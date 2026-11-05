"""
Unpaid cleanup regression checks.

Verifies:
- stale checkout-created unpaid reservations are cancelled by cleanup
- manual/admin unpaid holds are not cancelled by cleanup

Usage:
    python backend/tests/unpaid_cleanup_regression.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db.database import Base  # noqa: E402
from db.models import Reservation, Share, Shareholder  # noqa: E402
from routers.cron import cleanup_unpaid  # noqa: E402
from routers.reservations import update_reservation  # noqa: E402


class Result:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def ok(self, msg: str) -> None:
        self.passed += 1
        print(f"  [PASS] {msg}")

    def fail(self, msg: str) -> None:
        self.failed += 1
        print(f"  [FAIL] {msg}")


def make_reservation(
    reservation_id: int,
    *,
    checkout_session_id: str | None,
    cancelled_at: str | None,
    cancellation_reason: str | None,
) -> Reservation:
    return Reservation(
        id=reservation_id,
        share="fir",
        booked_by_shareholder_id=None,
        guest_count=0,
        guest_nights_json="[]",
        start_date="2026-05-20",
        end_date="2026-05-21",
        cabins=json.dumps(["pine"]),
        cost=52.0,
        booking_round="round_3",
        base_cost=50.0,
        processing_fee=2.0,
        is_day_use=0,
        guest_fee=None,
        status="unpaid",
        stripe_checkout_session_id=checkout_session_id,
        stripe_payment_intent_id=None,
        created_at="2000-01-01 00:00:00",
        cancelled_at=cancelled_at,
        cancellation_reason=cancellation_reason,
    )


def main() -> None:
    result = Result()
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        db.add(Share(share_id="fir", share_name="Fir", priority=1))
        db.add(Shareholder(
            id=1,
            share="fir",
            first_name="Admin",
            last_name="User",
            email="admin@example.com",
            is_admin=1,
            is_superadmin=1,
        ))
        db.add(make_reservation(1, checkout_session_id="cs_stale", cancelled_at=None, cancellation_reason=None))
        db.add(make_reservation(2, checkout_session_id="cs_old_cancelled", cancelled_at="2026-05-19T10:00:00", cancellation_reason="self_service"))
        db.add(make_reservation(3, checkout_session_id=None, cancelled_at=None, cancellation_reason=None))
        db.add(make_reservation(4, checkout_session_id="cs_old_cancelled_no_reason", cancelled_at="2026-05-19T10:00:00", cancellation_reason=None))
        db.add(make_reservation(5, checkout_session_id="cs_paid", cancelled_at=None, cancellation_reason=None))
        db.flush()
        paid_row = db.query(Reservation).filter(Reservation.id == 5).one()
        paid_row.status = "paid"
        paid_row.stripe_payment_intent_id = "pi_paid"
        paid_row.refund_amount = 12.34
        paid_row.refunded_at = "2026-05-19T11:00:00"
        paid_row.stripe_refund_id = "re_paid"
        db.commit()

        response = cleanup_unpaid(db=db)
        if response == {"deleted": 1}:
            result.ok("Cleanup cancelled exactly one stale checkout hold")
        else:
            result.fail(f"Expected deleted=1, got {response}")

        rows = {row.id: row for row in db.query(Reservation).order_by(Reservation.id).all()}
        if rows[1].status == "cancelled" and rows[1].cancellation_reason == "cron_cleanup":
            result.ok("Stale checkout-created unpaid reservation was cancelled")
        else:
            result.fail(f"Reservation 1 was not cleaned up correctly: {rows[1].status}, {rows[1].cancellation_reason}")

        if rows[2].status == "unpaid" and rows[2].cancellation_reason == "self_service":
            result.ok("Manual resurrected unpaid hold with old cancellation reason survived")
        else:
            result.fail(f"Reservation 2 should have stayed unpaid, got {rows[2].status}")

        if rows[3].status == "unpaid":
            result.ok("Manual unpaid hold without checkout session survived")
        else:
            result.fail(f"Reservation 3 should have stayed unpaid, got {rows[3].status}")

        if rows[4].status == "unpaid":
            result.ok("Manual resurrected unpaid hold with old cancellation timestamp survived")
        else:
            result.fail(f"Reservation 4 should have stayed unpaid, got {rows[4].status}")

        update_reservation(
            5,
            {"status": "unpaid"},
            db=db,
            current=db.query(Shareholder).filter(Shareholder.id == 1).one(),
        )
        repaired = db.query(Reservation).filter(Reservation.id == 5).one()
        if (
            repaired.status == "unpaid"
            and repaired.stripe_checkout_session_id is None
            and repaired.stripe_payment_intent_id == "pi_paid"
            and repaired.refund_amount == 12.34
            and repaired.refunded_at == "2026-05-19T11:00:00"
            and repaired.stripe_refund_id == "re_paid"
        ):
            result.ok("Admin unpaid repair preserves paid/refund audit fields")
        else:
            result.fail("Admin unpaid repair did not preserve paid/refund audit fields")
    finally:
        db.close()

    print(f"\nSummary: {result.passed + result.failed} checks, {result.passed} passed, {result.failed} failed")
    sys.exit(1 if result.failed else 0)


if __name__ == "__main__":
    main()
