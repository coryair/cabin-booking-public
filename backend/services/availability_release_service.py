from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from datetime import date
from urllib.parse import quote

from sqlalchemy.orm import Session as DBSession

from config import settings
from db.models import Cabin, Reservation, Share, Shareholder
from services.booking_round_service import BookingRoundService
from services.date_service import get_simulated_date, get_today
from services.email_service import send_cancellation_availability_email
from services.reservation_service import ReservationService


logger = logging.getLogger(__name__)
UNSUBSCRIBE_SCOPE = "cancellation-availability"


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def create_unsubscribe_token(shareholder: Shareholder) -> str:
    payload = f"{UNSUBSCRIBE_SCOPE}:{shareholder.id}:{shareholder.email.strip().lower()}".encode()
    signature = hmac.new(settings.secret_key.encode(), payload, hashlib.sha256).digest()
    return f"{_b64encode(payload)}.{_b64encode(signature)}"


def validate_unsubscribe_token(db: DBSession, token: str) -> Shareholder | None:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        payload = _b64decode(encoded_payload)
        signature = _b64decode(encoded_signature)
        expected = hmac.new(settings.secret_key.encode(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return None
        scope, raw_id, signed_email = payload.decode().split(":", 2)
        if scope != UNSUBSCRIBE_SCOPE:
            return None
        shareholder = db.query(Shareholder).filter(Shareholder.id == int(raw_id)).first()
        if not shareholder or shareholder.email.strip().lower() != signed_email:
            return None
        return shareholder
    except (ValueError, TypeError, UnicodeDecodeError):
        return None


def unsubscribe_url(shareholder: Shareholder) -> str:
    token = create_unsubscribe_token(shareholder)
    return (
        f"{settings.app_url.rstrip('/')}/notification-preferences/"
        f"cancellation-availability/unsubscribe?token={quote(token, safe='')}"
    )


def _subtract_conflicts(
    start: date,
    end: date,
    conflicts: list[Reservation],
) -> list[tuple[date, date]]:
    blocked: list[tuple[date, date]] = []
    for conflict in conflicts:
        try:
            conflict_start = max(start, date.fromisoformat(conflict.start_date))
            conflict_end = min(end, date.fromisoformat(conflict.end_date))
        except ValueError:
            continue
        if conflict_end > conflict_start:
            blocked.append((conflict_start, conflict_end))

    blocked.sort()
    merged: list[tuple[date, date]] = []
    for block_start, block_end in blocked:
        if not merged or block_start > merged[-1][1]:
            merged.append((block_start, block_end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], block_end))

    available: list[tuple[date, date]] = []
    cursor = start
    for block_start, block_end in merged:
        if block_start > cursor:
            available.append((cursor, block_start))
        cursor = max(cursor, block_end)
    if cursor < end:
        available.append((cursor, end))
    return available


def _bookable_share_ids(db: DBSession) -> list[str]:
    rows = db.query(Share.share_id).join(
        Shareholder,
        Shareholder.share == Share.share_id,
    ).filter(
        Share.priority > 0,
    ).distinct().all()
    return [share_id for (share_id,) in rows]


def _any_share_can_book(
    db: DBSession,
    share_ids: list[str],
    cabin_id: str,
    start: date,
    end: date,
) -> bool:
    for share_id in share_ids:
        eligible, _, _ = BookingRoundService.check_round_eligibility(
            db,
            share_id,
            start.isoformat(),
            end.isoformat(),
            [cabin_id],
        )
        if eligible:
            return True
    return False


def _build_released_ranges(db: DBSession, reservation: Reservation) -> list[dict]:
    try:
        reservation_start = date.fromisoformat(reservation.start_date)
        reservation_end = date.fromisoformat(reservation.end_date)
        cabins = json.loads(reservation.cabins) if isinstance(reservation.cabins, str) else reservation.cabins
    except (ValueError, TypeError, json.JSONDecodeError):
        return []

    today = get_today(db)
    candidate_start = max(today, reservation_start)
    if reservation_end <= candidate_start or not isinstance(cabins, list):
        return []

    cabin_rows = db.query(Cabin).filter(Cabin.cabin_id.in_(cabins)).all()
    cabin_names = {cabin.cabin_id: cabin.cabin_name for cabin in cabin_rows}
    share_ids = _bookable_share_ids(db)
    if not share_ids:
        return []

    released: list[dict] = []
    for cabin_id in cabins:
        if cabin_id not in cabin_names:
            continue
        conflicts = ReservationService.get_conflicting_reservations(
            db,
            [cabin_id],
            candidate_start.isoformat(),
            reservation_end.isoformat(),
        )
        for segment_start, segment_end in _subtract_conflicts(candidate_start, reservation_end, conflicts):
            if not _any_share_can_book(db, share_ids, cabin_id, segment_start, segment_end):
                continue
            released.append({
                "cabin_id": cabin_id,
                "cabin_name": cabin_names[cabin_id],
                "start_date": segment_start.isoformat(),
                "end_date": segment_end.isoformat(),
                "is_day_use": bool(reservation.is_day_use)
                and segment_start == reservation_start
                and segment_end == reservation_end,
            })
    return released


def prepare_release_alert_if_eligible(
    db: DBSession,
    reservation: Reservation,
    *,
    previous_status: str,
    source: str,
) -> dict | None:
    """Build an alert payload inside the cancellation transaction without sending mail."""
    if previous_status != "paid" or source != "self_service":
        return None
    if reservation.booking_round == "admin" or get_simulated_date(db) is not None:
        return None
    if reservation.status not in ("cancelled", "refunded") or not reservation.cancelled_at:
        return None

    db.flush()
    released_ranges = _build_released_ranges(db, reservation)
    if not released_ranges:
        return None
    return {
        "reservation_id": reservation.id,
        "cancelled_at": reservation.cancelled_at,
        "released_ranges": released_ranges,
    }


def _prepared_alert_still_bookable(db: DBSession, prepared: dict) -> bool:
    share_ids = _bookable_share_ids(db)
    if not share_ids:
        return False
    ranges = prepared.get("released_ranges")
    if not isinstance(ranges, list) or not ranges:
        return False
    today = get_today(db)
    for released in ranges:
        try:
            cabin_id = str(released["cabin_id"])
            start = date.fromisoformat(str(released["start_date"]))
            end = date.fromisoformat(str(released["end_date"]))
        except (KeyError, ValueError, TypeError):
            return False
        if end <= max(today, start):
            return False
        conflicts = ReservationService.get_conflicting_reservations(
            db,
            [cabin_id],
            start.isoformat(),
            end.isoformat(),
        )
        if conflicts or not _any_share_can_book(db, share_ids, cabin_id, start, end):
            return False
    return True


def send_prepared_release_alert(db: DBSession, prepared: dict) -> dict[str, int]:
    """Make one immediate post-commit email attempt per subscribed shareholder."""
    counts = {"attempted": 0, "sent": 0, "failed": 0, "skipped_opt_out": 0}
    if not _prepared_alert_still_bookable(db, prepared):
        logger.info(
            "availability_release.suppressed reservation_id=%s reason=no_longer_bookable",
            prepared.get("reservation_id"),
        )
        return counts

    released_ranges = prepared["released_ranges"]
    cancellation_fingerprint = hashlib.sha256(
        str(prepared.get("cancelled_at", "")).encode()
    ).hexdigest()[:16]
    for shareholder in db.query(Shareholder).order_by(Shareholder.id).all():
        if not shareholder.cancellation_availability_emails_enabled:
            counts["skipped_opt_out"] += 1
            continue

        counts["attempted"] += 1
        idempotency_key = (
            f"availability-release/{prepared['reservation_id']}/"
            f"{cancellation_fingerprint}/{shareholder.id}"
        )
        try:
            sent = send_cancellation_availability_email(
                to_email=shareholder.email,
                first_name=shareholder.first_name,
                released_ranges=released_ranges,
                availability_url=settings.app_url.rstrip("/") + "/",
                unsubscribe_url=unsubscribe_url(shareholder),
                idempotency_key=idempotency_key,
            )
        except Exception:
            logger.exception(
                "availability_release.send_failed reservation_id=%s shareholder_id=%s",
                prepared["reservation_id"],
                shareholder.id,
            )
            counts["failed"] += 1
            continue
        if sent:
            counts["sent"] += 1
        else:
            counts["failed"] += 1

    logger.info(
        "availability_release.sent reservation_id=%s attempted=%s sent=%s failed=%s opted_out=%s",
        prepared["reservation_id"],
        counts["attempted"],
        counts["sent"],
        counts["failed"],
        counts["skipped_opt_out"],
    )
    return counts
