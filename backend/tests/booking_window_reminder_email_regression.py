"""
Booking window reminder email regression checks.

Usage:
    cd backend
    python tests/booking_window_reminder_email_regression.py
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
        sent = email_service.send_booking_window_reminder_email(
            to_emails=["shareholder@example.com", "copilot@example.com"],
            share_name="Aspen",
            round_display="Round 1",
            window_start="2026-04-01",
            window_end="2026-04-02",
            max_reservations=2,
            max_nights=10,
        )

        if sent:
            result.ok("Reminder helper returned success")
        else:
            result.fail("Reminder helper should return True when resend send succeeds")

        if len(captured) == 2:
            result.ok("Booking-window helper sent one email per recipient")
        else:
            result.fail(f"Expected 2 sends, found {len(captured)}")

        recipient_sets = [payload.get("to") for payload in captured]
        if recipient_sets == [["shareholder@example.com"], ["copilot@example.com"]]:
            result.ok("Each booking-window email targets one visible recipient")
        else:
            result.fail(f"Unexpected booking-window recipients: {recipient_sets!r}")

        first_payload = captured[0] if captured else {}
        subject = str(first_payload.get("subject", ""))
        html = str(first_payload.get("html", ""))

        if subject == "Your Booking Window Opens Tomorrow (Round 1)":
            result.ok("Subject includes round display")
        else:
            result.fail(f"Unexpected subject: {subject!r}")

        expected_copy = "Your booking window for the <strong>Aspen</strong> share opens tomorrow for <strong>Round 1</strong>."
        if expected_copy in html:
            result.ok("Body copy reads as a share-specific reminder")
        else:
            result.fail("Body copy did not match the approved share-specific wording")

        if "Sign In" in html:
            result.ok("Reminder HTML includes a sign-in CTA")
        else:
            result.fail("Reminder HTML should include a sign-in CTA")

        if 'href="https://example.com"' in html:
            result.ok("Sign-in CTA points at the generic site login")
        else:
            result.fail("Sign-in CTA should link to https://example.com")

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
