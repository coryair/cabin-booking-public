import logging
from datetime import date, datetime

import stripe
from sqlalchemy.orm import Session as DBSession

from config import settings
from db.models import Reservation, ReservationGuestAdjustment
from models.reservation import ReservationStatus
from services.date_service import get_today
from services.fee_policy_service import cancellation_refund_amount
from services.availability_release_service import prepare_release_alert_if_eligible

logger = logging.getLogger(__name__)


def _commit_cancellation(
    db: DBSession,
    reservation: Reservation,
    *,
    previous_status: str,
    source: str,
) -> None:
    prepared_alert = prepare_release_alert_if_eligible(
        db,
        reservation,
        previous_status=previous_status,
        source=source,
    )
    db.commit()
    reservation._availability_release_alert = prepared_alert

REFUND_NOTICE_DAYS = 15
CANCELLATION_NOTICE_STATUSES = {ReservationStatus.reserved, ReservationStatus.paid}


def compute_cancellation_eligibility(reservation: Reservation, today: date) -> dict:
    """
    Determine if a reservation can be cancelled under the shared 15-day policy.
    Returns dict with: eligible, days_until_checkin, status, reason.
    """
    checkin = date.fromisoformat(reservation.start_date)
    days_until = (checkin - today).days

    if days_until >= REFUND_NOTICE_DAYS:
        return {
            "eligible": True,
            "days_until_checkin": days_until,
            "status": reservation.status,
            "reason": (
                f"Eligible for cancellation ({days_until} days notice, {REFUND_NOTICE_DAYS} required)."
            ),
        }

    return {
        "eligible": False,
        "days_until_checkin": days_until,
        "status": reservation.status,
        "reason": (
            f"Cancellations aren't allowed within {REFUND_NOTICE_DAYS} days of check-in "
            f"({days_until} days notice) to keep dates available for others. "
            f"If you'd like someone else to use your dates, coordinate with them directly."
        ),
    }


def compute_refund_eligibility(reservation: Reservation, today: date) -> dict:
    """
    Determine if a paid reservation is eligible for a refund.
    Returns dict with: eligible, days_until_checkin, refund_amount, processing_fee_kept, reason.
    """
    cancellation = compute_cancellation_eligibility(reservation, today)
    days_until = cancellation["days_until_checkin"]

    policy = cancellation_refund_amount(reservation)
    refund_amount = policy["approved_refund_amount"]
    processing_fee = policy["processing_fee_retained_total"]
    requested_refund_amount = round((reservation.base_cost or 0.0) + (reservation.guest_fee or 0.0), 2)

    if cancellation["eligible"]:
        return {
            "eligible": True,
            "cancellation_eligible": True,
            "days_until_checkin": days_until,
            "refund_amount": refund_amount,
            "requested_refund_amount": requested_refund_amount,
            "processing_fee_kept": processing_fee,
            "policy_fee_target": policy["policy_fee_target"],
            "status": reservation.status,
            "reason": (
                f"Eligible for refund ({days_until} days notice, {REFUND_NOTICE_DAYS} required). "
                f"Processing fee of ${processing_fee:.2f} is non-refundable."
            ),
        }
    else:
        return {
            "eligible": False,
            "cancellation_eligible": False,
            "days_until_checkin": days_until,
            "refund_amount": 0.0,
            "requested_refund_amount": requested_refund_amount,
            "processing_fee_kept": processing_fee,
            "policy_fee_target": policy["policy_fee_target"],
            "status": reservation.status,
            "reason": (
                f"Cancellations aren't allowed within {REFUND_NOTICE_DAYS} days of check-in "
                f"({days_until} days notice) to keep dates available for others. "
                f"If you'd like someone else to use your dates, coordinate with them directly."
            ),
        }


def compute_admin_refund_preview(reservation: Reservation, today: date) -> dict:
    """Return the refund amount an admin can issue, plus any required policy override."""
    preview = compute_refund_eligibility(reservation, today)
    override_required = not preview["eligible"]
    if override_required:
        policy = cancellation_refund_amount(reservation)
        preview["refund_amount"] = policy["approved_refund_amount"]
        preview["processing_fee_kept"] = policy["processing_fee_retained_total"]
        preview["policy_fee_target"] = policy["policy_fee_target"]
        preview["cancellation_eligible"] = True
        preview["admin_override"] = True
        preview["reason"] = (
            f"This reservation has {preview['days_until_checkin']} days before check-in, "
            f"which is less than the {REFUND_NOTICE_DAYS}-day refund policy allows. "
            "An admin override is required."
        )
    preview["override_required"] = override_required
    return preview


def _build_stripe_refund_targets(
    db: DBSession,
    reservation: Reservation,
    refund_cents: int,
) -> list[dict]:
    """Allocate a cancellation refund across adjustment charges, then the original charge."""
    remaining_cents = refund_cents
    targets: list[dict] = []
    paid_adjustments = db.query(ReservationGuestAdjustment).filter(
        ReservationGuestAdjustment.reservation_id == reservation.id,
        ReservationGuestAdjustment.action == "collect",
        ReservationGuestAdjustment.status == "paid",
        ReservationGuestAdjustment.stripe_payment_intent_id.isnot(None),
    ).order_by(ReservationGuestAdjustment.id.desc()).all()

    for adjustment in paid_adjustments:
        if remaining_cents <= 0:
            break
        charged_cents = max(0, round(float(adjustment.delta_total or 0.0) * 100))
        amount_cents = min(charged_cents, remaining_cents)
        if amount_cents <= 0:
            continue
        targets.append({
            "payment_intent": adjustment.stripe_payment_intent_id,
            "amount": amount_cents,
            "idempotency_key": f"reservation-refund-{reservation.id}-adjustment-{adjustment.id}",
        })
        remaining_cents -= amount_cents

    if remaining_cents > 0:
        targets.append({
            "payment_intent": reservation.stripe_payment_intent_id,
            "amount": remaining_cents,
            "idempotency_key": f"reservation-refund-{reservation.id}-original",
        })
    return targets


def process_cancellation(
    db: DBSession,
    reservation: Reservation,
    reason: str = "self_service",
    *,
    override_refund_policy: bool = False,
    cancel_on_refund_failure: bool = True,
) -> dict:
    """
    Cancel a reservation and issue a Stripe refund if eligible.
    Handles all statuses: reserved, unpaid, paid.
    Returns dict with: status, refund_issued, refund_amount, message.
    """
    previous_status = reservation.status
    today = get_today(db)
    now_iso = datetime.utcnow().isoformat()

    if reservation.status in ("cancelled", "refunded"):
        return {
            "status": reservation.status,
            "refund_issued": False,
            "refund_amount": None,
            "message": f"Reservation is already {reservation.status}.",
        }

    # Handle reserved (no payment involved)
    if reservation.status == "reserved":
        reservation.status = "cancelled"
        reservation.cancelled_at = now_iso
        reservation.cancellation_reason = reason
        _commit_cancellation(
            db,
            reservation,
            previous_status=previous_status,
            source=reason,
        )
        return {
            "status": "cancelled",
            "refund_issued": False,
            "refund_amount": None,
            "message": "Reservation cancelled.",
        }

    # Handle unpaid - expire Stripe session if exists
    if reservation.status == "unpaid":
        if reservation.stripe_checkout_session_id and settings.stripe_secret_key:
            stripe.api_key = settings.stripe_secret_key
            try:
                stripe.checkout.Session.expire(reservation.stripe_checkout_session_id)
            except stripe.StripeError:
                logger.warning("Could not expire Stripe session %s", reservation.stripe_checkout_session_id)

        reservation.status = "cancelled"
        reservation.cancelled_at = now_iso
        reservation.cancellation_reason = reason
        _commit_cancellation(
            db,
            reservation,
            previous_status=previous_status,
            source=reason,
        )
        return {
            "status": "cancelled",
            "refund_issued": False,
            "refund_amount": None,
            "message": "Unpaid reservation cancelled.",
        }

    # Handle paid - check refund eligibility
    eligibility = compute_refund_eligibility(reservation, today)
    if override_refund_policy and not eligibility["eligible"]:
        policy = cancellation_refund_amount(reservation)
        eligibility.update({
            "eligible": True,
            "refund_amount": policy["approved_refund_amount"],
            "processing_fee_kept": policy["processing_fee_retained_total"],
            "policy_fee_target": policy["policy_fee_target"],
        })

    if eligibility["eligible"] and reservation.stripe_payment_intent_id:
        refund_amount = eligibility["refund_amount"]
        refund_cents = round(refund_amount * 100)

        if settings.stripe_secret_key:
            stripe.api_key = settings.stripe_secret_key
            refund_ids = []
            refunded_cents = 0
            try:
                for target in _build_stripe_refund_targets(db, reservation, refund_cents):
                    refund = stripe.Refund.create(**target)
                    refund_ids.append(refund.id)
                    refunded_cents += target["amount"]
                reservation.status = "refunded"
                reservation.cancelled_at = now_iso
                reservation.refund_amount = refund_amount
                reservation.refunded_at = now_iso
                reservation.stripe_refund_id = ",".join(refund_ids)
                reservation.cancellation_reason = reason
                _commit_cancellation(
                    db,
                    reservation,
                    previous_status=previous_status,
                    source=reason,
                )
                logger.info(
                    "Refunded reservation %d: $%.2f (Stripe refunds %s)",
                    reservation.id, refund_amount, reservation.stripe_refund_id,
                )
                return {
                    "status": "refunded",
                    "refund_issued": True,
                    "refund_amount": refund_amount,
                    "message": (
                        f"Reservation cancelled and ${refund_amount:.2f} refunded. "
                        f"Booking fee retained: ${eligibility['processing_fee_kept']:.2f} (4% policy). "
                        f"Refund will appear in 3-5 business days."
                    ),
                }
            except stripe.StripeError as e:
                logger.exception("Stripe refund failed for reservation %d", reservation.id)
                if refund_ids:
                    partial_refund_amount = round(refunded_cents / 100, 2)
                    return {
                        "status": reservation.status,
                        "refund_issued": True,
                        "refund_amount": partial_refund_amount,
                        "retry_required": True,
                        "message": (
                            f"${partial_refund_amount:.2f} was refunded, but the remaining refund failed: "
                            f"{e.user_message or str(e)}. The reservation was not cancelled. "
                            "Retry the cancellation to complete the remaining refund."
                        ),
                    }
                if not cancel_on_refund_failure:
                    return {
                        "status": reservation.status,
                        "refund_issued": False,
                        "refund_amount": None,
                        "retry_required": True,
                        "message": (
                            f"Refund failed: {e.user_message or str(e)}. "
                            "The reservation was not cancelled."
                        ),
                    }
                # Still cancel, but note the refund failure
                reservation.status = "cancelled"
                reservation.cancelled_at = now_iso
                reservation.cancellation_reason = reason
                _commit_cancellation(
                    db,
                    reservation,
                    previous_status=previous_status,
                    source=reason,
                )
                return {
                    "status": "cancelled",
                    "refund_issued": False,
                    "refund_amount": None,
                    "message": f"Reservation cancelled but refund failed: {e.user_message or str(e)}. Please contact an administrator.",
                }
        else:
            # No Stripe key (dev mode) - mark as refunded anyway
            reservation.status = "refunded"
            reservation.cancelled_at = now_iso
            reservation.refund_amount = refund_amount
            reservation.refunded_at = now_iso
            reservation.cancellation_reason = reason
            _commit_cancellation(
                db,
                reservation,
                previous_status=previous_status,
                source=reason,
            )
            logger.info("DEV: Refunded reservation %d: $%.2f (no Stripe key)", reservation.id, refund_amount)
            return {
                "status": "refunded",
                "refund_issued": True,
                "refund_amount": refund_amount,
                "message": f"Reservation cancelled and ${refund_amount:.2f} refunded (dev mode).",
            }

    # Not eligible for refund, or no payment intent
    reservation.status = "cancelled"
    reservation.cancelled_at = now_iso
    reservation.cancellation_reason = reason
    _commit_cancellation(
        db,
        reservation,
        previous_status=previous_status,
        source=reason,
    )

    if not eligibility["eligible"]:
        return {
            "status": "cancelled",
            "refund_issued": False,
            "refund_amount": None,
            "message": (
                f"Reservation cancelled without refund. "
                f"{eligibility['days_until_checkin']} days notice "
                f"({REFUND_NOTICE_DAYS} required for refund)."
            ),
        }

    return {
        "status": "cancelled",
        "refund_issued": False,
        "refund_amount": None,
        "message": "Reservation cancelled. No payment on file to refund.",
    }
