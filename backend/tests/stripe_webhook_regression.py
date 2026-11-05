"""
Stripe webhook regression checks.

Verifies:
- malformed Stripe metadata does not crash the webhook
- reservation payment commit failures roll back the DB session

Usage:
    ./.venv/bin/python backend/tests/stripe_webhook_regression.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db.database import get_db  # noqa: E402
from main import app  # noqa: E402
import routers.checkout as checkout  # noqa: E402


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


class ForbiddenDB:
    def query(self, *_args, **_kwargs):
        raise AssertionError("Webhook should ignore malformed metadata before querying the DB")

    def rollback(self) -> None:
        pass


class FailingCommitDB:
    def __init__(self) -> None:
        self.rollback_called = False

    def commit(self) -> None:
        raise RuntimeError("commit failed")

    def rollback(self) -> None:
        self.rollback_called = True

    def query(self, *_args, **_kwargs):
        raise AssertionError("Commit failure test should not query the DB")


class FakeStripeEvent:
    def __init__(self, *, event_type: str, metadata, payment_intent: str | None = None) -> None:
        self.id = "evt_test"
        self.type = event_type
        self.data = SimpleNamespace(
            object=SimpleNamespace(
                id="cs_test_123",
                metadata=metadata,
                payment_intent=payment_intent,
            )
        )


class FakeStripeMetadataObject:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = dict(values)

    def __bool__(self) -> bool:
        return bool(self._values)

    def to_dict(self) -> dict[str, str]:
        return dict(self._values)


def assert_equal(result: Result, actual, expected, label: str) -> bool:
    if actual != expected:
        result.fail(f"{label}: expected {expected!r}, got {actual!r}")
        return False
    result.ok(f"{label}: {expected!r}")
    return True


def run_with_fake_event(metadata) -> tuple[int, str]:
    fake_db = ForbiddenDB()
    original_secret = checkout.settings.stripe_secret_key
    original_webhook_secret = checkout.settings.stripe_webhook_secret
    original_construct_event = checkout.stripe.Webhook.construct_event

    checkout.settings.stripe_secret_key = "sk_test_dummy"
    checkout.settings.stripe_webhook_secret = "whsec_test_dummy"
    checkout.stripe.Webhook.construct_event = lambda *_args, **_kwargs: FakeStripeEvent(
        event_type="checkout.session.completed",
        metadata=metadata,
        payment_intent="pi_test_123",
    )

    app.dependency_overrides[get_db] = lambda: iter([fake_db])

    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/stripe/webhook",
            content=json.dumps({"ignored": True}).encode(),
            headers={"stripe-signature": "t=1,v1=test"},
        )
        return response.status_code, response.text
    finally:
        app.dependency_overrides.clear()
        checkout.settings.stripe_secret_key = original_secret
        checkout.settings.stripe_webhook_secret = original_webhook_secret
        checkout.stripe.Webhook.construct_event = original_construct_event


def test_invalid_reservation_metadata(result: Result) -> None:
    result.section("Malformed reservation metadata is ignored")
    status_code, body = run_with_fake_event({"reservation_id": "not-an-int"})
    assert_equal(result, status_code, 200, "Webhook response status")
    assert_equal(result, body, '{"status":"ignored"}', "Webhook response body")


def test_invalid_adjustment_metadata(result: Result) -> None:
    result.section("Malformed guest adjustment metadata is ignored")
    status_code, body = run_with_fake_event(
        {
            "checkout_kind": "guest_adjustment",
            "reservation_id": "106",
            "adjustment_id": "not-an-int",
        }
    )
    assert_equal(result, status_code, 200, "Webhook response status")
    assert_equal(result, body, '{"status":"ignored"}', "Webhook response body")


def test_stripe_metadata_object_is_supported(result: Result) -> None:
    result.section("Stripe metadata objects without .get are supported")
    status_code, body = run_with_fake_event(
        FakeStripeMetadataObject({"reservation_id": "not-an-int"})
    )
    assert_equal(result, status_code, 200, "Webhook response status")
    assert_equal(result, body, '{"status":"ignored"}', "Webhook response body")


def test_mark_paid_rolls_back_on_commit_failure(result: Result) -> None:
    result.section("Payment commit failures roll back")
    db = FailingCommitDB()
    reservation = SimpleNamespace(
        id=106,
        status="unpaid",
        stripe_payment_intent_id=None,
        booked_by_shareholder_id=None,
        share="spruce",
    )

    try:
        checkout._mark_reservation_paid(db, reservation, "pi_live_123")
        result.fail("Expected _mark_reservation_paid to re-raise commit failure")
    except RuntimeError as exc:
        assert_equal(result, str(exc), "commit failed", "Raised error")

    assert_equal(result, db.rollback_called, True, "Rollback called")


def main() -> None:
    result = Result()
    try:
        test_invalid_reservation_metadata(result)
        test_invalid_adjustment_metadata(result)
        test_stripe_metadata_object_is_supported(result)
        test_mark_paid_rolls_back_on_commit_failure(result)
    except Exception as exc:
        result.fail(f"Aborted due to error: {exc}")

    result.print()
    sys.exit(1 if result.failed else 0)


if __name__ == "__main__":
    main()
