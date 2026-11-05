from __future__ import annotations

from datetime import date, datetime, timedelta
import json

from sqlalchemy.orm import Session as DBSession

from db.models import Reservation, ReservationGuestAdjustment
from services.booking_round_service import BookingRoundService
from services.fee_policy_service import clamp_partial_refund_amount, fee_target_amount
from services.guest_nights_service import (
    get_reservation_guest_nights,
    normalize_guest_nights_input,
    parse_guest_nights_json,
    serialize_guest_nights,
    stay_units,
    guest_nights_total,
)
from services.date_service import get_today


GUEST_EDIT_WINDOW_DAYS = 30


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat()


class GuestAdjustmentService:
    @staticmethod
    def edit_deadline(reservation: Reservation) -> str:
        return (date.fromisoformat(reservation.start_date) + timedelta(days=GUEST_EDIT_WINDOW_DAYS)).isoformat()

    @staticmethod
    def check_guest_edit_allowed(db: DBSession, reservation: Reservation) -> tuple[bool, str | None]:
        if reservation.status in ("cancelled", "refunded"):
            return False, f"Reservation is already {reservation.status}"

        today = get_today(db)
        deadline = date.fromisoformat(GuestAdjustmentService.edit_deadline(reservation))
        if today > deadline:
            return False, f"Guest edits are locked after {deadline.isoformat()} (30 days after check-in)."

        return True, None

    @staticmethod
    def build_preview(
        db: DBSession,
        reservation: Reservation,
        requested_guest_nights: list[int],
    ) -> dict:
        allowed, reason = GuestAdjustmentService.check_guest_edit_allowed(db, reservation)
        max_units = stay_units(reservation.start_date, reservation.end_date)
        normalized_requested = normalize_guest_nights_input(
            requested_guest_nights,
            None,
            max_units=max_units,
        )
        current_guest_nights = get_reservation_guest_nights(reservation)

        cabins = json.loads(reservation.cabins) if isinstance(reservation.cabins, str) else reservation.cabins
        is_day_use = bool(reservation.is_day_use)

        current_cost = BookingRoundService.compute_reservation_cost(
            db,
            reservation.start_date,
            reservation.end_date,
            cabins,
            is_day_use=is_day_use,
            guest_nights=current_guest_nights,
        )
        updated_cost = BookingRoundService.compute_reservation_cost(
            db,
            reservation.start_date,
            reservation.end_date,
            cabins,
            is_day_use=is_day_use,
            guest_nights=normalized_requested,
        )

        stored_base_cost = reservation.base_cost if reservation.base_cost is not None else current_cost["base_cost"]
        current_cost["base_cost"] = stored_base_cost
        current_cost["guest_fee"] = reservation.guest_fee or 0.0
        current_cost["processing_fee"] = reservation.processing_fee or current_cost["processing_fee"]
        current_cost["total"] = reservation.cost or current_cost["total"]

        updated_cost["base_cost"] = stored_base_cost
        updated_cost["processing_fee"] = round((stored_base_cost + updated_cost["guest_fee"]) * updated_cost["fee_pct"], 2)
        updated_cost["total"] = round(stored_base_cost + updated_cost["guest_fee"] + updated_cost["processing_fee"], 2)

        delta_guest_fee = round(updated_cost["guest_fee"] - current_cost["guest_fee"], 2)
        delta_processing_fee = round(updated_cost["processing_fee"] - current_cost["processing_fee"], 2)
        delta_total = round(updated_cost["total"] - current_cost["total"], 2)

        action = "none"
        charge_amount = 0.0
        refund_amount = 0.0
        requested_refund_amount = 0.0
        processing_fee_retained = 0.0
        processing_fee_retained_total = 0.0

        if allowed:
            if reservation.status == "paid":
                if delta_total > 0.009:
                    action = "collect"
                    charge_amount = delta_total
                elif delta_guest_fee < -0.009:
                    action = "refund"
                    requested_refund_amount = round(abs(delta_guest_fee), 2)
                    policy = clamp_partial_refund_amount(requested_refund_amount, reservation)
                    refund_amount = policy["approved_refund_amount"]
                    processing_fee_retained = policy["processing_fee_retained_this_action"]
                    processing_fee_retained_total = policy["processing_fee_retained_total"]
                    # Retain fee and reduce total by approved refund amount.
                    updated_cost["processing_fee"] = current_cost["processing_fee"]
                    updated_cost["total"] = round(current_cost["total"] - refund_amount, 2)
                    delta_processing_fee = 0.0
                    delta_total = round(updated_cost["total"] - current_cost["total"], 2)
                elif abs(delta_total) > 0.009:
                    action = "apply"
                else:
                    action = "none"
            else:
                action = "apply" if abs(delta_total) > 0.009 else "none"

        return {
            "reservation_id": reservation.id,
            "allowed": allowed,
            "reason": reason,
            "action": action,
            "edit_deadline": GuestAdjustmentService.edit_deadline(reservation),
            "current_guest_nights": current_guest_nights,
            "updated_guest_nights": normalized_requested,
            "current_guest_count": len(current_guest_nights),
            "updated_guest_count": len(normalized_requested),
            "current_guest_nights_total": guest_nights_total(current_guest_nights),
            "updated_guest_nights_total": guest_nights_total(normalized_requested),
            "current_guest_fee": current_cost["guest_fee"],
            "updated_guest_fee": updated_cost["guest_fee"],
            "current_processing_fee": current_cost["processing_fee"],
            "updated_processing_fee": updated_cost["processing_fee"],
            "current_total": current_cost["total"],
            "updated_total": updated_cost["total"],
            "delta_guest_fee": delta_guest_fee,
            "delta_processing_fee": delta_processing_fee,
            "delta_total": delta_total,
            "charge_amount": charge_amount,
            "refund_amount": refund_amount,
            "requested_refund_amount": requested_refund_amount,
            "processing_fee_retained": processing_fee_retained,
            "processing_fee_retained_total": processing_fee_retained_total,
            "policy_fee_target": fee_target_amount(reservation),
            "reservation_status": reservation.status,
        }

    @staticmethod
    def apply_guest_nights(
        db: DBSession,
        reservation: Reservation,
        guest_nights: list[int],
        *,
        commit: bool = True,
    ) -> Reservation:
        max_units = stay_units(reservation.start_date, reservation.end_date)
        normalized_guest_nights = normalize_guest_nights_input(guest_nights, None, max_units=max_units)
        cabins = json.loads(reservation.cabins) if isinstance(reservation.cabins, str) else reservation.cabins
        cost_info = BookingRoundService.compute_reservation_cost(
            db,
            reservation.start_date,
            reservation.end_date,
            cabins,
            is_day_use=bool(reservation.is_day_use),
            guest_nights=normalized_guest_nights,
        )
        base_cost = reservation.base_cost if reservation.base_cost is not None else cost_info["base_cost"]
        processing_fee = round((base_cost + cost_info["guest_fee"]) * cost_info["fee_pct"], 2)
        total = round(base_cost + cost_info["guest_fee"] + processing_fee, 2)
        reservation.guest_nights_json = serialize_guest_nights(normalized_guest_nights)
        reservation.guest_count = len(normalized_guest_nights)
        reservation.base_cost = base_cost
        reservation.processing_fee = processing_fee
        reservation.guest_fee = cost_info["guest_fee"] if cost_info["guest_fee"] > 0 else None
        reservation.cost = total

        if commit:
            db.commit()
            db.refresh(reservation)
        return reservation

    @staticmethod
    def create_adjustment_record(
        db: DBSession,
        reservation: Reservation,
        preview: dict,
        *,
        created_by_shareholder_id: int | None,
    ) -> ReservationGuestAdjustment:
        adjustment = ReservationGuestAdjustment(
            reservation_id=reservation.id,
            before_guest_nights_json=serialize_guest_nights(preview["current_guest_nights"]) or "[]",
            after_guest_nights_json=serialize_guest_nights(preview["updated_guest_nights"]) or "[]",
            before_guest_fee=preview["current_guest_fee"],
            after_guest_fee=preview["updated_guest_fee"],
            before_processing_fee=preview["current_processing_fee"],
            after_processing_fee=preview["updated_processing_fee"],
            before_total=preview["current_total"],
            after_total=preview["updated_total"],
            delta_guest_fee=preview["delta_guest_fee"],
            delta_processing_fee=preview["delta_processing_fee"],
            delta_total=preview["delta_total"],
            action=preview["action"],
            status="pending",
            created_by_shareholder_id=created_by_shareholder_id,
            updated_at=_utcnow_iso(),
        )
        db.add(adjustment)
        db.commit()
        db.refresh(adjustment)
        return adjustment

    @staticmethod
    def mark_adjustment(
        db: DBSession,
        adjustment: ReservationGuestAdjustment,
        *,
        status: str,
        error_message: str | None = None,
        stripe_checkout_session_id: str | None = None,
        stripe_payment_intent_id: str | None = None,
        stripe_refund_id: str | None = None,
        commit: bool = True,
    ) -> None:
        adjustment.status = status
        adjustment.error_message = error_message
        if stripe_checkout_session_id is not None:
            adjustment.stripe_checkout_session_id = stripe_checkout_session_id
        if stripe_payment_intent_id is not None:
            adjustment.stripe_payment_intent_id = stripe_payment_intent_id
        if stripe_refund_id is not None:
            adjustment.stripe_refund_id = stripe_refund_id
        adjustment.updated_at = _utcnow_iso()
        if commit:
            db.commit()

    @staticmethod
    def pending_adjustments_for_reservation(db: DBSession, reservation_id: int) -> list[ReservationGuestAdjustment]:
        return db.query(ReservationGuestAdjustment).filter(
            ReservationGuestAdjustment.reservation_id == reservation_id,
            ReservationGuestAdjustment.status == "pending",
        ).all()

    @staticmethod
    def finalize_paid_adjustment(
        db: DBSession,
        reservation: Reservation,
        adjustment: ReservationGuestAdjustment,
        *,
        payment_intent_id: str | None = None,
        commit: bool = True,
    ) -> Reservation:
        guest_nights = parse_guest_nights_json(adjustment.after_guest_nights_json) or []
        GuestAdjustmentService.apply_guest_nights(db, reservation, guest_nights, commit=False)
        adjustment.status = "paid"
        if payment_intent_id:
            adjustment.stripe_payment_intent_id = payment_intent_id
        adjustment.updated_at = _utcnow_iso()
        if commit:
            db.commit()
            db.refresh(reservation)
        return reservation
