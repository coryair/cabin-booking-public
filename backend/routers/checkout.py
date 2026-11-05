import json
import logging
from datetime import date, datetime
from typing import Literal

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession, joinedload

from config import settings
from db.database import get_db
from db.models import Reservation, Shareholder, ReservationGuestAdjustment
from models.reservation import ReservationCreate
from services.reservation_service import ReservationService
from services.date_service import get_simulated_date
from services.frontend_origin_service import resolve_frontend_base_url
from services.guest_adjustment_service import GuestAdjustmentService
from services.guest_nights_service import (
    format_guest_nights_summary,
    get_reservation_guest_nights,
    guest_nights_total,
    serialize_guest_nights,
)
from services.share_access_service import ShareAccessService
from .auth import ensure_not_viewer, get_current_shareholder
from .reservations import send_reservation_confirmation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["checkout"])


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


class CheckoutResumeRequest(BaseModel):
    reservation_id: int


class CheckoutResumeResponse(BaseModel):
    status: Literal["requires_payment", "paid"]
    reservation_id: int
    checkout_url: str | None = None


class CheckoutReconcileRequest(BaseModel):
    reservation_id: int


class CheckoutReconcileResponse(BaseModel):
    status: Literal["unpaid", "paid"]
    reservation_id: int


class CheckoutCancelRequest(BaseModel):
    reservation_id: int


def _create_checkout_session(reservation: Reservation, customer_email: str, app_url: str):
    """Create a Stripe hosted Checkout session for an existing reservation."""
    total_cents = round((reservation.cost or 0.0) * 100)
    cabins_list = json.loads(reservation.cabins) if isinstance(reservation.cabins, str) else reservation.cabins
    cabins_str = ", ".join(c.title() for c in cabins_list)
    guest_nights = get_reservation_guest_nights(reservation)
    guest_summary = format_guest_nights_summary(guest_nights)
    guest_nights_sum = guest_nights_total(guest_nights)
    stay_units = (date.fromisoformat(reservation.end_date) - date.fromisoformat(reservation.start_date)).days
    if reservation.is_day_use:
        description = f"{cabins_str} - Day Use ({reservation.start_date})"
    else:
        description = (
            f"{cabins_str} - {stay_units} night{'s' if stay_units != 1 else ''} "
            f"({reservation.start_date} to {reservation.end_date})"
        )

    base_cents = round((reservation.base_cost or 0.0) * 100)
    guest_fee_cents = round((reservation.guest_fee or 0.0) * 100)
    processing_fee_cents = round((reservation.processing_fee or 0.0) * 100)
    diff = total_cents - (base_cents + guest_fee_cents + processing_fee_cents)
    processing_fee_cents += diff

    line_items: list[dict] = [{
        "price_data": {
            "currency": "usd",
            "product_data": {
                "name": "Cabin Reservation",
                "description": f"{description}. {guest_summary}",
            },
            "unit_amount": max(base_cents, 0),
        },
        "quantity": 1,
    }]
    if guest_fee_cents > 0:
        line_items.append({
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "Guest Fee",
                    "description": f"{guest_nights_sum} guest-night{'s' if guest_nights_sum != 1 else ''} ({guest_summary})",
                },
                "unit_amount": guest_fee_cents,
            },
            "quantity": 1,
        })
    if processing_fee_cents > 0:
        line_items.append({
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "Processing Fee",
                    "description": "Reservation processing fee",
                },
                "unit_amount": processing_fee_cents,
            },
            "quantity": 1,
        })

    return stripe.checkout.Session.create(
        mode="payment",
        line_items=line_items,
        metadata={
            "reservation_id": str(reservation.id),
            "guest_nights": serialize_guest_nights(guest_nights) or "[]",
        },
        customer_email=customer_email,
        success_url=f"{app_url}/booking/success?reservation_id={reservation.id}",
        cancel_url=f"{app_url}/booking/cancel?reservation_id={reservation.id}",
    )


def _parse_metadata_int(metadata: dict, key: str) -> int | None:
    raw_value = metadata.get(key)
    if raw_value in (None, ""):
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        logger.warning("Stripe webhook metadata %s is not a valid integer: %r", key, raw_value)
        return None


def _normalize_metadata(raw_metadata) -> dict:
    if not raw_metadata:
        return {}
    if isinstance(raw_metadata, dict):
        return raw_metadata
    if hasattr(raw_metadata, "to_dict"):
        try:
            normalized = raw_metadata.to_dict()
            if isinstance(normalized, dict):
                return normalized
        except Exception:
            logger.warning("Failed to convert Stripe metadata object via to_dict()", exc_info=True)
            return {}
    try:
        return dict(raw_metadata)
    except Exception:
        logger.warning("Unsupported Stripe metadata type: %s", type(raw_metadata).__name__)
        return {}


def _mark_reservation_paid(
    db: DBSession,
    reservation: Reservation,
    payment_intent_id: str | None = None,
):
    """Transition a reservation from unpaid -> paid and send confirmation once."""
    if reservation.status != "unpaid":
        return

    reservation.status = "paid"
    if payment_intent_id:
        reservation.stripe_payment_intent_id = payment_intent_id
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to mark reservation %s as paid for payment_intent=%s",
            reservation.id,
            payment_intent_id,
        )
        raise

    shareholder = None
    if reservation.booked_by_shareholder_id:
        shareholder = db.query(Shareholder).filter(
            Shareholder.id == reservation.booked_by_shareholder_id
        ).first()
    if not shareholder:
        shareholder = db.query(Shareholder).filter(
            Shareholder.share == reservation.share
        ).first()
    if shareholder:
        send_reservation_confirmation(db, reservation, shareholder)


@router.post("/checkout")
def create_checkout_session(
    reservation: ReservationCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder),
):
    """Create an unpaid reservation and a Stripe Checkout Session."""
    ensure_not_viewer(current)
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe is not configured")

    stripe.api_key = settings.stripe_secret_key

    try:
        reservation.share = ShareAccessService.resolve_share_selection(
            db, current, reservation.share
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    is_admin = bool(current.is_superadmin) and get_simulated_date(db) is None

    # Create reservation with status="unpaid" to hold the dates
    db_reservation, error = ReservationService.create_reservation(
        db,
        reservation,
        is_admin=is_admin,
        status="unpaid",
        booked_by_shareholder_id=current.id,
    )
    if error:
        raise HTTPException(status_code=400, detail=error)

    frontend_base_url = resolve_frontend_base_url(request)

    try:
        session = _create_checkout_session(db_reservation, current.email, frontend_base_url)
    except stripe.StripeError as e:
        # Stripe session creation failed - delete the held reservation
        db.delete(db_reservation)
        db.commit()
        logger.exception("Stripe checkout session creation failed")
        raise HTTPException(status_code=502, detail=f"Payment service error: {e.user_message or str(e)}")

    # Store the checkout session ID on the reservation
    db_reservation.stripe_checkout_session_id = session.id
    db.commit()

    return {
        "checkout_url": session.url,
        "reservation_id": db_reservation.id,
    }


@router.post("/checkout/resume", response_model=CheckoutResumeResponse)
def resume_checkout_session(
    payload: CheckoutResumeRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder),
):
    """Create a new checkout session for an existing unpaid reservation."""
    ensure_not_viewer(current)
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe is not configured")

    stripe.api_key = settings.stripe_secret_key

    reservation = db.query(Reservation).filter(Reservation.id == payload.reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    is_admin = bool(current.is_admin or current.is_superadmin)
    _require_reservation_owner_or_admin(
        current,
        reservation,
        is_admin,
        "Can only resume checkout for reservations you booked",
    )

    if reservation.status == "paid":
        return CheckoutResumeResponse(status="paid", reservation_id=reservation.id)

    if reservation.status != "unpaid":
        raise HTTPException(status_code=400, detail="Reservation is not awaiting payment")

    frontend_base_url = resolve_frontend_base_url(request)

    try:
        session = _create_checkout_session(reservation, current.email, frontend_base_url)
    except stripe.StripeError as e:
        logger.exception("Stripe checkout session resume failed")
        raise HTTPException(status_code=502, detail=f"Payment service error: {e.user_message or str(e)}")

    reservation.stripe_checkout_session_id = session.id
    reservation.cancelled_at = None
    reservation.cancellation_reason = None
    db.commit()

    return CheckoutResumeResponse(
        status="requires_payment",
        reservation_id=reservation.id,
        checkout_url=session.url,
    )


@router.post("/checkout/reconcile", response_model=CheckoutReconcileResponse)
def reconcile_checkout_status(
    payload: CheckoutReconcileRequest,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder),
):
    """Verify Stripe session state and reconcile reservation payment status."""
    ensure_not_viewer(current)
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe is not configured")

    stripe.api_key = settings.stripe_secret_key

    reservation = db.query(Reservation).options(
        joinedload(Reservation.share_rel)
    ).filter(Reservation.id == payload.reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    is_admin = bool(current.is_admin or current.is_superadmin)
    _require_reservation_owner_or_admin(
        current,
        reservation,
        is_admin,
        "Can only reconcile checkout for reservations you booked",
    )

    if reservation.status == "paid":
        return CheckoutReconcileResponse(status="paid", reservation_id=reservation.id)

    if reservation.status != "unpaid":
        return CheckoutReconcileResponse(status="unpaid", reservation_id=reservation.id)

    if not reservation.stripe_checkout_session_id:
        return CheckoutReconcileResponse(status="unpaid", reservation_id=reservation.id)

    try:
        session = stripe.checkout.Session.retrieve(reservation.stripe_checkout_session_id)
    except stripe.StripeError as e:
        logger.exception("Stripe checkout session reconcile failed")
        raise HTTPException(status_code=502, detail=f"Payment service error: {e.user_message or str(e)}")

    if session.payment_status == "paid":
        payment_intent = session.payment_intent if isinstance(session.payment_intent, str) else None
        _mark_reservation_paid(db, reservation, payment_intent)
        return CheckoutReconcileResponse(status="paid", reservation_id=reservation.id)

    return CheckoutReconcileResponse(status="unpaid", reservation_id=reservation.id)


@router.post("/checkout/cancel")
def cancel_checkout(
    payload: CheckoutCancelRequest,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder),
):
    """Cancel an unpaid reservation and expire its Stripe checkout session."""
    ensure_not_viewer(current)
    reservation = db.query(Reservation).filter(Reservation.id == payload.reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    is_admin = bool(current.is_admin or current.is_superadmin)
    _require_reservation_owner_or_admin(
        current,
        reservation,
        is_admin,
        "Can only cancel reservations you booked",
    )

    if reservation.status != "unpaid":
        raise HTTPException(status_code=400, detail="Only unpaid reservations can be cancelled")

    # Expire the Stripe checkout session so it can't be paid after cancellation
    if reservation.stripe_checkout_session_id and settings.stripe_secret_key:
        stripe.api_key = settings.stripe_secret_key
        try:
            stripe.checkout.Session.expire(reservation.stripe_checkout_session_id)
        except stripe.StripeError:
            logger.warning("Could not expire Stripe session %s", reservation.stripe_checkout_session_id)

    reservation.status = "cancelled"
    reservation.cancelled_at = datetime.utcnow().isoformat()
    reservation.cancellation_reason = (
        "admin" if (is_admin and not _user_owns_reservation(current, reservation)) else "self_service"
    )
    db.commit()
    logger.info("Cancelled unpaid reservation %s", reservation.id)

    return {"status": "cancelled"}


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: DBSession = Depends(get_db)):
    """Handle Stripe webhook events. No session auth - uses signature verification."""
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe is not configured")

    stripe.api_key = settings.stripe_secret_key
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if settings.stripe_webhook_secret:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.stripe_webhook_secret
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid signature")
    else:
        # No webhook secret configured (dev mode) - parse directly
        event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)

    session_id = None
    reservation_id = None

    try:
        if event.type != "checkout.session.completed":
            return {"status": "ignored"}

        session = event.data.object
        session_id = getattr(session, "id", None)
        metadata = _normalize_metadata(session.metadata)
        checkout_kind = metadata.get("checkout_kind")
        reservation_id = metadata.get("reservation_id")
        reservation_pk = _parse_metadata_int(metadata, "reservation_id")
        if reservation_pk is None:
            if reservation_id:
                logger.warning("checkout.session.completed has invalid reservation_id in metadata: %r", reservation_id)
            else:
                logger.warning("checkout.session.completed missing reservation_id in metadata")
            return {"status": "ignored"}

        if checkout_kind == "guest_adjustment":
            adjustment_id = metadata.get("adjustment_id")
            adjustment_pk = _parse_metadata_int(metadata, "adjustment_id")
            if adjustment_pk is None:
                if adjustment_id:
                    logger.warning("guest adjustment checkout has invalid adjustment_id: %r", adjustment_id)
                else:
                    logger.warning("guest adjustment checkout missing adjustment_id")
                return {"status": "ignored"}
            adjustment = db.query(ReservationGuestAdjustment).filter(
                ReservationGuestAdjustment.id == adjustment_pk
            ).first()
            if not adjustment:
                logger.warning("Guest adjustment %s not found for checkout", adjustment_id)
                return {"status": "ignored"}
            reservation = db.query(Reservation).options(
                joinedload(Reservation.share_rel)
            ).filter(Reservation.id == reservation_pk).first()
            if not reservation:
                logger.warning("Reservation %s not found for guest adjustment checkout", reservation_id)
                return {"status": "ignored"}
            if adjustment.status == "pending":
                payment_intent = session.payment_intent if isinstance(session.payment_intent, str) else None
                GuestAdjustmentService.finalize_paid_adjustment(
                    db,
                    reservation,
                    adjustment,
                    payment_intent_id=payment_intent,
                )
                logger.info("Guest adjustment %s applied for reservation %s", adjustment_id, reservation_id)
            return {"status": "ok"}

        reservation = db.query(Reservation).options(
            joinedload(Reservation.share_rel)
        ).filter(Reservation.id == reservation_pk).first()
        if not reservation:
            logger.warning("Reservation %s not found for completed checkout", reservation_id)
            return {"status": "ignored"}

        if reservation.status == "unpaid":
            payment_intent = session.payment_intent if isinstance(session.payment_intent, str) else None
            _mark_reservation_paid(db, reservation, payment_intent)
            logger.info("Reservation %s marked as paid", reservation_id)

        return {"status": "ok"}
    except Exception:
        db.rollback()
        logger.exception(
            "Stripe webhook processing failed for event_id=%s session_id=%s reservation_id=%s",
            getattr(event, "id", None),
            session_id,
            reservation_id,
        )
        raise
