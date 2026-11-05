from __future__ import annotations

from typing import Any


FEE_POLICY_PCT = 0.04


def _round_money(value: float) -> float:
    return round(float(value or 0.0), 2)


def fee_target_amount(reservation: Any) -> float:
    """
    Canonical processing-fee target to retain for this reservation.
    Source of truth is the charged fee column, with 4% fallback.
    """
    stored = getattr(reservation, "processing_fee", None)
    if stored is not None:
        return _round_money(stored)
    base_cost = _round_money(getattr(reservation, "base_cost", 0.0))
    guest_fee = _round_money(getattr(reservation, "guest_fee", 0.0))
    return _round_money((base_cost + guest_fee) * FEE_POLICY_PCT)


def accumulated_fee_retained(reservation: Any) -> float:
    """
    Amount of fee already retained via prior partial refunds.
    Derived from drift between stored total and (base + guest + fee_target).
    """
    total = _round_money(getattr(reservation, "cost", 0.0))
    base_cost = _round_money(getattr(reservation, "base_cost", 0.0))
    guest_fee = _round_money(getattr(reservation, "guest_fee", 0.0))
    target = fee_target_amount(reservation)
    retained = _round_money(total - (base_cost + guest_fee + target))
    return retained if retained > 0 else 0.0


def remaining_fee_retainable(reservation: Any) -> float:
    target = fee_target_amount(reservation)
    already = accumulated_fee_retained(reservation)
    remaining = _round_money(target - already)
    return remaining if remaining > 0 else 0.0


def clamp_partial_refund_amount(requested_refund: float, reservation: Any) -> dict:
    """
    For partial guest refunds, retain 4% of requested refund, capped so cumulative retained
    fee never exceeds the reservation's fee target.
    """
    requested = _round_money(requested_refund)
    requested = requested if requested > 0 else 0.0
    retain_rule = _round_money(requested * FEE_POLICY_PCT)
    retain_cap = remaining_fee_retainable(reservation)
    retained_this_action = min(retain_rule, retain_cap)
    approved_refund = _round_money(requested - retained_this_action)
    return {
        "requested_refund_amount": requested,
        "approved_refund_amount": approved_refund,
        "processing_fee_retained_this_action": _round_money(retained_this_action),
        "processing_fee_retained_total": _round_money(accumulated_fee_retained(reservation) + retained_this_action),
        "policy_fee_target": fee_target_amount(reservation),
    }


def cancellation_refund_amount(reservation: Any) -> dict:
    """
    For full cancellation, refund everything except the fee target.
    Includes automatic true-up so total retained fee equals target (not more).
    """
    total = _round_money(getattr(reservation, "cost", 0.0))
    target = fee_target_amount(reservation)
    approved = _round_money(total - target)
    if approved < 0:
        approved = 0.0
    return {
        "approved_refund_amount": approved,
        "processing_fee_retained_total": target,
        "policy_fee_target": target,
    }
