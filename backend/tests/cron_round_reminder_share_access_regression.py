"""
Round reminder cron regression checks for additional share access.

Coverage:
- round reminders include shareholders who can access a share via shareholder_share_access
- the recipient list is not limited to shareholders whose primary share matches the reminder share

Usage:
    cd backend
    .venv/bin/python tests/cron_round_reminder_share_access_regression.py
"""

import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import func

sys.path.append(str(Path(__file__).resolve().parents[1]))

from db.database import SessionLocal, engine
from db.models import (
    AppSetting,
    BookingRound,
    BookingSeason,
    ReminderLog,
    Share,
    Shareholder,
    ShareholderShareAccess,
)
from routers import cron
from services.date_service import set_simulated_date


class Result:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.lines: list[str] = []

    def ok(self, msg: str):
        self.passed += 1
        self.lines.append(f"  [PASS] {msg}")

    def fail(self, msg: str):
        self.failed += 1
        self.lines.append(f"  [FAIL] {msg}")

    def section(self, msg: str):
        self.lines.append(f"\n=== {msg} ===")

    def print(self):
        for line in self.lines:
            print(line)
        print(f"\nSummary: {self.passed + self.failed} checks, {self.passed} passed, {self.failed} failed")


def first_unused_year(db, start_year: int = 2199) -> int:
    year = start_year
    while db.query(BookingSeason.id).filter(BookingSeason.year == year).first() is not None:
        year += 1
    return year


def cleanup(db, *, share_ids: list[str], shareholder_ids: list[int], year: int):
    db.query(ReminderLog).filter(ReminderLog.share_id.in_(share_ids)).delete(synchronize_session=False)
    db.query(ShareholderShareAccess).filter(
        ShareholderShareAccess.shareholder_id.in_(shareholder_ids)
    ).delete(synchronize_session=False)
    db.query(Shareholder).filter(Shareholder.id.in_(shareholder_ids)).delete(synchronize_session=False)
    db.query(BookingRound).filter(
        BookingRound.season_id.in_(
            db.query(BookingSeason.id).filter(BookingSeason.year == year)
        )
    ).delete(synchronize_session=False)
    db.query(BookingSeason).filter(BookingSeason.year == year).delete(synchronize_session=False)
    db.query(Share).filter(Share.share_id.in_(share_ids)).delete(synchronize_session=False)
    set_simulated_date(db, None)
    db.commit()


def main():
    AppSetting.__table__.create(bind=engine, checkfirst=True)
    ReminderLog.__table__.create(bind=engine, checkfirst=True)
    ShareholderShareAccess.__table__.create(bind=engine, checkfirst=True)

    result = Result()
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    share_ids = [f"test_round_access_g_{suffix}", f"test_round_access_p_{suffix}"]
    shareholder_ids: list[int] = []
    year = 0
    captured: list[dict[str, object]] = []
    original_send = cron.send_booking_window_reminder_email

    try:
        result.section("Create synthetic share access scenario")
        year = first_unused_year(db)
        max_priority = db.query(func.max(Share.priority)).scalar() or 0
        target_priority = int(max_priority) + 10
        primary_priority = target_priority + 1

        primary_share = Share(
            share_id=share_ids[0],
            share_name=f"Round Access G {suffix}",
            priority=primary_priority,
        )
        target_share = Share(
            share_id=share_ids[1],
            share_name=f"Round Access P {suffix}",
            priority=target_priority,
        )
        db.add(primary_share)
        db.add(target_share)
        db.commit()

        shareholder = Shareholder(
            share=primary_share.share_id,
            first_name="Kevin",
            last_name="Access",
            email=f"round-access-{suffix}@example.com",
            phone_number=None,
            password_hash=None,
        )
        db.add(shareholder)
        db.commit()
        db.refresh(shareholder)
        shareholder_ids.append(int(shareholder.id))

        db.add(ShareholderShareAccess(
            shareholder_id=shareholder.id,
            share_id=target_share.share_id,
        ))

        today = date(year, 12, 30)
        tomorrow = today + timedelta(days=1)
        round_start = tomorrow - timedelta(days=target_priority - 1)

        season = BookingSeason(
            year=year,
            prime_season_start=f"{year}-06-01",
            prime_season_end=f"{year}-09-01",
            open_season_start=f"{year}-10-01",
            open_season_end=f"{year}-12-31",
            season_max_nights=18,
            processing_fee_pct=0.04,
            guest_fee_per_day=10.0,
        )
        db.add(season)
        db.commit()
        db.refresh(season)

        db.add(BookingRound(
            season_id=season.id,
            round_number=1,
            start_date=round_start.isoformat(),
            end_date=round_start.isoformat(),
            window_days=1,
            max_reservations=2,
            max_nights=10,
            priority_order="priority",
        ))
        db.commit()

        set_simulated_date(db, today)
        result.ok("Created target share plus additional-share access assignment")

        result.section("Round reminder includes additional-share recipient")

        def fake_send(**payload):
            captured.append(dict(payload))
            return True

        cron.send_booking_window_reminder_email = fake_send
        response = cron.send_round_reminders(db)

        sent = int(response.get("sent", -1))
        if sent == 1:
            result.ok("Cron reported one round reminder sent")
        else:
            result.fail(f"Expected sent=1 for additional-share access reminder, got {response}")

        if len(captured) == 1:
            result.ok("Exactly one reminder email was requested")
        else:
            result.fail(f"Expected exactly one email send, captured {len(captured)} payload(s)")

        recipients = captured[0].get("to_emails") if captured else []
        expected_email = shareholder.email
        if recipients == [expected_email]:
            result.ok("Reminder targeted the shareholder with additional access to the share")
        else:
            result.fail(f"Unexpected reminder recipients: expected {[expected_email]!r}, got {recipients!r}")

    except Exception as exc:
        result.fail(f"Aborted due to error: {exc}")
    finally:
        cron.send_booking_window_reminder_email = original_send
        try:
            if year:
                cleanup(db, share_ids=share_ids, shareholder_ids=shareholder_ids, year=year)
                result.ok("Cleanup removed synthetic shares, shareholder, season, and reminder logs")
        except Exception as cleanup_err:
            result.fail(f"Cleanup failed: {cleanup_err}")
        db.close()

    result.print()
    sys.exit(1 if result.failed else 0)


if __name__ == "__main__":
    main()
