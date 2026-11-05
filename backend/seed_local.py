"""
Local SQLite seed script.

Usage:
    cd backend && source venv/bin/activate
    python seed_local.py           # seed if empty
    python seed_local.py --force   # wipe and re-seed
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path
from config import settings

import bcrypt

from db.database import engine, Base, SessionLocal
from db.models import (
    Share, Cabin, Shareholder, Rate, BookingSeason, BookingRound,
)
from models.reservation import ReservationCreate
from services.reservation_service import ReservationService

def hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

if settings.environment == "production":
    raise SystemExit("Demo seeding is only allowed in development.")
Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
SEED_PASSWORD = "password" if settings.demo_mode else os.environ.get("SEED_PASSWORD", "password")
SU_PASSWORD = SEED_PASSWORD

force = "--force" in sys.argv

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

shares = [{'share_id': 'alder', 'share_name': 'Alder', 'priority': 1}, {'share_id': 'birch', 'share_name': 'Birch', 'priority': 2}, {'share_id': 'aspen', 'share_name': 'Aspen', 'priority': 3}, {'share_id': 'maple', 'share_name': 'Demo Four', 'priority': 4}, {'share_id': 'oak', 'share_name': 'Oak', 'priority': 5}, {'share_id': 'willow', 'share_name': 'Demo Six', 'priority': 6}, {'share_id': 'spruce', 'share_name': 'Spruce', 'priority': 7}, {'share_id': 'elm', 'share_name': 'Elm', 'priority': 8}, {'share_id': 'fir', 'share_name': 'Fir', 'priority': 9}]

cabins = [
    {"cabin_id": "pine", "cabin_name": "Pine", "description": "Pine Cabin", "max_guests": 10},
    {"cabin_id": "cedar", "cabin_name": "Cedar", "description": "Cedar Cabin", "max_guests": 8},
]

shareholder_defs = [{'share': 'fir', 'first_name': 'Demo', 'last_name': 'Admin', 'email': 'admin@example.com', 'is_admin': 1, 'is_superadmin': 1}, {'share': 'alder', 'first_name': 'Demo', 'last_name': 'Member 1', 'email': 'alder@example.com', 'is_admin': 0, 'is_superadmin': 0}, {'share': 'birch', 'first_name': 'Demo', 'last_name': 'Member 2', 'email': 'birch@example.com', 'is_admin': 0, 'is_superadmin': 0}, {'share': 'aspen', 'first_name': 'Demo', 'last_name': 'Member 3', 'email': 'aspen@example.com', 'is_admin': 0, 'is_superadmin': 0}, {'share': 'maple', 'first_name': 'Demo', 'last_name': 'Member 4', 'email': 'maple@example.com', 'is_admin': 0, 'is_superadmin': 0}, {'share': 'oak', 'first_name': 'Demo', 'last_name': 'Member 5', 'email': 'oak@example.com', 'is_admin': 0, 'is_superadmin': 0}, {'share': 'willow', 'first_name': 'Demo', 'last_name': 'Member 6', 'email': 'willow@example.com', 'is_admin': 0, 'is_superadmin': 0}, {'share': 'spruce', 'first_name': 'Demo', 'last_name': 'Member 7', 'email': 'spruce@example.com', 'is_admin': 0, 'is_superadmin': 0}, {'share': 'elm', 'first_name': 'Demo', 'last_name': 'Member 8', 'email': 'elm@example.com', 'is_admin': 0, 'is_superadmin': 0}, {'share': 'fir', 'first_name': 'Demo', 'last_name': 'Member 9', 'email': 'fir@example.com', 'is_admin': 0, 'is_superadmin': 0}]

demo_reservation_rows = [('Alder', 'Day only', 'Demo Guest 1', 'guest1@example.com'), ('Birch', 'Overnight', 'Demo Guest 2', 'guest2@example.com'), ('Aspen', 'Overnight', 'Demo Guest 3', 'guest3@example.com'), ('Demo Four', 'Day only', 'Demo Guest 4', 'guest4@example.com'), ('Oak', 'Overnight', 'Demo Guest 5', 'guest5@example.com'), ('Demo Six', 'Overnight', 'Demo Guest 6', 'guest6@example.com'), ('Spruce', 'Day only', 'Demo Guest 7', 'guest7@example.com'), ('Elm', 'Overnight', 'Demo Guest 8', 'guest8@example.com'), ('Fir', 'Overnight', 'Demo Guest 9', 'guest9@example.com')]

share_label_to_id = {
    "Alder": "alder",
    "Birch": "birch",
    "Aspen": "aspen",
    "Demo Four": "maple",
    "Oak": "oak",
    "Demo Six": "willow",
    "Spruce": "spruce",
    "Elm": "elm",
    "Fir": "fir",
}

reservation_cabin_pattern = ["pine", "cedar"]
overnight_duration_pattern = [2, 3, 4, 2, 5, 3]
gap_pattern = [1, 2, 1, 3]


def normalize_full_name(name: str) -> str:
    return " ".join(name.split()).title()


def split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else "Shareholder"
    return first_name, last_name


def build_demo_shareholders(rows: list[tuple[str, str, str, str]]) -> list[dict[str, str | int]]:
    by_email: dict[str, dict[str, str]] = {}

    for share_label, _stay_type, raw_name, raw_email in rows:
        email = raw_email.strip().lower()
        full_name = normalize_full_name(raw_name)
        existing = by_email.get(email)
        if existing is None or len(full_name) > len(existing["full_name"]):
            by_email[email] = {
                "share": share_label_to_id[share_label],
                "full_name": full_name,
                "email": email,
            }

    result: list[dict[str, str | int]] = []
    for info in by_email.values():
        first_name, last_name = split_name(info["full_name"])
        result.append({
            "share": info["share"],
            "first_name": first_name,
            "last_name": last_name,
            "email": info["email"],
            "is_admin": 0,
            "is_superadmin": 0,
        })
    return sorted(result, key=lambda row: (str(row["share"]), str(row["last_name"]), str(row["first_name"])))


def build_demo_reservations(rows: list[tuple[str, str, str, str]]) -> list[dict[str, str | bool]]:
    early_next_start = {
        "pine": date(2026, 1, 9),
        "cedar": date(2026, 1, 15),
    }
    showcase_next_start = {
        "pine": date(2026, 4, 6),
        "cedar": date(2026, 4, 9),
    }
    early_reservation_count = 12
    demo_reservations: list[dict[str, str | bool]] = []

    for idx, (share_label, stay_type, raw_name, raw_email) in enumerate(rows):
        share_id = share_label_to_id[share_label]
        email = raw_email.strip().lower()
        cabin = reservation_cabin_pattern[idx % len(reservation_cabin_pattern)]
        is_day_use = stay_type.strip().lower().startswith("day")
        duration_days = 1 if is_day_use else overnight_duration_pattern[idx % len(overnight_duration_pattern)]
        start_map = early_next_start if idx < early_reservation_count else showcase_next_start
        start = start_map[cabin]
        end = start + timedelta(days=duration_days)
        gap_days = gap_pattern[idx % len(gap_pattern)]
        start_map[cabin] = end + timedelta(days=gap_days)

        demo_reservations.append({
            "share": share_id,
            "email": email,
            "cabin": cabin,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "is_day_use": is_day_use,
        })

    return demo_reservations

rates = [
    {"season": "offseason", "nightly_rate": 25.0, "daily_rate": 13.0, "effective_date": "2024-01-01"},
    {"season": "onseason", "nightly_rate": 50.0, "daily_rate": 25.0, "effective_date": "2024-01-01"},
]

season_2026 = {
    "year": 2026,
    "prime_season_start": "2026-05-22",
    "prime_season_end": "2026-09-08",
    "open_season_start": "2026-05-25",
    "open_season_end": "2026-09-07",
    "season_max_nights": 18,
    "processing_fee_pct": 0.04,
    "guest_fee_per_day": 10.0,
}

rounds = [
    {"round_number": 1, "start_date": "2026-04-01", "end_date": "2026-04-18", "window_days": 2, "max_reservations": 2, "max_nights": 10, "priority_order": "priority"},
    {"round_number": 2, "start_date": "2026-04-20", "end_date": "2026-05-07", "window_days": 2, "max_reservations": 1, "max_nights": 10, "priority_order": "reverse"},
    {"round_number": 3, "start_date": "2026-05-10", "end_date": "2026-05-18", "window_days": 1, "max_reservations": 1, "max_nights": 10, "priority_order": "priority"},
]

demo_shareholder_defs = build_demo_shareholders(demo_reservation_rows)
all_shareholder_defs = shareholder_defs + demo_shareholder_defs
demo_reservations = build_demo_reservations(demo_reservation_rows)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

Base.metadata.create_all(bind=engine)

db = SessionLocal()

existing = db.query(Cabin).count()
if existing > 0 and not force:
    print("Database already seeded. Use --force to wipe and re-seed.")
    db.close()
    sys.exit(0)

if existing > 0:
    print("Wiping existing data...")
    from sqlalchemy import text
    for table in [
        "reservation_guest_adjustments",
        "reservations",
        "sessions",
        "login_tokens",
        "invitations",
        "shareholder_share_access",
        "app_settings",
        "booking_rounds",
        "booking_seasons",
        "rates",
        "shareholders",
        "shares",
        "cabins",
    ]:
        db.execute(text(f"DELETE FROM {table}"))
    db.commit()

# Shares
for s in shares:
    db.add(Share(**s))
db.commit()
print(f"Added {len(shares)} shares")

# Cabins
for c in cabins:
    db.add(Cabin(**c))
db.commit()
print(f"Added cabins: {', '.join(c['cabin_id'] for c in cabins)}")

# Shareholders
seed_hash = hash_pw(SEED_PASSWORD)
su_hash = hash_pw(SU_PASSWORD)
for sh in shareholder_defs:
    pw_hash = su_hash if sh["is_superadmin"] else seed_hash
    db.add(Shareholder(
        share=sh["share"],
        first_name=sh["first_name"],
        last_name=sh["last_name"],
        email=sh["email"],
        password_hash=pw_hash,
        is_admin=sh["is_admin"],
        is_superadmin=sh["is_superadmin"],
    ))
db.commit()
for sh in demo_shareholder_defs:
    db.add(Shareholder(
        share=sh["share"],
        first_name=sh["first_name"],
        last_name=sh["last_name"],
        email=sh["email"],
        password_hash=seed_hash,
        is_admin=sh["is_admin"],
        is_superadmin=sh["is_superadmin"],
    ))
db.commit()
print(f"Added {len(all_shareholder_defs)} shareholders ({len(demo_shareholder_defs)} named demo shareholders)")

# Rates
for r in rates:
    db.add(Rate(**r))
db.commit()
print("Added rates for offseason and onseason")

# Booking season
bs = BookingSeason(**season_2026)
db.add(bs)
db.commit()
db.refresh(bs)

for r in rounds:
    db.add(BookingRound(season_id=bs.id, **r))
db.commit()
print("Added 2026 booking season config")

shareholder_ids_by_email = {
    sh.email.lower(): sh.id
    for sh in db.query(Shareholder).all()
}

created_demo_count = 0
created_day_use_count = 0
for spec in demo_reservations:
    booked_by_id = shareholder_ids_by_email[spec["email"]]
    payload = ReservationCreate(
        share=spec["share"],
        guest_count=0,
        start_date=spec["start_date"],
        end_date=spec["end_date"],
        cabins=[spec["cabin"]],
        is_day_use=bool(spec["is_day_use"]),
    )
    reservation, error = ReservationService.create_reservation(
        db,
        payload,
        is_admin=True,
        status="paid",
        booked_by_shareholder_id=booked_by_id,
    )
    if error:
        raise RuntimeError(f"Failed to create demo reservation {spec}: {error}")
    created_demo_count += 1
    if spec["is_day_use"]:
        created_day_use_count += 1

print(f"Added {created_demo_count} demo reservations ({created_day_use_count} day use)")

db.close()
print("\nDatabase seeded successfully!")
print(f"Superadmin login: admin@example.com / {SU_PASSWORD}")
print(f"Family accounts: <share>@example.com / {SEED_PASSWORD}")
