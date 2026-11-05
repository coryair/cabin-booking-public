"""Focused regression checks for lean cancellation-availability alerts.

Usage:
    ./.venv/bin/python backend/tests/cancellation_availability_alert_regression.py
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db.database import Base  # noqa: E402
from db.models import (  # noqa: E402
    AppSetting,
    Cabin,
    Invitation,
    Reservation,
    Share,
    Shareholder,
)
import services.availability_release_service as release_service  # noqa: E402
import services.email_service as email_service  # noqa: E402


class Result:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def check(self, condition: bool, message: str) -> None:
        if condition:
            self.passed += 1
            print(f"  [PASS] {message}")
        else:
            self.failed += 1
            print(f"  [FAIL] {message}")


def make_cancelled_paid(reservation_id: int, *, source_round: str = "open") -> Reservation:
    start = date.today() + timedelta(days=40 + reservation_id)
    return Reservation(
        id=reservation_id,
        share="alpha",
        booked_by_shareholder_id=1,
        guest_count=0,
        guest_nights_json="[]",
        start_date=start.isoformat(),
        end_date=(start + timedelta(days=2)).isoformat(),
        cabins=json.dumps(["pine"]),
        cost=104.0,
        booking_round=source_round,
        base_cost=100.0,
        processing_fee=4.0,
        is_day_use=0,
        status="refunded",
        cancelled_at=f"2026-08-21T12:00:{reservation_id:02d}",
        cancellation_reason="self_service",
    )


def main() -> None:
    result = Result()
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    original_sender = release_service.send_cancellation_availability_email
    captured: list[dict] = []

    try:
        db.add_all([
            Share(share_id="alpha", share_name="Alpha", priority=1),
            Cabin(cabin_id="pine", cabin_name="Pine", max_guests=10),
            Shareholder(
                id=1,
                share="alpha",
                first_name="Subscribed",
                last_name="Owner",
                email="subscribed@example.com",
                cancellation_availability_emails_enabled=1,
            ),
            Shareholder(
                id=2,
                share="alpha",
                first_name="Opted",
                last_name="Out",
                email="optedout@example.com",
                cancellation_availability_emails_enabled=0,
            ),
            Shareholder(
                id=3,
                share="alpha",
                first_name="Also",
                last_name="Subscribed",
                email="also-subscribed@example.com",
                cancellation_availability_emails_enabled=1,
            ),
            Invitation(
                id="pending-invitation",
                email="invited@example.com",
                first_name="Pending",
                last_name="Invitation",
                token="pending-invitation-token",
                share="alpha",
                expires_at=(date.today() + timedelta(days=7)).isoformat(),
            ),
        ])
        db.commit()

        result.check(
            "availability_release_events" not in Base.metadata.tables
            and "availability_release_deliveries" not in Base.metadata.tables,
            "No alert outbox or delivery-history tables remain",
        )

        reservation = make_cancelled_paid(1)
        db.add(reservation)
        db.flush()
        prepared = release_service.prepare_release_alert_if_eligible(
            db,
            reservation,
            previous_status="paid",
            source="self_service",
        )
        db.commit()
        result.check(prepared is not None, "Paid self-service cancellation prepares an alert")

        def successful_sender(**kwargs):
            captured.append(kwargs)
            return True

        release_service.send_cancellation_availability_email = successful_sender
        send_result = release_service.send_prepared_release_alert(db, prepared)
        result.check(
            send_result == {"attempted": 2, "sent": 2, "failed": 0, "skipped_opt_out": 1},
            "One immediate attempt is made for every subscribed shareholder",
        )
        result.check(
            {item["to_email"] for item in captured}
            == {"subscribed@example.com", "also-subscribed@example.com"},
            "Opt-outs and invitations are excluded from private recipient sends",
        )
        result.check(
            len({item["idempotency_key"] for item in captured}) == 2
            and all(item["idempotency_key"].startswith("availability-release/1/") for item in captured),
            "Each recipient gets a stable private provider idempotency key",
        )

        duplicate = release_service.prepare_release_alert_if_eligible(
            db,
            reservation,
            previous_status=reservation.status,
            source="self_service",
        )
        result.check(duplicate is None, "A repeated cancellation state cannot prepare another alert")

        for reservation_id, previous_status, source, source_round in [
            (2, "unpaid", "self_service", "open"),
            (3, "reserved", "self_service", "open"),
            (4, "paid", "admin_refund", "open"),
            (5, "paid", "self_service", "admin"),
        ]:
            excluded = make_cancelled_paid(reservation_id, source_round=source_round)
            db.add(excluded)
            db.flush()
            excluded_alert = release_service.prepare_release_alert_if_eligible(
                db,
                excluded,
                previous_status=previous_status,
                source=source,
            )
            result.check(
                excluded_alert is None,
                f"Excluded cancellation sends nothing ({previous_status}/{source}/{source_round})",
            )
            db.rollback()

        simulated = make_cancelled_paid(6)
        db.add(simulated)
        db.add(AppSetting(key="simulated_date", value=date.today().isoformat()))
        db.flush()
        simulated_alert = release_service.prepare_release_alert_if_eligible(
            db,
            simulated,
            previous_status="paid",
            source="self_service",
        )
        result.check(simulated_alert is None, "Time-travel cancellation sends nothing")
        db.rollback()

        past = make_cancelled_paid(8)
        past.start_date = (date.today() - timedelta(days=4)).isoformat()
        past.end_date = (date.today() - timedelta(days=2)).isoformat()
        db.add(past)
        db.flush()
        past_alert = release_service.prepare_release_alert_if_eligible(
            db,
            past,
            previous_status="paid",
            source="self_service",
        )
        result.check(past_alert is None, "Past released dates send nothing")
        db.rollback()

        rebooked = make_cancelled_paid(7)
        db.add(rebooked)
        db.flush()
        rebooked_alert = release_service.prepare_release_alert_if_eligible(
            db,
            rebooked,
            previous_status="paid",
            source="self_service",
        )
        db.commit()
        db.add(Reservation(
            share="alpha",
            booked_by_shareholder_id=1,
            guest_count=0,
            guest_nights_json="[]",
            start_date=rebooked.start_date,
            end_date=rebooked.end_date,
            cabins=json.dumps(["pine"]),
            cost=104.0,
            booking_round="open",
            base_cost=100.0,
            processing_fee=4.0,
            is_day_use=0,
            status="paid",
        ))
        db.commit()
        capture_count = len(captured)
        stale_result = release_service.send_prepared_release_alert(db, rebooked_alert)
        result.check(
            stale_result["attempted"] == 0 and len(captured) == capture_count,
            "Rebooking before the post-commit send suppresses stale mail",
        )

        failure_case = make_cancelled_paid(80)
        db.add(failure_case)
        db.flush()
        failure_alert = release_service.prepare_release_alert_if_eligible(
            db,
            failure_case,
            previous_status="paid",
            source="self_service",
        )
        db.commit()
        one_shot_attempts = 0

        def one_failure_sender(**_kwargs):
            nonlocal one_shot_attempts
            one_shot_attempts += 1
            return one_shot_attempts != 1

        release_service.send_cancellation_availability_email = one_failure_sender
        failure_result = release_service.send_prepared_release_alert(db, failure_alert)
        result.check(
            failure_result["attempted"] == 2
            and failure_result["failed"] == 1
            and failure_result["sent"] == 1,
            "A recipient failure is logged while later one-shot sends continue",
        )
        result.check(one_shot_attempts == 2, "Failed delivery is not retried")

        token = release_service.create_unsubscribe_token(
            db.query(Shareholder).filter(Shareholder.id == 1).one()
        )
        result.check(
            release_service.validate_unsubscribe_token(db, token).id == 1,
            "Signed unsubscribe token validates",
        )
        result.check(
            release_service.validate_unsubscribe_token(db, token + "tampered") is None,
            "Tampered unsubscribe token is rejected",
        )

        email_calls: list[tuple[dict, dict | None]] = []

        class FakeEmails:
            @staticmethod
            def send(payload, options=None):
                email_calls.append((payload, options))
                return {"id": "email-copy-check"}

        original_use_resend = email_service._use_resend
        original_resend_module = sys.modules.get("resend")
        email_sent = False
        try:
            email_service._use_resend = lambda: True
            sys.modules["resend"] = SimpleNamespace(api_key=None, Emails=FakeEmails)
            email_sent = original_sender(
                to_email="subscribed@example.com",
                first_name="Subscribed",
                released_ranges=[{
                    "cabin_name": "Pine",
                    "start_date": "2027-04-10",
                    "end_date": "2027-04-12",
                    "is_day_use": False,
                }],
                availability_url="https://cabins.example/",
                unsubscribe_url="https://cabins.example/unsubscribe",
                idempotency_key="copy-check",
            )
        finally:
            email_service._use_resend = original_use_resend
            if original_resend_module is None:
                sys.modules.pop("resend", None)
            else:
                sys.modules["resend"] = original_resend_module

        email_payload = email_calls[0][0] if email_calls else {}
        result.check(
            email_sent
            and email_payload.get("subject") == "Dates are available for the Pine cabin",
            "Email subject uses the approved Pine cabin wording",
        )
        result.check(
            "Pine cabin</td>" in email_payload.get("html", ""),
            "Email body uses lowercase cabin in the released-date label",
        )
    finally:
        release_service.send_cancellation_availability_email = original_sender
        db.close()

    print(
        f"\nSummary: {result.passed + result.failed} checks, "
        f"{result.passed} passed, {result.failed} failed"
    )
    sys.exit(1 if result.failed else 0)


if __name__ == "__main__":
    main()
