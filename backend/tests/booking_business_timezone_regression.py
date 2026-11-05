"""
Business timezone regression tests for booking date calculations.

Verifies:
- get_today uses the booking business timezone instead of the server-local date
- simulated dates still override the real clock

Usage:
    cd backend && .venv/bin/python tests/booking_business_timezone_regression.py
"""

from __future__ import annotations

import os
import sys
from datetime import date as real_date
from datetime import datetime as real_datetime
from datetime import timezone

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services import date_service  # noqa: E402


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


class FakeDate(real_date):
    @classmethod
    def today(cls) -> "FakeDate":
        # Simulate a server whose local date has already rolled to April 3.
        return cls(2026, 4, 3)


class FakeDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None) -> "FakeDateTime":
        # 2026-04-03 05:30 UTC == 2026-04-02 23:30 in America/Denver.
        utc_now = real_datetime(2026, 4, 3, 5, 30, 0, tzinfo=timezone.utc)
        if tz is None:
            return cls.fromtimestamp(utc_now.timestamp())
        localized = utc_now.astimezone(tz)
        return cls(
            localized.year,
            localized.month,
            localized.day,
            localized.hour,
            localized.minute,
            localized.second,
            localized.microsecond,
            tzinfo=localized.tzinfo,
        )


def main() -> int:
    result = Result()

    original_date = date_service.date
    original_datetime = getattr(date_service, "datetime", None)
    original_get_simulated_date = date_service.get_simulated_date

    try:
        result.section("Business timezone uses America/Denver date")
        date_service.date = FakeDate
        date_service.datetime = FakeDateTime
        date_service.get_simulated_date = lambda db: None

        today = date_service.get_today(None)
        if today == real_date(2026, 4, 2):
            result.ok("get_today keeps booking date on Apr 2 in America/Denver")
        else:
            result.fail(f"Expected 2026-04-02, got {today.isoformat()}")

        result.section("Simulated date remains the top override")
        date_service.get_simulated_date = lambda db: real_date(2026, 4, 10)

        simulated = date_service.get_today(None)
        if simulated == real_date(2026, 4, 10):
            result.ok("get_today returns simulated date when time travel is active")
        else:
            result.fail(f"Expected simulated date 2026-04-10, got {simulated.isoformat()}")

    except Exception as exc:
        result.fail(f"Aborted due to error: {exc}")
    finally:
        date_service.date = original_date
        if original_datetime is not None:
            date_service.datetime = original_datetime
        elif hasattr(date_service, "datetime"):
            delattr(date_service, "datetime")
        date_service.get_simulated_date = original_get_simulated_date

    result.print()
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
