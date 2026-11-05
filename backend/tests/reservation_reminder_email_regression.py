"""
Reservation reminder email regression checks.

Usage:
    cd backend
    python tests/reservation_reminder_email_regression.py
"""

import sys
import types
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from services import email_service


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

    def print(self):
        for line in self.lines:
            print(line)
        print(f"\nSummary: {self.passed + self.failed} checks, {self.passed} passed, {self.failed} failed")


def main():
    result = Result()
    captured: list[dict[str, object]] = []

    original_use_resend = email_service._use_resend
    original_resend = sys.modules.get("resend")

    fake_resend = types.SimpleNamespace()
    fake_resend.api_key = None
    fake_resend.Emails = types.SimpleNamespace(send=lambda payload: captured.append(dict(payload)))
    sys.modules["resend"] = fake_resend
    email_service._use_resend = lambda: True

    try:
        sent = email_service.send_reservation_reminder_email(
            to_emails=["shareholder@example.com", "copilot@example.com"],
            first_name="Demo",
            share_name="Aspen",
            start_date="2026-04-08",
            end_date="2026-04-10",
            cabins=["pine"],
            days_until=3,
            reservation_id=42,
        )

        if sent:
            result.ok("Reservation helper returned success")
        else:
            result.fail("Reservation helper should return True when resend send succeeds")

        if len(captured) == 2:
            result.ok("Reservation helper sent one email per recipient")
        else:
            result.fail(f"Expected 2 sends, found {len(captured)}")

        recipient_sets = [payload.get("to") for payload in captured]
        if recipient_sets == [["shareholder@example.com"], ["copilot@example.com"]]:
            result.ok("Each reservation email targets one visible recipient")
        else:
            result.fail(f"Unexpected reservation recipients: {recipient_sets!r}")

        subjects = [payload.get("subject") for payload in captured]
        if subjects == ["Your booking starts in 3 days - Cabin Booking"] * 2:
            result.ok("Each reservation email keeps the expected subject")
        else:
            result.fail(f"Unexpected reservation subjects: {subjects!r}")

    except Exception as exc:
        result.fail(f"Aborted due to error: {exc}")
    finally:
        email_service._use_resend = original_use_resend
        if original_resend is None:
            sys.modules.pop("resend", None)
        else:
            sys.modules["resend"] = original_resend

    result.print()
    sys.exit(1 if result.failed else 0)


if __name__ == "__main__":
    main()
