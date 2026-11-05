import json
from datetime import date
from typing import Any


def stay_units(start_date: str, end_date: str) -> int:
    """Return billable stay units (nights or day-use units after normalization)."""
    units = (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days
    return max(1, units)


def parse_guest_nights_json(value: Any) -> list[int] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [int(v) for v in value]
    if isinstance(value, str):
        raw = value.strip()
        if raw == "":
            return []
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise ValueError("guest_nights_json must decode to a list")
        return [int(v) for v in parsed]
    raise ValueError("Invalid guest_nights_json format")


def serialize_guest_nights(guest_nights: list[int] | None) -> str | None:
    if guest_nights is None:
        return None
    return json.dumps([int(v) for v in guest_nights])


def validate_guest_nights(guest_nights: list[int], *, max_units: int) -> list[int]:
    validated: list[int] = []
    for idx, raw in enumerate(guest_nights):
        try:
            nights = int(raw)
        except (TypeError, ValueError):
            raise ValueError(f"Guest {idx + 1}: Guest Nights must be a whole number")
        if nights < 1:
            raise ValueError(f"Guest {idx + 1}: Guest Nights must be at least 1")
        if nights > max_units:
            raise ValueError(f"Guest {idx + 1}: Guest Nights cannot exceed {max_units}")
        validated.append(nights)
    return validated


def normalize_guest_nights_input(
    guest_nights: list[int] | None,
    guest_count: int | None,
    *,
    max_units: int,
) -> list[int]:
    """Canonicalize incoming guest data. Falls back to legacy guest_count when guest_nights absent."""
    if guest_nights is not None:
        return validate_guest_nights(guest_nights, max_units=max_units)

    count = int(guest_count or 0)
    if count < 0:
        raise ValueError("Guest count cannot be negative")
    if count == 0:
        return []
    # Legacy fallback assumes each guest stayed the full duration.
    return [max_units for _ in range(count)]


def parse_guest_nights_query(value: str | None) -> list[int] | None:
    if value is None:
        return None
    raw = value.strip()
    if raw == "":
        return []
    if raw.startswith("["):
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise ValueError("guest_nights must be a list")
        return [int(v) for v in parsed]
    return [int(v) for v in raw.split(",") if v.strip() != ""]


def guest_nights_total(guest_nights: list[int] | None) -> int:
    return sum(guest_nights or [])


def format_guest_nights_summary(guest_nights: list[int] | None) -> str:
    rows = guest_nights or []
    if not rows:
        return "No non-family guests"
    parts = [f"G{i + 1} {n}n" for i, n in enumerate(rows)]
    return "Guests: " + ", ".join(parts)


def get_reservation_guest_nights(reservation: Any) -> list[int]:
    """Read canonical guest nights from a reservation row, synthesizing legacy rows if needed."""
    parsed = parse_guest_nights_json(getattr(reservation, "guest_nights_json", None))
    if parsed is not None:
        return parsed
    count = int(getattr(reservation, "guest_count", 0) or 0)
    if count <= 0:
        return []
    units = stay_units(reservation.start_date, reservation.end_date)
    return [units for _ in range(count)]
