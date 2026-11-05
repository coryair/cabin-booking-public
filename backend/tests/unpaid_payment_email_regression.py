"""
Regression check for unpaid reservation payment emails.

Usage:
    cd backend && python tests/unpaid_payment_email_regression.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from db.database import Base
from db.models import LoginToken, Reservation, Share, Shareholder
from routers import cron
from routers import reservations as reservations_router
from services import unpaid_payment_service


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def build_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def build_request() -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/api/cron/send-unpaid-payment-reminders",
        "headers": [(b"origin", b"http://localhost:3001")],
        "server": ("testserver", 80),
        "scheme": "http",
    })


def seed(db):
    share = Share(share_id="alder", share_name="Alder", priority=1)
    booker = Shareholder(
        share="alder",
        first_name="Peter",
        last_name="Alder",
        email="peter@example.com",
    )
    admin = Shareholder(
        share="alder",
        first_name="Admin",
        last_name="User",
        email="admin@example.com",
        is_admin=1,
    )
    db.add(share)
    db.add(booker)
    db.add(admin)
    db.commit()
    db.refresh(booker)
    db.refresh(admin)

    unpaid = Reservation(
        id=126,
        share="alder",
        booked_by_shareholder_id=booker.id,
        guest_count=2,
        start_date="2026-05-29",
        end_date="2026-06-01",
        cabins='["pine"]',
        cost=1234.56,
        booking_round="round_3",
        status="unpaid",
    )
    paid = Reservation(
        id=127,
        share="alder",
        booked_by_shareholder_id=booker.id,
        guest_count=2,
        start_date="2026-06-05",
        end_date="2026-06-06",
        cabins='["cedar"]',
        cost=100.0,
        booking_round="round_3",
        status="paid",
    )
    no_booker = Reservation(
        id=128,
        share="alder",
        booked_by_shareholder_id=None,
        guest_count=1,
        start_date="2026-06-10",
        end_date="2026-06-11",
        cabins='["pine"]',
        cost=50.0,
        booking_round="admin",
        status="unpaid",
    )
    db.add_all([unpaid, paid, no_booker])
    db.commit()
    return booker, admin


def main() -> None:
    db = build_session()
    booker, admin = seed(db)
    sent: list[dict] = []

    original_sender = unpaid_payment_service.send_unpaid_reservation_payment_email

    def capture_email(**kwargs):
        sent.append(kwargs)
        return True

    unpaid_payment_service.send_unpaid_reservation_payment_email = capture_email
    try:
        result = cron.send_unpaid_payment_reminders(request=build_request(), db=db)
    finally:
        unpaid_payment_service.send_unpaid_reservation_payment_email = original_sender

    assert_true(result["sent"] == 1, "exactly one unpaid reservation with a booker should be emailed")
    assert_true(result["skipped_no_booker"] == 1, "unpaid reservations without a booker should be skipped")
    assert_true(result["failed"] == 0, "email send should not fail")
    assert_true(result["reservation_ids"] == [126], "only the unpaid booker-owned reservation should be reported sent")

    assert_true(len(sent) == 1, "one email payload should be captured")
    email = sent[0]
    assert_true(email["to_email"] == booker.email, "email should go to the reservation booker")
    assert_true(email["reservation_id"] == 126, "email should target the unpaid reservation")
    assert_true(
        "/auth/verify?token=" in email["payment_url"],
        "payment URL should include a magic-link verification token",
    )
    assert_true(
        "next=%2Fbooking%2Fpay%3Freservation_id%3D126" in email["payment_url"],
        "payment URL should redirect to the reservation payment route after login",
    )

    tokens = db.query(LoginToken).all()
    assert_true(len(tokens) == 1, "one login token should be created for the payment email")
    assert_true(tokens[0].shareholder_id == booker.id, "login token should authenticate the reservation booker")

    unpaid_payment_service.send_unpaid_reservation_payment_email = capture_email
    try:
        direct_result = reservations_router.send_payment_email(
            reservation_id=126,
            request=build_request(),
            db=db,
            current=admin,
        )
    finally:
        unpaid_payment_service.send_unpaid_reservation_payment_email = original_sender
    assert_true(direct_result.sent is True, "targeted admin endpoint should report success")
    assert_true(direct_result.to_email == booker.email, "targeted admin endpoint should email only the booker")
    assert_true(len(sent) == 2, "targeted admin endpoint should send one additional email")
    assert_true(sent[-1]["reservation_id"] == 126, "targeted admin endpoint should target the requested reservation")

    print("unpaid payment email regression passed")


if __name__ == "__main__":
    main()
