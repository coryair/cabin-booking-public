"""
Cancellation email regression checks.

Verifies:
- cancellation emails go to the reservation booker, not the first shareholder on the share

Usage:
    ./.venv/bin/python backend/tests/cancellation_email_regression.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import routers.reservations as reservations_router  # noqa: E402
from db.models import Share, Shareholder  # noqa: E402


class Result:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.lines: list[str] = []

    def ok(self, msg: str) -> None:
        self.passed += 1
        self.lines.append(f"  [PASS] {msg}")

    def fail(self, msg: str) -> None:
        self.failed += 1
        self.lines.append(f"  [FAIL] {msg}")

    def section(self, msg: str) -> None:
        self.lines.append(f"\n=== {msg} ===")

    def print(self) -> None:
        for line in self.lines:
            print(line)
        print(f"\nSummary: {self.passed + self.failed} checks, {self.passed} passed, {self.failed} failed")


class FakeQuery:
    def __init__(self, db, model, default_result) -> None:
        self._db = db
        self._model = model
        self._result = default_result
        self._filter_key = None

    def filter(self, *args, **_kwargs):
        if args:
            self._filter_key = getattr(getattr(args[0], "left", None), "key", None)
        return self

    def first(self):
        if self._model is Shareholder:
            if self._filter_key == "id":
                return self._db.booked_by_shareholder
            if self._filter_key == "share":
                return self._db.first_shareholder
        return self._result


class FakeDB:
    def __init__(self, share_obj, first_shareholder, booked_by_shareholder) -> None:
        self.share_obj = share_obj
        self.first_shareholder = first_shareholder
        self.booked_by_shareholder = booked_by_shareholder

    def query(self, model):
        if model is Share:
            return FakeQuery(self, model, self.share_obj)
        if model is Shareholder:
            return FakeQuery(self, model, self.first_shareholder)
        raise AssertionError(f"Unexpected query model: {model}")


def assert_equal(result: Result, actual, expected, label: str) -> bool:
    if actual != expected:
        result.fail(f"{label}: expected {expected!r}, got {actual!r}")
        return False
    result.ok(f"{label}: {expected!r}")
    return True


def test_cancellation_email_prefers_booked_by_shareholder(result: Result) -> None:
    result.section("Cancellation emails go to the booked-by shareholder")

    share_obj = SimpleNamespace(share_id="fir", share_name="Fir")
    first_shareholder = SimpleNamespace(
        id=74,
        first_name="Health",
        last_name="Check",
        email="healthcheck@example.com",
    )
    booked_by_shareholder = SimpleNamespace(
        id=80,
        first_name="Demo",
        last_name="Fir Booker",
        email="booker@example.com",
    )
    reservation = SimpleNamespace(
        id=103,
        share="fir",
        booked_by_shareholder_id=80,
        cabins='["pine"]',
        start_date="2026-07-22",
        end_date="2026-07-24",
        processing_fee=8.32,
    )
    current = SimpleNamespace(id=46)
    fake_db = FakeDB(share_obj, first_shareholder, booked_by_shareholder)
    captured: dict[str, object] = {}

    original_sender = reservations_router.send_cancellation_confirmation_email
    reservations_router.send_cancellation_confirmation_email = lambda **kwargs: captured.update(kwargs) or True

    try:
        reservations_router._send_cancellation_email(
            fake_db,
            reservation,
            current,
            {"refund_issued": False, "refund_amount": None},
        )
    finally:
        reservations_router.send_cancellation_confirmation_email = original_sender

    assert_equal(result, captured.get("to_email"), "booker@example.com", "Email recipient")
    assert_equal(result, captured.get("first_name"), "Demo", "Recipient first name")


def main() -> None:
    result = Result()
    try:
        test_cancellation_email_prefers_booked_by_shareholder(result)
    except Exception as exc:
        result.fail(f"Aborted due to error: {exc}")

    result.print()
    sys.exit(1 if result.failed else 0)


if __name__ == "__main__":
    main()
