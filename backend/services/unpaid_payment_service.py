import json
from dataclasses import dataclass

from sqlalchemy.orm import Session as DBSession

from db.models import Reservation
from services.email_service import send_unpaid_reservation_payment_email
from services.login_token_service import LoginTokenService


class UnpaidPaymentEmailError(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass
class UnpaidPaymentEmailResult:
    reservation_id: int
    to_email: str
    booker_name: str


def send_unpaid_reservation_payment_link(
    db: DBSession,
    reservation: Reservation,
    frontend_base_url: str,
) -> UnpaidPaymentEmailResult:
    """Email a payment link to the specific shareholder who booked the unpaid reservation."""
    if reservation.status != "unpaid":
        raise UnpaidPaymentEmailError("not_unpaid", "Reservation is not awaiting payment")

    booker = reservation.booked_by_shareholder_rel
    if not booker:
        raise UnpaidPaymentEmailError("no_booker", "Reservation does not have a booked-by shareholder")

    if not booker.email:
        raise UnpaidPaymentEmailError("no_email", "Reservation booker does not have an email address")

    token = LoginTokenService.create_token(db, booker.email, booker.id)
    payment_url = LoginTokenService.get_login_url(
        token.token,
        frontend_base_url,
        next_path=f"/booking/pay?reservation_id={reservation.id}",
    )
    cabins = json.loads(reservation.cabins) if isinstance(reservation.cabins, str) else reservation.cabins
    share_name = reservation.share_rel.share_name if reservation.share_rel else reservation.share

    success = send_unpaid_reservation_payment_email(
        to_email=booker.email,
        first_name=booker.first_name,
        share_name=share_name,
        start_date=reservation.start_date,
        end_date=reservation.end_date,
        cabins=cabins,
        amount_due=reservation.cost or 0.0,
        payment_url=payment_url,
        reservation_id=reservation.id,
    )
    if not success:
        raise UnpaidPaymentEmailError("send_failed", "Failed to send payment email")

    return UnpaidPaymentEmailResult(
        reservation_id=reservation.id,
        to_email=booker.email,
        booker_name=f"{booker.first_name} {booker.last_name}".strip(),
    )
