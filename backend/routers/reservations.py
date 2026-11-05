from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session as DBSession, joinedload
from typing import Optional
from datetime import date
from pydantic import BaseModel, ValidationError
import json
import calendar
import math

import stripe

from config import settings
from db.database import get_db
from db.models import Reservation, Shareholder, Share, ReservationGuestAdjustment
from models.reservation import (
    ReservationCreate, ReservationResponse, ReservationSelfUpdate, ReservationAdminUpdate,
    AvailabilityResponse, RefundPreviewResponse, CancelReservationResponse, AdminRefundRequest,
    GuestAdjustmentRequest, GuestAdjustmentPreviewResponse, GuestAdjustmentCheckoutResponse,
    GuestAdjustmentApplyResponse, GuestAdjustmentReconcileRequest, GuestAdjustmentReconcileResponse,
)
from models.booking_season import BookingStatusResponse, BookingEligibilityResponse, CostPreviewResponse
from services.reservation_service import ReservationService
from services.booking_round_service import BookingRoundService
from services.date_service import get_simulated_date, get_today
from services.email_service import send_booking_confirmation_email, send_cancellation_confirmation_email
from services.frontend_origin_service import resolve_frontend_base_url
from services.guest_adjustment_service import GuestAdjustmentService
from services.guest_nights_service import (
    format_guest_nights_summary,
    get_reservation_guest_nights,
    guest_nights_total,
    normalize_guest_nights_input,
    parse_guest_nights_query,
    serialize_guest_nights,
    stay_units,
)
from services.refund_service import (
    CANCELLATION_NOTICE_STATUSES,
    REFUND_NOTICE_DAYS,
    compute_admin_refund_preview,
    compute_cancellation_eligibility,
    compute_refund_eligibility,
    process_cancellation,
)
from services.share_access_service import ShareAccessService
from services.unpaid_payment_service import (
    UnpaidPaymentEmailError,
    send_unpaid_reservation_payment_link,
)
from services.availability_release_service import send_prepared_release_alert
from .auth import ensure_not_viewer, get_current_shareholder, has_analytics_access

logger = __import__("logging").getLogger(__name__)

router = APIRouter(prefix="/api", tags=["reservations"])
MAX_CALENDAR_RANGE_MONTHS = 23
CALENDAR_VISIBLE_STATUSES = ["paid", "unpaid"]


class SendPaymentEmailResponse(BaseModel):
    sent: bool
    reservation_id: int
    to_email: str
    booker_name: str


def _user_can_access_share(db: DBSession, current: Shareholder, share_id: str) -> bool:
    return ShareAccessService.is_share_allowed(db, current, share_id)


def _user_owns_reservation(current: Shareholder, reservation: Reservation) -> bool:
    return reservation.booked_by_shareholder_id is not None and reservation.booked_by_shareholder_id == current.id


def _require_reservation_owner_or_admin(
    current: Shareholder,
    reservation: Reservation,
    is_admin: bool,
    detail: str,
) -> None:
    if is_admin:
        return
    if not _user_owns_reservation(current, reservation):
        raise HTTPException(status_code=403, detail=detail)


def _require_checkout_for_direct_reservations(current: Shareholder, simulated_date: date | None) -> None:
    """Block the legacy direct-create path for end users outside admin-controlled simulations."""
    ensure_not_viewer(current)
    if current.is_admin or current.is_superadmin:
        return
    if simulated_date is not None:
        return
    raise HTTPException(
        status_code=403,
        detail="Checkout is required. Create reservations through /api/checkout.",
    )


def _validate_date(value: str, field_name: str) -> str:
    """Validate an ISO date string, raising 400 on failure."""
    try:
        date.fromisoformat(value)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid date format for {field_name}: {value!r}")
    return value


def _parse_reservation_update_payload(payload: dict, is_admin: bool) -> dict:
    """Validate update payload against role-specific reservation update schema."""
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Invalid update payload")
    if not payload:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    schema_cls = ReservationAdminUpdate if is_admin else ReservationSelfUpdate
    allowed_fields = set(schema_cls.model_fields.keys())
    disallowed = sorted(set(payload.keys()) - allowed_fields)
    if disallowed:
        if is_admin:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported update field(s): {', '.join(disallowed)}"
            )
        raise HTTPException(
            status_code=403,
            detail=f"Only admins can update: {', '.join(disallowed)}"
        )

    try:
        return schema_cls(**payload).model_dump(exclude_unset=True)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())


def _require_cancellation_notice_window(
    db: DBSession, reservation: Reservation, *, is_admin: bool = False
) -> None:
    if is_admin:
        return
    if reservation.status not in CANCELLATION_NOTICE_STATUSES:
        return

    policy = compute_cancellation_eligibility(reservation, get_today(db))
    if not policy["eligible"]:
        raise HTTPException(status_code=400, detail=policy["reason"])


def _require_no_pending_guest_adjustments(
    db: DBSession,
    reservation: Reservation,
) -> None:
    pending = GuestAdjustmentService.pending_adjustments_for_reservation(db, reservation.id)
    if pending:
        raise HTTPException(
            status_code=409,
            detail="Cancel the pending guest adjustment checkout before cancelling this reservation",
        )


def _raise_for_retryable_refund_failure(result: dict) -> None:
    if result.get("retry_required"):
        raise HTTPException(status_code=502, detail=result["message"])


def reservation_to_response(reservation: Reservation) -> ReservationResponse:
    """Convert a Reservation ORM model to a ReservationResponse with share_name."""
    guest_nights = get_reservation_guest_nights(reservation)
    booked_by = reservation.booked_by_shareholder_rel
    booked_by_name = None
    if booked_by:
        first = (booked_by.first_name or "").strip()
        last = (booked_by.last_name or "").strip()
        booked_by_name = " ".join(part for part in [first, last] if part) or None

    return ReservationResponse(
        id=reservation.id,
        share=reservation.share,
        share_name=reservation.share_rel.share_name if reservation.share_rel else None,
        booked_by_shareholder_id=booked_by.id if booked_by else reservation.booked_by_shareholder_id,
        booked_by_shareholder_name=booked_by_name,
        guest_count=len(guest_nights),
        guest_nights=guest_nights,
        start_date=reservation.start_date,
        end_date=reservation.end_date,
        cabins=json.loads(reservation.cabins) if isinstance(reservation.cabins, str) else reservation.cabins,
        cost=reservation.cost,
        booking_round=reservation.booking_round,
        base_cost=reservation.base_cost,
        processing_fee=reservation.processing_fee,
        is_day_use=bool(reservation.is_day_use) if reservation.is_day_use is not None else False,
        guest_fee=reservation.guest_fee,
        status=reservation.status,
        stripe_checkout_session_id=reservation.stripe_checkout_session_id,
        stripe_payment_intent_id=reservation.stripe_payment_intent_id,
        created_at=reservation.created_at,
        cancelled_at=reservation.cancelled_at,
        refund_amount=reservation.refund_amount,
        refunded_at=reservation.refunded_at,
        stripe_refund_id=reservation.stripe_refund_id,
        cancellation_reason=reservation.cancellation_reason,
    )


@router.get("/reservations", response_model=list[ReservationResponse])
def list_reservations(
    share: Optional[str] = Query(None),
    cabin: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    include_cancelled: bool = Query(False),
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder)
):
    ensure_not_viewer(current, "Viewer accounts can only view the calendar, not reservation lists.")
    query = db.query(Reservation).options(
        joinedload(Reservation.share_rel),
        joinedload(Reservation.booked_by_shareholder_rel),
    )

    # Analytics/admin users can see the global reservation view used by admin dashboards.
    can_view_global = has_analytics_access(current)
    if not (include_cancelled and can_view_global):
        query = query.filter(Reservation.status.notin_(["cancelled", "refunded"]))

    allowed_share_ids = ShareAccessService.get_allowed_share_ids(db, current)
    if share:
        if not can_view_global and share not in allowed_share_ids:
            raise HTTPException(status_code=403, detail="Can only view reservations for your allowed shares")
        query = query.filter(Reservation.share == share)
    elif not can_view_global:
        query = query.filter(Reservation.share.in_(allowed_share_ids))

    if start_date and end_date:
        query = query.filter(
            Reservation.start_date <= end_date,
            Reservation.end_date >= start_date
        )

    reservations = query.order_by(Reservation.start_date).all()

    # Filter by cabin if specified (need to check JSON field)
    if cabin:
        reservations = [
            r for r in reservations
            if cabin in (json.loads(r.cabins) if isinstance(r.cabins, str) else r.cabins)
        ]

    return [reservation_to_response(r) for r in reservations]


@router.get("/reservations/{reservation_id}", response_model=ReservationResponse)
def get_reservation(
    reservation_id: int,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder)
):
    ensure_not_viewer(current, "Viewer accounts can only view the calendar, not reservation details.")
    reservation = db.query(Reservation).options(
        joinedload(Reservation.share_rel),
        joinedload(Reservation.booked_by_shareholder_rel),
    ).filter(Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    is_admin = bool(current.is_admin or current.is_superadmin)
    if not is_admin and not _user_can_access_share(db, current, reservation.share):
        raise HTTPException(status_code=403, detail="Can only view your own reservations")
    return reservation_to_response(reservation)


def send_reservation_confirmation(db: DBSession, reservation: Reservation, shareholder: Shareholder) -> None:
    """Fire-and-forget confirmation email for a reservation."""
    try:
        cabins = json.loads(reservation.cabins) if isinstance(reservation.cabins, str) else reservation.cabins
        nights = (date.fromisoformat(reservation.end_date) - date.fromisoformat(reservation.start_date)).days
        nights = max(1, nights)

        share_obj = db.query(Share).filter(Share.share_id == reservation.share).first()
        season = BookingRoundService.get_current_season(db)
        nights_used = nights_remaining = season_max = None
        is_prime = True
        if season:
            season_max = season.season_max_nights
            nights_used = BookingRoundService.get_share_season_nights(db, reservation.share, season)
            nights_remaining = season_max - nights_used
            prime_start = date.fromisoformat(season.prime_season_start)
            prime_end = date.fromisoformat(season.prime_season_end)
            res_start = date.fromisoformat(reservation.start_date)
            res_end = date.fromisoformat(reservation.end_date)
            is_prime = not (res_start >= prime_end or res_end <= prime_start)

        admins = db.query(Shareholder).filter(
            (Shareholder.is_admin == 1) | (Shareholder.is_superadmin == 1)
        ).all()
        admin_contacts = [{"name": f"{a.first_name} {a.last_name}", "email": a.email} for a in admins]

        send_booking_confirmation_email(
            to_email=shareholder.email,
            first_name=shareholder.first_name,
            start_date=reservation.start_date,
            end_date=reservation.end_date,
            cabins=cabins,
            is_day_use=bool(reservation.is_day_use),
            base_cost=reservation.base_cost or 0.0,
            guest_fee=reservation.guest_fee or 0.0,
            processing_fee=reservation.processing_fee or 0.0,
            total_cost=reservation.cost,
            reservation_id=reservation.id,
            share_name=share_obj.share_name if share_obj else None,
            booking_round=reservation.booking_round,
            nights=nights,
            guest_count=reservation.guest_count,
            nights_used=nights_used,
            nights_remaining=nights_remaining,
            season_max_nights=season_max,
            is_prime_season=is_prime,
            admin_contacts=admin_contacts,
        )
    except Exception:
        logger.exception("Failed to send booking confirmation email")


def _send_cancellation_email(db: DBSession, reservation: Reservation, current: Shareholder, result: dict) -> None:
    """Fire-and-forget cancellation confirmation email."""
    try:
        cabins = json.loads(reservation.cabins) if isinstance(reservation.cabins, str) else reservation.cabins
        nights = max(1, (date.fromisoformat(reservation.end_date) - date.fromisoformat(reservation.start_date)).days)
        share_obj = db.query(Share).filter(Share.share_id == reservation.share).first()

        # Prefer the actual reservation booker; only fall back to the share if legacy data lacks a booker id.
        owner = None
        if reservation.booked_by_shareholder_id:
            owner = db.query(Shareholder).filter(
                Shareholder.id == reservation.booked_by_shareholder_id
            ).first()
        if not owner:
            owner = db.query(Shareholder).filter(Shareholder.share == reservation.share).first()
        if not owner:
            return

        send_cancellation_confirmation_email(
            to_email=owner.email,
            first_name=owner.first_name,
            start_date=reservation.start_date,
            end_date=reservation.end_date,
            cabins=cabins,
            reservation_id=reservation.id,
            share_name=share_obj.share_name if share_obj else None,
            nights=nights,
            refund_issued=result.get("refund_issued", False),
            refund_amount=result.get("refund_amount"),
            processing_fee=reservation.processing_fee or 0.0,
        )
    except Exception:
        logger.exception("Failed to send cancellation confirmation email")


def _send_availability_release_alert(db: DBSession, reservation: Reservation) -> None:
    prepared = getattr(reservation, "_availability_release_alert", None)
    if not prepared:
        return
    try:
        send_prepared_release_alert(db, prepared)
    except Exception:
        logger.exception(
            "Immediate availability-release send failed after cancellation committed reservation_id=%s",
            reservation.id,
        )


@router.post("/reservations", response_model=ReservationResponse)
def create_reservation(
    reservation: ReservationCreate,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder)
):
    try:
        reservation.share = ShareAccessService.resolve_share_selection(
            db, current, reservation.share
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    simulated_date = get_simulated_date(db)
    _require_checkout_for_direct_reservations(current, simulated_date)

    # Suppress the superadmin booking override during time travel simulation.
    is_admin = bool(current.is_superadmin) and simulated_date is None

    db_reservation, error = ReservationService.create_reservation(
        db,
        reservation,
        is_admin=is_admin,
        booked_by_shareholder_id=current.id,
    )
    if error:
        raise HTTPException(status_code=400, detail=error)

    send_reservation_confirmation(db, db_reservation, current)

    return reservation_to_response(db_reservation)


@router.put("/reservations/{reservation_id}", response_model=ReservationResponse)
def update_reservation(
    reservation_id: int,
    payload: dict,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder)
):
    ensure_not_viewer(current)
    reservation = db.query(Reservation).filter(
        Reservation.id == reservation_id
    ).with_for_update().first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    # Admin+ can update any reservation, others only their own
    is_admin = bool(current.is_admin or current.is_superadmin)
    _require_reservation_owner_or_admin(
        current,
        reservation,
        is_admin,
        "Can only update reservations you booked",
    )

    update_data = _parse_reservation_update_payload(payload, is_admin)

    if "start_date" in update_data:
        _validate_date(update_data["start_date"], "start_date")
    if "end_date" in update_data:
        _validate_date(update_data["end_date"], "end_date")

    existing_cabins = json.loads(reservation.cabins) if isinstance(reservation.cabins, str) else reservation.cabins
    candidate_start = update_data.get("start_date", reservation.start_date)
    candidate_end = update_data.get("end_date", reservation.end_date)
    new_cabins = update_data.get("cabins", existing_cabins)
    current_guest_nights = get_reservation_guest_nights(reservation)
    guest_payload_changed = ("guest_count" in update_data) or ("guest_nights" in update_data)
    new_guest_count = update_data.get("guest_count", reservation.guest_count)
    current_is_day_use = bool(reservation.is_day_use)

    try:
        new_start, new_end, normalized_is_day_use = ReservationService.normalize_reservation_dates(
            candidate_start,
            candidate_end,
            current_is_day_use
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    dates_or_cabins_changed = any(k in update_data for k in ("start_date", "end_date", "cabins"))
    pricing_inputs_changed = dates_or_cabins_changed or guest_payload_changed

    try:
        if "guest_nights" in update_data:
            new_guest_nights = normalize_guest_nights_input(
                update_data.get("guest_nights"),
                None,
                max_units=stay_units(new_start, new_end),
            )
        elif "guest_count" in update_data:
            new_guest_nights = normalize_guest_nights_input(
                None,
                new_guest_count,
                max_units=stay_units(new_start, new_end),
            )
        elif dates_or_cabins_changed:
            new_guest_nights = normalize_guest_nights_input(
                current_guest_nights,
                None,
                max_units=stay_units(new_start, new_end),
            )
        else:
            new_guest_nights = current_guest_nights
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if reservation.status == "paid" and guest_payload_changed:
        raise HTTPException(
            status_code=400,
            detail="Paid reservation guest changes must use the guest adjustment flow.",
        )

    if dates_or_cabins_changed:
        with ReservationService.booking_scope(
            db,
            reservation.share,
            [*existing_cabins, *new_cabins],
        ):
            # Match create behavior: only superadmins can bypass booking round restrictions, and
            # never while time travel simulation is active.
            admin_bypass = bool(current.is_superadmin) and get_simulated_date(db) is None
            eligible, error, context = BookingRoundService.check_round_eligibility(
                db,
                reservation.share,
                new_start,
                new_end,
                new_cabins,
                is_admin=admin_bypass
            )
            if not eligible:
                raise HTTPException(status_code=400, detail=error or "Updated reservation is not eligible")

            conflicts = ReservationService.get_conflicting_reservations(
                db, new_cabins, new_start, new_end, exclude_id=reservation_id
            )
            if conflicts:
                raise HTTPException(status_code=400, detail="Update would create booking conflict")

            if not admin_bypass:
                updated_round = context.get("round") or context.get("current_round")
                if updated_round:
                    reservation.booking_round = updated_round

    if pricing_inputs_changed:
        cost_info = BookingRoundService.compute_reservation_cost(
            db,
            new_start,
            new_end,
            new_cabins,
            is_day_use=normalized_is_day_use,
            guest_count=new_guest_count,
            guest_nights=new_guest_nights,
        )
        reservation.cost = cost_info["total"]
        reservation.base_cost = cost_info["base_cost"]
        reservation.processing_fee = cost_info["processing_fee"]
        reservation.guest_fee = cost_info["guest_fee"] if cost_info["guest_fee"] > 0 else None

    if guest_payload_changed or dates_or_cabins_changed:
        reservation.guest_count = len(new_guest_nights)
        reservation.guest_nights_json = serialize_guest_nights(new_guest_nights)
    if "start_date" in update_data:
        reservation.start_date = new_start
    if "end_date" in update_data:
        reservation.end_date = new_end
    if "start_date" in update_data or "end_date" in update_data:
        reservation.is_day_use = 1 if normalized_is_day_use else 0
    if "cabins" in update_data:
        reservation.cabins = json.dumps(new_cabins)
    if "status" in update_data:
        status_value = update_data["status"]
        next_status = status_value.value if hasattr(status_value, "value") else str(status_value)
        previous_status = reservation.status
        if (
            next_status in ("cancelled", "refunded")
            and reservation.status not in ("cancelled", "refunded")
        ):
            _require_cancellation_notice_window(db, reservation, is_admin=is_admin)
        reservation.status = next_status
        if next_status == "unpaid":
            reservation.stripe_checkout_session_id = None
            reservation.cancelled_at = None
            reservation.cancellation_reason = None
            if previous_status not in ("paid", "refunded"):
                reservation.stripe_payment_intent_id = None
                reservation.refund_amount = None
                reservation.refunded_at = None
                reservation.stripe_refund_id = None

    db.commit()
    db.refresh(reservation)
    return reservation_to_response(reservation)


@router.post("/reservations/{reservation_id}/send-payment-email", response_model=SendPaymentEmailResponse)
def send_payment_email(
    reservation_id: int,
    request: Request,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder),
):
    ensure_not_viewer(current)
    if not (current.is_admin or current.is_superadmin):
        raise HTTPException(status_code=403, detail="Admin access required")

    reservation = db.query(Reservation).options(
        joinedload(Reservation.share_rel),
        joinedload(Reservation.booked_by_shareholder_rel),
    ).filter(
        Reservation.id == reservation_id
    ).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    try:
        result = send_unpaid_reservation_payment_link(
            db,
            reservation,
            resolve_frontend_base_url(request),
        )
    except UnpaidPaymentEmailError as exc:
        if exc.code == "send_failed":
            raise HTTPException(status_code=502, detail=exc.detail)
        raise HTTPException(status_code=400, detail=exc.detail)

    return SendPaymentEmailResponse(
        sent=True,
        reservation_id=result.reservation_id,
        to_email=result.to_email,
        booker_name=result.booker_name,
    )


@router.delete("/reservations/{reservation_id}", response_model=CancelReservationResponse)
def delete_reservation(
    reservation_id: int,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder)
):
    ensure_not_viewer(current)
    reservation = db.query(Reservation).options(
        joinedload(Reservation.share_rel)
    ).filter(
        Reservation.id == reservation_id
    ).with_for_update(of=Reservation).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    # Admin+ can delete any reservation, others only their own
    is_admin = bool(current.is_admin or current.is_superadmin)
    _require_reservation_owner_or_admin(
        current,
        reservation,
        is_admin,
        "Can only cancel reservations you booked",
    )

    _require_cancellation_notice_window(db, reservation, is_admin=is_admin)
    _require_no_pending_guest_adjustments(db, reservation)

    reason = "admin" if (is_admin and not _user_owns_reservation(current, reservation)) else "self_service"
    was_active = reservation.status not in ("cancelled", "refunded")
    result = process_cancellation(db, reservation, reason=reason)
    _raise_for_retryable_refund_failure(result)
    if was_active:
        _send_cancellation_email(db, reservation, current, result)
        _send_availability_release_alert(db, reservation)
    return CancelReservationResponse(**result)


@router.get("/reservations/{reservation_id}/refund-preview", response_model=RefundPreviewResponse)
def get_refund_preview(
    reservation_id: int,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder)
):
    """Preview refund eligibility for a reservation."""
    ensure_not_viewer(current)
    reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    is_admin = bool(current.is_admin or current.is_superadmin)
    _require_reservation_owner_or_admin(
        current,
        reservation,
        is_admin,
        "Can only preview refunds for reservations you booked",
    )

    if reservation.status in ("cancelled", "refunded"):
        raise HTTPException(status_code=400, detail=f"Reservation is already {reservation.status}")

    today = get_today(db)

    if reservation.status == "paid":
        preview = (
            compute_admin_refund_preview(reservation, today)
            if is_admin
            else compute_refund_eligibility(reservation, today)
        )
        return RefundPreviewResponse(**preview)

    if reservation.status == "reserved":
        policy = compute_cancellation_eligibility(reservation, today)
        admin_override = is_admin and not policy["eligible"]
        cancellation_eligible = policy["eligible"] or is_admin
        reason = (
            f"No payment on file. Cancellation allowed ({policy['days_until_checkin']} days notice)."
            if policy["eligible"]
            else policy["reason"]
        )
        if admin_override:
            reason += " (Admin override: cancellation allowed.)"
        return RefundPreviewResponse(
            eligible=False,
            cancellation_eligible=cancellation_eligible,
            days_until_checkin=policy["days_until_checkin"],
            refund_amount=0.0,
            processing_fee_kept=0.0,
            status=reservation.status,
            reason=reason,
            admin_override=admin_override,
        )

    # Non-paid, non-confirmed statuses - no refund to preview
    checkin = date.fromisoformat(reservation.start_date)
    days_until = (checkin - today).days
    return RefundPreviewResponse(
        eligible=False,
        days_until_checkin=days_until,
        refund_amount=0.0,
        processing_fee_kept=0.0,
        status=reservation.status,
        reason=f"No payment on file (status: {reservation.status}). Cancellation will release the dates.",
    )


@router.post("/reservations/{reservation_id}/refund", response_model=CancelReservationResponse)
def refund_and_cancel_reservation(
    reservation_id: int,
    payload: AdminRefundRequest,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder),
):
    """Issue an admin-authorized refund and cancel the reservation."""
    ensure_not_viewer(current)
    if not (current.is_admin or current.is_superadmin):
        raise HTTPException(status_code=403, detail="Admin access required")
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe is not configured")

    reservation = db.query(Reservation).filter(
        Reservation.id == reservation_id
    ).with_for_update().first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if reservation.status in ("cancelled", "refunded"):
        raise HTTPException(status_code=400, detail=f"Reservation is already {reservation.status}")
    if reservation.status != "paid":
        raise HTTPException(status_code=400, detail="Only paid reservations can be refunded")
    if reservation.refunded_at or reservation.stripe_refund_id:
        raise HTTPException(status_code=400, detail="Reservation already has a cancellation refund")
    if not reservation.stripe_payment_intent_id:
        raise HTTPException(status_code=400, detail="No Stripe payment is available to refund")

    _require_no_pending_guest_adjustments(db, reservation)

    preview = compute_admin_refund_preview(reservation, get_today(db))
    if preview["override_required"] and not payload.override_policy:
        raise HTTPException(
            status_code=409,
            detail=(
                f"This reservation has {preview['days_until_checkin']} days before check-in, "
                f"which is less than the {REFUND_NOTICE_DAYS}-day refund policy allows. "
                "An explicit admin override is required."
            ),
        )
    if preview["refund_amount"] <= 0:
        raise HTTPException(status_code=400, detail="There is no refundable balance remaining")

    result = process_cancellation(
        db,
        reservation,
        reason="admin_policy_override" if preview["override_required"] else "admin_refund",
        override_refund_policy=preview["override_required"],
        cancel_on_refund_failure=False,
    )
    _raise_for_retryable_refund_failure(result)
    if not result["refund_issued"]:
        raise HTTPException(status_code=502, detail=result["message"])

    _send_cancellation_email(db, reservation, current, result)
    _send_availability_release_alert(db, reservation)
    return CancelReservationResponse(**result)


@router.post("/reservations/{reservation_id}/cancel", response_model=CancelReservationResponse)
def cancel_reservation(
    reservation_id: int,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder)
):
    """Cancel a reservation with refund handling for paid reservations."""
    ensure_not_viewer(current)
    reservation = db.query(Reservation).options(
        joinedload(Reservation.share_rel)
    ).filter(
        Reservation.id == reservation_id
    ).with_for_update(of=Reservation).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    is_admin = bool(current.is_admin or current.is_superadmin)
    _require_reservation_owner_or_admin(
        current,
        reservation,
        is_admin,
        "Can only cancel reservations you booked",
    )

    if reservation.status in ("cancelled", "refunded"):
        raise HTTPException(status_code=400, detail=f"Reservation is already {reservation.status}")

    _require_cancellation_notice_window(db, reservation, is_admin=is_admin)
    _require_no_pending_guest_adjustments(db, reservation)

    reason = "admin" if (is_admin and not _user_owns_reservation(current, reservation)) else "self_service"
    result = process_cancellation(db, reservation, reason=reason)
    _raise_for_retryable_refund_failure(result)
    _send_cancellation_email(db, reservation, current, result)
    _send_availability_release_alert(db, reservation)
    return CancelReservationResponse(**result)


def _get_reservation_for_guest_adjustment(
    db: DBSession,
    reservation_id: int,
    current: Shareholder,
    *,
    lock: bool = False,
) -> tuple[Reservation, bool]:
    ensure_not_viewer(current)
    query = db.query(Reservation).options(
        joinedload(Reservation.share_rel)
    ).filter(Reservation.id == reservation_id)
    if lock:
        query = query.with_for_update(of=Reservation)
    reservation = query.first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    is_admin = bool(current.is_admin or current.is_superadmin)
    _require_reservation_owner_or_admin(
        current,
        reservation,
        is_admin,
        "Can only edit guests on reservations you booked",
    )

    return reservation, is_admin


def _create_guest_adjustment_checkout_session(
    reservation: Reservation,
    adjustment: ReservationGuestAdjustment,
    customer_email: str,
    preview: dict,
    app_url: str,
):
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe is not configured")

    stripe.api_key = settings.stripe_secret_key
    amount_cents = math.ceil(float(preview["charge_amount"]) * 100)
    if amount_cents <= 0:
        raise HTTPException(status_code=400, detail="Additional charge must be greater than zero")

    updated_guest_nights = [int(v) for v in preview.get("updated_guest_nights", [])]
    guest_summary = format_guest_nights_summary(updated_guest_nights)
    guest_nights_sum = guest_nights_total(updated_guest_nights)
    guest_fee_delta_cents = max(0, round(float(preview.get("delta_guest_fee", 0.0)) * 100))
    processing_fee_delta_cents = max(0, round(float(preview.get("delta_processing_fee", 0.0)) * 100))
    diff = amount_cents - (guest_fee_delta_cents + processing_fee_delta_cents)
    processing_fee_delta_cents += diff

    line_items = []
    if guest_fee_delta_cents > 0:
        line_items.append({
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "Guest Fee Adjustment",
                    "description": (
                        f"Reservation #{reservation.id}: {guest_nights_sum} guest-night"
                        f"{'s' if guest_nights_sum != 1 else ''}. {guest_summary}"
                    ),
                },
                "unit_amount": guest_fee_delta_cents,
            },
            "quantity": 1,
        })
    if processing_fee_delta_cents > 0:
        line_items.append({
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "Processing Fee Adjustment",
                    "description": f"Reservation #{reservation.id} processing fee change",
                },
                "unit_amount": processing_fee_delta_cents,
            },
            "quantity": 1,
        })
    if not line_items:
        raise HTTPException(status_code=400, detail="No line items to charge for guest adjustment")

    return stripe.checkout.Session.create(
        mode="payment",
        line_items=line_items,
        metadata={
            "reservation_id": str(reservation.id),
            "adjustment_id": str(adjustment.id),
            "checkout_kind": "guest_adjustment",
            "guest_nights": serialize_guest_nights(updated_guest_nights) or "[]",
        },
        customer_email=customer_email,
        success_url=f"{app_url}/booking/success?reservation_id={reservation.id}&adjustment_id={adjustment.id}",
        cancel_url=f"{app_url}/booking/cancel?reservation_id={reservation.id}&adjustment_id={adjustment.id}",
    )


@router.post("/reservations/{reservation_id}/guest-adjustment-preview", response_model=GuestAdjustmentPreviewResponse)
def preview_guest_adjustment(
    reservation_id: int,
    payload: GuestAdjustmentRequest,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder),
):
    reservation, _ = _get_reservation_for_guest_adjustment(db, reservation_id, current)
    try:
        preview = GuestAdjustmentService.build_preview(db, reservation, payload.guest_nights)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return GuestAdjustmentPreviewResponse(**preview)


@router.post("/reservations/{reservation_id}/guest-adjustment-checkout", response_model=GuestAdjustmentCheckoutResponse)
def start_guest_adjustment_checkout(
    reservation_id: int,
    payload: GuestAdjustmentRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder),
):
    reservation, _ = _get_reservation_for_guest_adjustment(
        db,
        reservation_id,
        current,
        lock=True,
    )
    try:
        preview = GuestAdjustmentService.build_preview(db, reservation, payload.guest_nights)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not preview["allowed"]:
        raise HTTPException(status_code=400, detail=preview["reason"] or "Guest edit not allowed")
    if preview["action"] != "collect":
        raise HTTPException(status_code=400, detail=f"Guest adjustment does not require checkout (action: {preview['action']})")

    pending = GuestAdjustmentService.pending_adjustments_for_reservation(db, reservation.id)
    if pending:
        raise HTTPException(status_code=400, detail="A guest adjustment is already pending for this reservation")

    adjustment = GuestAdjustmentService.create_adjustment_record(
        db,
        reservation,
        preview,
        created_by_shareholder_id=current.id,
    )

    frontend_base_url = resolve_frontend_base_url(request)

    try:
        session = _create_guest_adjustment_checkout_session(
            reservation,
            adjustment,
            current.email,
            preview,
            frontend_base_url,
        )
    except stripe.StripeError as exc:
        GuestAdjustmentService.mark_adjustment(
            db,
            adjustment,
            status="failed",
            error_message=exc.user_message or str(exc),
        )
        logger.exception("Guest adjustment checkout creation failed")
        raise HTTPException(status_code=502, detail=f"Payment service error: {exc.user_message or str(exc)}")

    GuestAdjustmentService.mark_adjustment(
        db,
        adjustment,
        status="pending",
        stripe_checkout_session_id=session.id,
    )
    return GuestAdjustmentCheckoutResponse(
        reservation_id=reservation.id,
        adjustment_id=adjustment.id,
        checkout_url=session.url,
    )


@router.post("/reservations/{reservation_id}/guest-adjustment-apply", response_model=GuestAdjustmentApplyResponse)
def apply_guest_adjustment(
    reservation_id: int,
    payload: GuestAdjustmentRequest,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder),
):
    reservation, is_admin = _get_reservation_for_guest_adjustment(
        db,
        reservation_id,
        current,
        lock=True,
    )
    try:
        preview = GuestAdjustmentService.build_preview(db, reservation, payload.guest_nights)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not preview["allowed"]:
        raise HTTPException(status_code=400, detail=preview["reason"] or "Guest edit not allowed")
    if not is_admin:
        if preview["action"] == "collect":
            raise HTTPException(status_code=400, detail="Additional charge required. Use guest-adjustment-checkout.")
        if preview["action"] == "refund":
            raise HTTPException(status_code=400, detail="Refund required. Use guest-adjustment-refund.")

    adjustment_id = None
    effective_action = preview["action"]
    if effective_action in ("apply", "none", "collect", "refund"):
        adjustment = GuestAdjustmentService.create_adjustment_record(
            db,
            reservation,
            preview,
            created_by_shareholder_id=current.id,
        )
        adjustment_id = adjustment.id
        GuestAdjustmentService.apply_guest_nights(db, reservation, preview["updated_guest_nights"], commit=False)
        GuestAdjustmentService.mark_adjustment(db, adjustment, status="applied", commit=False)
        db.commit()
        db.refresh(reservation)

    admin_note = " (admin - no payment processed)" if is_admin and effective_action in ("collect", "refund") else ""
    return GuestAdjustmentApplyResponse(
        reservation=reservation_to_response(reservation),
        action="none" if effective_action == "none" else "apply",
        adjustment_id=adjustment_id,
        refund_issued=False,
        refund_amount=None,
        message=f"Guest changes saved.{admin_note}" if effective_action != "none" else "No charge change.",
    )


@router.post("/reservations/{reservation_id}/guest-adjustment-refund", response_model=GuestAdjustmentApplyResponse)
def refund_guest_adjustment(
    reservation_id: int,
    payload: GuestAdjustmentRequest,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder),
):
    reservation, _ = _get_reservation_for_guest_adjustment(
        db,
        reservation_id,
        current,
        lock=True,
    )
    try:
        preview = GuestAdjustmentService.build_preview(db, reservation, payload.guest_nights)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not preview["allowed"]:
        raise HTTPException(status_code=400, detail=preview["reason"] or "Guest edit not allowed")
    if preview["action"] != "refund":
        raise HTTPException(status_code=400, detail=f"Guest adjustment is not a refund (action: {preview['action']})")

    adjustment = GuestAdjustmentService.create_adjustment_record(
        db,
        reservation,
        preview,
        created_by_shareholder_id=current.id,
    )

    refund_amount = preview["refund_amount"]
    requested_refund_amount = preview.get("requested_refund_amount", refund_amount)
    retained_this_action = preview.get("processing_fee_retained", 0.0)
    original_processing_fee = reservation.processing_fee or 0.0
    original_total = reservation.cost or 0.0
    stripe_refund_id = None
    if refund_amount > 0 and reservation.stripe_payment_intent_id and settings.stripe_secret_key:
        stripe.api_key = settings.stripe_secret_key
        try:
            refund = stripe.Refund.create(
                payment_intent=reservation.stripe_payment_intent_id,
                amount=round(refund_amount * 100),
            )
            stripe_refund_id = refund.id
        except stripe.StripeError as exc:
            GuestAdjustmentService.mark_adjustment(
                db,
                adjustment,
                status="failed",
                error_message=exc.user_message or str(exc),
            )
            logger.exception("Guest adjustment refund failed")
            raise HTTPException(status_code=502, detail=f"Refund failed: {exc.user_message or str(exc)}")

    GuestAdjustmentService.apply_guest_nights(db, reservation, preview["updated_guest_nights"], commit=False)
    reservation.processing_fee = original_processing_fee
    reservation.cost = round(original_total - refund_amount, 2)
    reservation.guest_fee_refunded = round((reservation.guest_fee_refunded or 0.0) + refund_amount, 2)
    GuestAdjustmentService.mark_adjustment(
        db,
        adjustment,
        status="refunded",
        stripe_refund_id=stripe_refund_id,
        commit=False,
    )
    db.commit()
    db.refresh(reservation)

    return GuestAdjustmentApplyResponse(
        reservation=reservation_to_response(reservation),
        action="refund",
        adjustment_id=adjustment.id,
        refund_issued=True,
        refund_amount=refund_amount,
        message=(
            f"Requested ${requested_refund_amount:.2f}, refunded ${refund_amount:.2f}. "
            f"Retained ${retained_this_action:.2f} per 4% booking fee policy."
        ),
    )


@router.post("/reservations/{reservation_id}/guest-adjustment-reconcile", response_model=GuestAdjustmentReconcileResponse)
def reconcile_guest_adjustment(
    reservation_id: int,
    payload: GuestAdjustmentReconcileRequest,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder),
):
    reservation, _ = _get_reservation_for_guest_adjustment(
        db,
        reservation_id,
        current,
        lock=True,
    )
    adjustment = db.query(ReservationGuestAdjustment).filter(
        ReservationGuestAdjustment.id == payload.adjustment_id,
        ReservationGuestAdjustment.reservation_id == reservation.id,
    ).first()
    if not adjustment:
        raise HTTPException(status_code=404, detail="Guest adjustment not found")

    if adjustment.status in ("paid", "applied", "refunded", "failed", "cancelled"):
        return GuestAdjustmentReconcileResponse(
            status="applied" if adjustment.status == "applied" else adjustment.status,  # type: ignore[arg-type]
            adjustment_id=adjustment.id,
            reservation_id=reservation.id,
        )

    if not adjustment.stripe_checkout_session_id:
        return GuestAdjustmentReconcileResponse(
            status="pending",
            adjustment_id=adjustment.id,
            reservation_id=reservation.id,
        )

    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe is not configured")
    stripe.api_key = settings.stripe_secret_key

    try:
        session = stripe.checkout.Session.retrieve(adjustment.stripe_checkout_session_id)
    except stripe.StripeError as exc:
        raise HTTPException(status_code=502, detail=f"Payment service error: {exc.user_message or str(exc)}")

    if session.payment_status == "paid":
        payment_intent = session.payment_intent if isinstance(session.payment_intent, str) else None
        GuestAdjustmentService.finalize_paid_adjustment(
            db,
            reservation,
            adjustment,
            payment_intent_id=payment_intent,
        )
        return GuestAdjustmentReconcileResponse(
            status="paid",
            adjustment_id=adjustment.id,
            reservation_id=reservation.id,
        )

    return GuestAdjustmentReconcileResponse(
        status="pending",
        adjustment_id=adjustment.id,
        reservation_id=reservation.id,
    )


@router.post("/guest-adjustments/{adjustment_id}/cancel")
def cancel_guest_adjustment_checkout(
    adjustment_id: int,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder),
):
    adjustment = db.query(ReservationGuestAdjustment).join(
        Reservation, Reservation.id == ReservationGuestAdjustment.reservation_id
    ).filter(ReservationGuestAdjustment.id == adjustment_id).first()
    if not adjustment:
        raise HTTPException(status_code=404, detail="Guest adjustment not found")

    reservation = db.query(Reservation).filter(Reservation.id == adjustment.reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    is_admin = bool(current.is_admin or current.is_superadmin)
    if not is_admin and not _user_can_access_share(db, current, reservation.share):
        raise HTTPException(status_code=403, detail="Can only cancel your own guest adjustment")

    if adjustment.status != "pending":
        return {"status": adjustment.status}

    if adjustment.stripe_checkout_session_id and settings.stripe_secret_key:
        stripe.api_key = settings.stripe_secret_key
        try:
            stripe.checkout.Session.expire(adjustment.stripe_checkout_session_id)
        except stripe.StripeError:
            logger.warning("Could not expire guest adjustment checkout %s", adjustment.stripe_checkout_session_id)

    GuestAdjustmentService.mark_adjustment(db, adjustment, status="cancelled")
    return {"status": "cancelled"}


@router.get("/booking-status", response_model=BookingStatusResponse)
def get_booking_status(
    share: Optional[str] = Query(None),
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder)
):
    """Get current booking round status for the authenticated user."""
    try:
        selected_share = ShareAccessService.resolve_share_selection(db, current, share)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    is_admin = bool(current.is_superadmin) and get_simulated_date(db) is None
    status = BookingRoundService.get_booking_status(db, selected_share)

    if current.is_viewer:
        status["can_book"] = False
        status["reason"] = "Viewer access: this account can view the calendar for its assigned share but cannot book."
        return BookingStatusResponse(**status)

    # Superadmins can always book (unless simulating).
    if is_admin:
        status["can_book"] = True
        status["reason"] = None

    return BookingStatusResponse(**status)


@router.get("/booking-eligibility", response_model=BookingEligibilityResponse)
def get_booking_eligibility(
    start_date: str = Query(...),
    end_date: str = Query(...),
    share: Optional[str] = Query(None),
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder)
):
    """Check whether the selected share can book the requested date range right now."""
    _validate_date(start_date, "start_date")
    _validate_date(end_date, "end_date")

    try:
        selected_share = ShareAccessService.resolve_share_selection(db, current, share)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    try:
        normalized_start, normalized_end, _ = ReservationService.normalize_reservation_dates(
            start_date,
            end_date,
            False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if current.is_viewer:
        return BookingEligibilityResponse(
            eligible=False,
            reason="Viewer access: this account can view the calendar for its assigned share but cannot book.",
            booking_round=None,
            current_round=None,
        )

    is_admin = bool(current.is_superadmin) and get_simulated_date(db) is None
    eligible, reason, context = BookingRoundService.check_round_eligibility(
        db,
        selected_share,
        normalized_start,
        normalized_end,
        [],
        is_admin=is_admin,
    )

    return BookingEligibilityResponse(
        eligible=eligible,
        reason=reason,
        booking_round=context.get("round"),
        current_round=context.get("current_round"),
    )


@router.get("/booking-cost", response_model=CostPreviewResponse)
def get_booking_cost(
    start_date: str = Query(...),
    end_date: str = Query(...),
    cabins: str = Query(..., description="Comma-separated cabin IDs"),
    is_day_use: bool = Query(False),
    guest_count: int = Query(0),
    guest_nights: Optional[str] = Query(None, description="CSV or JSON list of per-guest nights"),
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(get_current_shareholder)
):
    """Preview cost for a potential reservation."""
    _validate_date(start_date, "start_date")
    _validate_date(end_date, "end_date")
    cabin_list = [c.strip() for c in cabins.split(",") if c.strip()]

    try:
        normalized_start, normalized_end, normalized_day_use = ReservationService.normalize_reservation_dates(
            start_date,
            end_date,
            is_day_use
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        parsed_guest_nights = parse_guest_nights_query(guest_nights)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    cost_info = BookingRoundService.compute_reservation_cost(
        db, normalized_start, normalized_end, cabin_list,
        is_day_use=normalized_day_use, guest_count=guest_count, guest_nights=parsed_guest_nights
    )
    return CostPreviewResponse(**cost_info)


@router.get("/availability", response_model=AvailabilityResponse)
def check_availability(
    start_date: str = Query(...),
    end_date: str = Query(...),
    cabins: Optional[str] = Query(None),  # Comma-separated: "pine,cedar"
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(get_current_shareholder)
):
    _validate_date(start_date, "start_date")
    _validate_date(end_date, "end_date")
    try:
        normalized_start, normalized_end, _ = ReservationService.normalize_reservation_dates(
            start_date,
            end_date,
            False
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    cabin_list = cabins.split(",") if cabins else None
    cabin_conflicts = ReservationService.check_availability(db, normalized_start, normalized_end, cabin_list)

    cabin_availability = {cid: len(res) == 0 for cid, res in cabin_conflicts.items()}
    all_available = all(cabin_availability.values())

    # Deduplicate conflicts across cabins
    seen_ids: set[int] = set()
    conflicts = []
    if not all_available:
        for res_list in cabin_conflicts.values():
            for res in res_list:
                if res.id not in seen_ids:
                    seen_ids.add(res.id)
                    conflicts.append(reservation_to_response(res))

    return AvailabilityResponse(
        available=all_available,
        cabins=cabin_availability,
        conflicts=conflicts
    )


def _month_specs(start_year: int, start_month: int, count: int) -> list[dict]:
    specs: list[dict] = []
    year = start_year
    month = start_month

    for _ in range(count):
        _, last_day = calendar.monthrange(year, month)
        specs.append({
            "year": year,
            "month": month,
            "last_day": last_day,
            "start_date": f"{year}-{month:02d}-01",
            "end_date": f"{year}-{month:02d}-{last_day:02d}",
        })
        month += 1
        if month > 12:
            month = 1
            year += 1

    return specs


def _booked_by_short_name(reservation: Reservation) -> Optional[str]:
    booked_by = reservation.booked_by_shareholder_rel
    if not booked_by:
        return None

    first = (booked_by.first_name or "").strip()
    last = (booked_by.last_name or "").strip()
    if not first or not last:
        return None

    return f"{first[0]} {last}"


def _calendar_display_name(reservation: Reservation, booked_by_short_name: Optional[str]) -> str:
    share_label = reservation.share_rel.share_name if reservation.share_rel else reservation.share
    if booked_by_short_name:
        return f"{share_label} ({booked_by_short_name})"
    return share_label


def _build_calendar_month(year: int, month: int, last_day: int, reservations: list[Reservation]) -> dict:
    rows = []
    for res in reservations:
        booked_by_short_name = _booked_by_short_name(res)
        rows.append({
            "id": res.id,
            "share": res.share,
            "share_name": res.share_rel.share_name if res.share_rel else None,
            "booked_by_short_name": booked_by_short_name,
            "calendar_display_name": _calendar_display_name(res, booked_by_short_name),
            "cabins": json.loads(res.cabins) if isinstance(res.cabins, str) else res.cabins,
            "guest_count": res.guest_count,
            "is_day_use": bool(res.is_day_use),
            "status": res.status,
            "end_date": res.end_date,
            "start_date": res.start_date,
        })

    days = []
    for day in range(1, last_day + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        day_reservations = []

        for row in rows:
            if row["is_day_use"]:
                in_range = row["start_date"] <= date_str < row["end_date"]
            else:
                in_range = row["start_date"] <= date_str <= row["end_date"]

            if in_range:
                day_reservations.append({
                    "id": row["id"],
                    "share": row["share"],
                    "share_name": row["share_name"],
                    "booked_by_short_name": row["booked_by_short_name"],
                    "calendar_display_name": row["calendar_display_name"],
                    "cabins": row["cabins"],
                    "guest_count": row["guest_count"],
                    "is_day_use": row["is_day_use"],
                    "status": row["status"],
                    "is_checkout": date_str == row["end_date"] and not row["is_day_use"],
                })

        days.append({
            "date": date_str,
            "day": day,
            "reservations": day_reservations
        })

    return {
        "year": year,
        "month": month,
        "days": days
    }


@router.get("/calendar-range")
def get_calendar_range(
    start_year: int = Query(...),
    start_month: int = Query(..., ge=1, le=12),
    count: int = Query(6, ge=1, le=MAX_CALENDAR_RANGE_MONTHS),
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(get_current_shareholder)
):
    specs = _month_specs(start_year, start_month, count)
    range_start = specs[0]["start_date"]
    range_end = specs[-1]["end_date"]

    reservations = db.query(Reservation).options(
        joinedload(Reservation.share_rel),
        joinedload(Reservation.booked_by_shareholder_rel),
    ).filter(
        Reservation.start_date <= range_end,
        Reservation.end_date >= range_start,
        Reservation.status.in_(CALENDAR_VISIBLE_STATUSES),
    ).all()

    months = [
        _build_calendar_month(spec["year"], spec["month"], spec["last_day"], reservations)
        for spec in specs
    ]

    return {"months": months}


@router.get("/calendar/{year}/{month}")
def get_calendar(
    year: int,
    month: int,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(get_current_shareholder)
):
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail=f"Invalid month: {month}")

    specs = _month_specs(year, month, 1)
    spec = specs[0]

    reservations = db.query(Reservation).options(
        joinedload(Reservation.share_rel),
        joinedload(Reservation.booked_by_shareholder_rel),
    ).filter(
        Reservation.start_date <= spec["end_date"],
        Reservation.end_date >= spec["start_date"],
        Reservation.status.in_(CALENDAR_VISIBLE_STATUSES),
    ).all()

    return _build_calendar_month(year, month, spec["last_day"], reservations)
