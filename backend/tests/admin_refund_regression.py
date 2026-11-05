"""
Admin refund API regression checks.

Run:
    backend/.venv/bin/python backend/tests/admin_refund_regression.py
"""

from pathlib import Path
from types import SimpleNamespace
import importlib
import json
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import settings
from db.database import Base, get_db
from db.models import (
    AppSetting,
    Reservation,
    ReservationGuestAdjustment,
    Share,
    Shareholder,
)
from routers.auth import get_current_shareholder


reservations_router = importlib.import_module("routers.reservations")
refund_service = importlib.import_module("services.refund_service")


def assert_status(response, expected: int, label: str) -> None:
    assert response.status_code == expected, (
        f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text}"
    )


def main() -> int:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    seed_db = testing_session()
    seed_db.add(Share(share_id="review", share_name="Review", priority=1))
    admin = Shareholder(
        share="review",
        first_name="Admin",
        last_name="Reviewer",
        email="admin-refund@example.com",
        is_admin=1,
    )
    user = Shareholder(
        share="review",
        first_name="Regular",
        last_name="User",
        email="refund-user@example.com",
    )
    seed_db.add_all([admin, user])
    seed_db.add(AppSetting(key="simulated_date", value="2026-02-20"))
    seed_db.commit()
    seed_db.refresh(admin)
    seed_db.refresh(user)

    current = {"shareholder": admin}

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    def override_current_shareholder():
        return current["shareholder"]

    app = FastAPI()
    app.include_router(reservations_router.router)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_shareholder] = override_current_shareholder
    client = TestClient(app)

    original_stripe_key = settings.stripe_secret_key
    original_refund_create = refund_service.stripe.Refund.create
    original_send_email = reservations_router._send_cancellation_email
    original_logger_disabled = refund_service.logger.disabled
    refund_calls: list[dict] = []

    def create_reservation(
        *,
        start_date: str,
        cost: float = 208.0,
        processing_fee: float = 8.0,
        payment_intent: str,
    ) -> int:
        db = testing_session()
        try:
            reservation = Reservation(
                share="review",
                booked_by_shareholder_id=user.id,
                guest_count=0,
                guest_nights_json="[]",
                start_date=start_date,
                end_date=start_date,
                cabins=json.dumps(["pine"]),
                cost=cost,
                base_cost=cost - processing_fee,
                processing_fee=processing_fee,
                is_day_use=1,
                status="paid",
                stripe_payment_intent_id=payment_intent,
            )
            db.add(reservation)
            db.commit()
            db.refresh(reservation)
            return reservation.id
        finally:
            db.close()

    def get_reservation(reservation_id: int) -> Reservation:
        db = testing_session()
        try:
            reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
            assert reservation is not None
            db.expunge(reservation)
            return reservation
        finally:
            db.close()

    def successful_refund(**kwargs):
        refund_calls.append(kwargs)
        return SimpleNamespace(id=f"re_{kwargs['payment_intent']}")

    try:
        reservations_router._send_cancellation_email = lambda *_args, **_kwargs: None

        permission_id = create_reservation(
            start_date="2026-03-10",
            payment_intent="pi_permission",
        )
        current["shareholder"] = user
        response = client.post(
            f"/api/reservations/{permission_id}/refund",
            json={"override_policy": False},
        )
        assert_status(response, 403, "Non-admin refund")

        current["shareholder"] = admin
        settings.stripe_secret_key = ""
        response = client.post(
            f"/api/reservations/{permission_id}/refund",
            json={"override_policy": False},
        )
        assert_status(response, 500, "Refund without Stripe configuration")
        assert get_reservation(permission_id).status == "paid"

        settings.stripe_secret_key = "sk_test_fake"
        refund_service.stripe.Refund.create = successful_refund

        override_id = create_reservation(
            start_date="2026-03-01",
            payment_intent="pi_override",
        )
        response = client.post(
            f"/api/reservations/{override_id}/refund",
            json={"override_policy": False},
        )
        assert_status(response, 409, "Refund inside policy without override")
        assert get_reservation(override_id).status == "paid"

        response = client.post(
            f"/api/reservations/{override_id}/refund",
            json={"override_policy": True},
        )
        assert_status(response, 200, "Refund inside policy with override")
        assert response.json()["refund_amount"] == 200.0
        assert get_reservation(override_id).status == "refunded"

        pending_id = create_reservation(
            start_date="2026-03-10",
            payment_intent="pi_pending",
        )
        db = testing_session()
        db.add(ReservationGuestAdjustment(
            reservation_id=pending_id,
            before_guest_nights_json="[]",
            after_guest_nights_json="[1]",
            before_guest_fee=0.0,
            after_guest_fee=100.0,
            before_processing_fee=8.0,
            after_processing_fee=12.0,
            before_total=208.0,
            after_total=312.0,
            delta_guest_fee=100.0,
            delta_processing_fee=4.0,
            delta_total=104.0,
            action="collect",
            status="pending",
            stripe_checkout_session_id="cs_pending",
        ))
        db.commit()
        db.close()
        call_count = len(refund_calls)
        response = client.post(
            f"/api/reservations/{pending_id}/refund",
            json={"override_policy": False},
        )
        assert_status(response, 409, "Refund with pending guest checkout")
        assert len(refund_calls) == call_count
        assert get_reservation(pending_id).status == "paid"

        adjusted_id = create_reservation(
            start_date="2026-03-10",
            cost=312.0,
            processing_fee=12.0,
            payment_intent="pi_original",
        )
        db = testing_session()
        paid_adjustment = ReservationGuestAdjustment(
            reservation_id=adjusted_id,
            before_guest_nights_json="[]",
            after_guest_nights_json="[10]",
            before_guest_fee=0.0,
            after_guest_fee=100.0,
            before_processing_fee=8.0,
            after_processing_fee=12.0,
            before_total=208.0,
            after_total=312.0,
            delta_guest_fee=100.0,
            delta_processing_fee=4.0,
            delta_total=104.0,
            action="collect",
            status="paid",
            stripe_payment_intent_id="pi_adjustment",
        )
        db.add(paid_adjustment)
        db.commit()
        db.refresh(paid_adjustment)
        paid_adjustment_id = paid_adjustment.id
        db.close()
        refund_calls.clear()
        response = client.post(
            f"/api/reservations/{adjusted_id}/refund",
            json={"override_policy": False},
        )
        assert_status(response, 200, "Refund across original and adjustment charges")
        assert [(call["payment_intent"], call["amount"]) for call in refund_calls] == [
            ("pi_adjustment", 10400),
            ("pi_original", 19600),
        ]
        assert [call["idempotency_key"] for call in refund_calls] == [
            f"reservation-refund-{adjusted_id}-adjustment-{paid_adjustment_id}",
            f"reservation-refund-{adjusted_id}-original",
        ]
        adjusted = get_reservation(adjusted_id)
        assert adjusted.status == "refunded"
        assert adjusted.refund_amount == 300.0
        assert adjusted.stripe_refund_id == "re_pi_adjustment,re_pi_original"

        partial_id = create_reservation(
            start_date="2026-03-10",
            cost=312.0,
            processing_fee=12.0,
            payment_intent="pi_partial_original",
        )
        db = testing_session()
        partial_adjustment = ReservationGuestAdjustment(
            reservation_id=partial_id,
            before_guest_nights_json="[]",
            after_guest_nights_json="[10]",
            before_guest_fee=0.0,
            after_guest_fee=100.0,
            before_processing_fee=8.0,
            after_processing_fee=12.0,
            before_total=208.0,
            after_total=312.0,
            delta_guest_fee=100.0,
            delta_processing_fee=4.0,
            delta_total=104.0,
            action="collect",
            status="paid",
            stripe_payment_intent_id="pi_partial_adjustment",
        )
        db.add(partial_adjustment)
        db.commit()
        db.refresh(partial_adjustment)
        partial_adjustment_id = partial_adjustment.id
        db.close()

        def fail_original_refund(**kwargs):
            refund_calls.append(kwargs)
            if kwargs["payment_intent"] == "pi_partial_original":
                raise refund_service.stripe.StripeError("test second refund failure")
            return SimpleNamespace(id=f"re_{kwargs['payment_intent']}")

        current["shareholder"] = user
        refund_calls.clear()
        refund_service.stripe.Refund.create = fail_original_refund
        refund_service.logger.disabled = True
        response = client.post(f"/api/reservations/{partial_id}/cancel")
        assert_status(response, 502, "Self-cancellation with a partial refund failure")
        assert "$104.00 was refunded" in response.json()["detail"]
        partial = get_reservation(partial_id)
        assert partial.status == "paid"
        assert partial.cancelled_at is None
        assert partial.stripe_refund_id is None
        assert [call["payment_intent"] for call in refund_calls] == [
            "pi_partial_adjustment",
            "pi_partial_original",
        ]

        refund_calls.clear()
        refund_service.stripe.Refund.create = successful_refund
        response = client.post(f"/api/reservations/{partial_id}/cancel")
        assert_status(response, 200, "Retry after a partial refund failure")
        assert get_reservation(partial_id).status == "refunded"
        assert [call["idempotency_key"] for call in refund_calls] == [
            f"reservation-refund-{partial_id}-adjustment-{partial_adjustment_id}",
            f"reservation-refund-{partial_id}-original",
        ]

        current["shareholder"] = admin
        failure_id = create_reservation(
            start_date="2026-03-10",
            payment_intent="pi_failure",
        )

        def reject_refund(**_kwargs):
            raise refund_service.stripe.StripeError("test refund failure")

        refund_service.stripe.Refund.create = reject_refund
        refund_service.logger.disabled = True
        response = client.post(
            f"/api/reservations/{failure_id}/refund",
            json={"override_policy": False},
        )
        assert_status(response, 502, "Stripe refund failure")
        failed = get_reservation(failure_id)
        assert failed.status == "paid"
        assert failed.cancelled_at is None

    finally:
        settings.stripe_secret_key = original_stripe_key
        refund_service.stripe.Refund.create = original_refund_create
        reservations_router._send_cancellation_email = original_send_email
        refund_service.logger.disabled = original_logger_disabled
        app.dependency_overrides.clear()
        client.close()
        seed_db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

    print("admin refund API regression checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
