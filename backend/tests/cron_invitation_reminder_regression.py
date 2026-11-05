"""
Invitation reminder cron regression checks.

Coverage:
- reminders target pending invitations that are older than the current day
- repeated cron runs on the same day are idempotent per invitation
- reminders resume on the next day for still-pending invitations
- expired invitations are skipped

Usage:
    cd backend
    python tests/cron_invitation_reminder_regression.py
"""

import secrets
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from db.database import SessionLocal, engine
from db.models import AppSetting, Invitation, InvitationReminderLog, Share
from routers.cron import send_invitation_reminders
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


def assert_sent(result: Result, payload: dict, expected: int, label: str) -> bool:
    sent = payload.get("sent")
    if sent != expected:
        result.fail(f"{label}: expected sent={expected}, got {payload}")
        return False
    result.ok(f"{label}: sent={sent}")
    return True


def create_invitation(
    db,
    *,
    share_id: str,
    email: str,
    first_name: str,
    created_at: str,
    expires_at: str,
) -> str:
    invitation = Invitation(
        id=str(uuid.uuid4()),
        email=email,
        first_name=first_name,
        last_name="Reminder",
        phone_number=None,
        token=secrets.token_urlsafe(32),
        share=share_id,
        expires_at=expires_at,
        used_at=None,
        created_at=created_at,
    )
    db.add(invitation)
    db.commit()
    return invitation.id


def count_logs(db, invitation_ids: list[str]) -> int:
    return db.query(InvitationReminderLog).filter(
        InvitationReminderLog.invitation_id.in_(invitation_ids),
    ).count()


def cleanup(db, invitation_ids: list[str]):
    if invitation_ids:
        db.query(InvitationReminderLog).filter(
            InvitationReminderLog.invitation_id.in_(invitation_ids),
        ).delete(synchronize_session=False)
        db.query(Invitation).filter(
            Invitation.id.in_(invitation_ids),
        ).delete(synchronize_session=False)
    set_simulated_date(db, None)


def main():
    InvitationReminderLog.__table__.create(bind=engine, checkfirst=True)
    AppSetting.__table__.create(bind=engine, checkfirst=True)

    result = Result()
    db = SessionLocal()
    invitation_ids: list[str] = []

    try:
        share = db.query(Share).order_by(Share.priority.asc(), Share.share_id.asc()).first()
        if not share:
            raise RuntimeError("No shares found in local database")

        result.section("Create pending invitations")
        invitation_ids.append(create_invitation(
            db,
            share_id=share.share_id,
            email=f"invite-reminder-old-{uuid.uuid4().hex[:8]}@example.com",
            first_name="Older",
            created_at="2099-01-01T09:00:00",
            expires_at="2099-01-10T09:00:00",
        ))
        invitation_ids.append(create_invitation(
            db,
            share_id=share.share_id,
            email=f"invite-reminder-new-{uuid.uuid4().hex[:8]}@example.com",
            first_name="Fresh",
            created_at="2099-01-02T09:00:00",
            expires_at="2099-01-10T09:00:00",
        ))
        result.ok(f"Created 2 pending invitations on share {share.share_id}")

        result.section("Same-day invitations are skipped")
        set_simulated_date(db, date.fromisoformat("2099-01-02"))
        assert_sent(result, send_invitation_reminders(db), 1, "First run only sends older invitation")
        assert_sent(result, send_invitation_reminders(db), 0, "Second same-day run is idempotent")

        result.section("Next day reminders resume")
        set_simulated_date(db, date.fromisoformat("2099-01-03"))
        assert_sent(result, send_invitation_reminders(db), 2, "Next day sends one reminder per pending invitation")
        log_count = count_logs(db, invitation_ids)
        if log_count == 3:
            result.ok("Reminder log count matches daily sends")
        else:
            result.fail(f"Expected 3 reminder log rows, found {log_count}")

        result.section("Expired invitations are skipped")
        set_simulated_date(db, date.fromisoformat("2099-01-11"))
        assert_sent(result, send_invitation_reminders(db), 0, "Expired invitations do not receive reminders")

    except Exception as exc:
        result.fail(f"Aborted due to error: {exc}")
    finally:
        try:
            cleanup(db, invitation_ids)
            result.ok("Cleanup removed test invitations and reminder logs")
        except Exception as cleanup_err:
            result.fail(f"Cleanup failed: {cleanup_err}")
        db.close()

    result.print()
    sys.exit(1 if result.failed else 0)


if __name__ == "__main__":
    main()
