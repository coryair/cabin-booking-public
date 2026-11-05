import logging
import json
import os
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import DateTime, cast, func, or_, text
from sqlalchemy.orm import Session as DBSession, joinedload

from db.database import get_db
from db.models import (
    BookingSeason,
    Invitation,
    InvitationReminderLog,
    ReminderLog,
    Reservation,
    Share,
    Shareholder,
    ShareholderShareAccess,
)
from services.booking_round_service import BookingRoundService
from services.date_service import get_today
from services.email_service import (
    send_booking_window_reminder_email,
    send_invitation_reminder_email,
    send_reservation_reminder_email,
)
from services.frontend_origin_service import resolve_frontend_base_url
from services.magic_link_service import MagicLinkService
from services.unpaid_payment_service import (
    UnpaidPaymentEmailError,
    send_unpaid_reservation_payment_link,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cron", tags=["cron"])


def verify_cron_secret(authorization: str = Header(None)):
    """Verify the request is from Vercel Cron via CRON_SECRET."""
    cron_secret = os.environ.get("CRON_SECRET")
    if not cron_secret:
        raise HTTPException(status_code=500, detail="CRON_SECRET not configured")
    expected = f"Bearer {cron_secret}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")



def _shareholder_emails_for_share(db: DBSession, share_id: str) -> list[str]:
    rows = db.query(Shareholder.email).outerjoin(
        ShareholderShareAccess,
        ShareholderShareAccess.shareholder_id == Shareholder.id,
    ).filter(
        Shareholder.email.isnot(None),
        or_(
            Shareholder.share == share_id,
            ShareholderShareAccess.share_id == share_id,
        ),
    ).distinct().all()
    return [email for (email,) in rows if email]


def _reservation_recipients(db: DBSession, reservation: Reservation) -> tuple[list[str], str]:
    owner = reservation.booked_by_shareholder_rel
    if owner and owner.email:
        return [owner.email], (owner.first_name or "there")

    shareholders = db.query(Shareholder).filter(Shareholder.share == reservation.share).all()
    emails = [s.email for s in shareholders if s.email]
    first_name = next((s.first_name for s in shareholders if s.first_name), "there")
    return emails, first_name


def _reminder_already_sent(db: DBSession, share_id: str, reminder_name: str, year: int) -> bool:
    return db.query(ReminderLog.id).filter(
        ReminderLog.share_id == share_id,
        ReminderLog.round_name == reminder_name,
        ReminderLog.year == year,
    ).first() is not None


def _record_reminder_sent(db: DBSession, share_id: str, reminder_name: str, year: int) -> None:
    db.add(ReminderLog(share_id=share_id, round_name=reminder_name, year=year))
    db.commit()


def _invitation_reminder_already_sent(db: DBSession, invitation_id: str, reminder_date: str) -> bool:
    return db.query(InvitationReminderLog.id).filter(
        InvitationReminderLog.invitation_id == invitation_id,
        InvitationReminderLog.reminder_date == reminder_date,
    ).first() is not None


def _record_invitation_reminder_sent(db: DBSession, invitation_id: str, reminder_date: str) -> None:
    db.add(InvitationReminderLog(invitation_id=invitation_id, reminder_date=reminder_date))
    db.commit()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(normalized.replace(" ", "T", 1))
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


@router.get("/send-reservation-reminders", dependencies=[Depends(verify_cron_secret)])
def send_reservation_reminders(
    db: DBSession = Depends(get_db),
):
    """Send reservation reminder emails 7 days, 3 days, and day-of."""
    reminder_offsets = {7, 3, 0}
    sent_count = 0
    matched_reservations = 0
    skipped_already_sent = 0
    skipped_no_emails = 0
    skipped_bad_dates = 0
    failed_send = 0

    try:
        today = get_today(db)
        target_dates = {(today + timedelta(days=offset)).isoformat() for offset in reminder_offsets}

        logger.info(
            "cron.send_reservation_reminders.start today=%s target_dates=%s",
            today.isoformat(),
            sorted(target_dates),
        )

        reservations = db.query(Reservation).options(
            joinedload(Reservation.booked_by_shareholder_rel),
            joinedload(Reservation.share_rel),
        ).filter(
            Reservation.status.in_(["reserved", "paid"]),
            Reservation.start_date.in_(target_dates),
        ).all()

        logger.info(
            "cron.send_reservation_reminders.context candidate_reservations=%s",
            len(reservations),
        )

        for reservation in reservations:
            try:
                checkin = date.fromisoformat(reservation.start_date)
            except ValueError:
                skipped_bad_dates += 1
                logger.warning(
                    "cron.send_reservation_reminders.skip_bad_start_date reservation_id=%s start_date=%s",
                    reservation.id,
                    reservation.start_date,
                )
                continue

            days_until = (checkin - today).days
            if days_until not in reminder_offsets:
                continue

            matched_reservations += 1
            reminder_key = f"reservation_{reservation.id}_{days_until}d"

            if _reminder_already_sent(db, reservation.share, reminder_key, checkin.year):
                skipped_already_sent += 1
                logger.info(
                    "cron.send_reservation_reminders.skip_already_sent reservation_id=%s key=%s",
                    reservation.id,
                    reminder_key,
                )
                continue

            emails, first_name = _reservation_recipients(db, reservation)

            if not emails:
                skipped_no_emails += 1
                logger.warning(
                    "cron.send_reservation_reminders.skip_no_emails reservation_id=%s share_id=%s",
                    reservation.id,
                    reservation.share,
                )
                continue

            try:
                cabins_raw = json.loads(reservation.cabins) if isinstance(reservation.cabins, str) else reservation.cabins
            except Exception:
                cabins_raw = []

            cabins = cabins_raw if isinstance(cabins_raw, list) else []
            share_name = reservation.share_rel.share_name if reservation.share_rel else reservation.share

            try:
                success = send_reservation_reminder_email(
                    to_emails=emails,
                    first_name=first_name,
                    share_name=share_name,
                    start_date=reservation.start_date,
                    end_date=reservation.end_date,
                    cabins=cabins,
                    days_until=days_until,
                    reservation_id=reservation.id,
                )
            except Exception:
                failed_send += 1
                logger.exception(
                    "cron.send_reservation_reminders.error reservation_id=%s days_until=%s",
                    reservation.id,
                    days_until,
                )
                continue

            if success:
                try:
                    _record_reminder_sent(db, reservation.share, reminder_key, checkin.year)
                    sent_count += 1
                    logger.info(
                        "cron.send_reservation_reminders.sent reservation_id=%s days_until=%s to=%s",
                        reservation.id,
                        days_until,
                        emails,
                    )
                except Exception:
                    failed_send += 1
                    db.rollback()
                    logger.exception(
                        "cron.send_reservation_reminders.commit_failed reservation_id=%s key=%s",
                        reservation.id,
                        reminder_key,
                    )
            else:
                failed_send += 1
                logger.warning(
                    "cron.send_reservation_reminders.send_failed reservation_id=%s days_until=%s",
                    reservation.id,
                    days_until,
                )

        logger.info(
            "cron.send_reservation_reminders.done sent=%s matched_reservations=%s skipped_already_sent=%s skipped_no_emails=%s skipped_bad_dates=%s failed=%s",
            sent_count,
            matched_reservations,
            skipped_already_sent,
            skipped_no_emails,
            skipped_bad_dates,
            failed_send,
        )
        return {"sent": sent_count}
    except Exception:
        db.rollback()
        logger.exception(
            "cron.send_reservation_reminders.fatal sent=%s matched_reservations=%s skipped_already_sent=%s skipped_no_emails=%s skipped_bad_dates=%s failed=%s",
            sent_count,
            matched_reservations,
            skipped_already_sent,
            skipped_no_emails,
            skipped_bad_dates,
            failed_send,
        )
        raise HTTPException(status_code=500, detail="Failed to run send-reservation-reminders cron")


@router.get("/send-round-reminders", dependencies=[Depends(verify_cron_secret)])
def send_round_reminders(
    db: DBSession = Depends(get_db),
):
    """Send reminder emails to shares whose booking window opens tomorrow."""
    sent_count = 0
    matched_windows = 0
    skipped_already_sent = 0
    skipped_no_emails = 0
    failed_send = 0

    try:
        today = get_today(db)
        tomorrow = today + timedelta(days=1)
        year = today.year

        logger.info(
            "cron.send_round_reminders.start today=%s tomorrow=%s year=%s",
            today.isoformat(),
            tomorrow.isoformat(),
            year,
        )

        season = db.query(BookingSeason).filter(BookingSeason.year == year).first()
        if not season:
            logger.warning(
                "cron.send_round_reminders.no_season year=%s detail=%s",
                year,
                "No booking season configured for this year",
            )
            return {"sent": 0, "detail": "No booking season configured for this year"}

        shares = db.query(Share).filter(Share.priority > 0).all()

        logger.info(
            "cron.send_round_reminders.context season_id=%s rounds=%s candidate_shares=%s",
            season.id,
            len(season.rounds),
            len(shares),
        )

        for rnd in season.rounds:
            round_name = f"round_{rnd.round_number}"
            round_display = f"Round {rnd.round_number}"
            logger.info(
                "cron.send_round_reminders.round.start round=%s display=%s window_days=%s",
                round_name,
                round_display,
                rnd.window_days,
            )

            for share in shares:
                window = BookingRoundService.get_shareholder_booking_window(
                    db, share.share_id, round_name, season
                )
                if not window:
                    continue

                window_start = window[0]
                if window_start != tomorrow:
                    continue

                matched_windows += 1

                # Check idempotency - skip if already sent
                if _reminder_already_sent(db, share.share_id, round_name, year):
                    skipped_already_sent += 1
                    logger.info("Reminder already sent for %s / %s / %d", share.share_id, round_name, year)
                    continue

                # Get email addresses for all shareholders in this share
                emails = _shareholder_emails_for_share(db, share.share_id)
                if not emails:
                    skipped_no_emails += 1
                    logger.warning(
                        "cron.send_round_reminders.skip_no_emails share_id=%s share_name=%s round=%s",
                        share.share_id,
                        share.share_name,
                        round_name,
                    )
                    continue

                try:
                    success = send_booking_window_reminder_email(
                        to_emails=emails,
                        share_name=share.share_name,
                        round_display=round_display,
                        window_start=window[0].isoformat(),
                        window_end=window[1].isoformat(),
                        max_reservations=rnd.max_reservations,
                        max_nights=rnd.max_nights,
                    )
                except Exception:
                    failed_send += 1
                    logger.exception(
                        "cron.send_round_reminders.error share_id=%s round=%s",
                        share.share_id,
                        round_name,
                    )
                    continue

                if success:
                    try:
                        _record_reminder_sent(db, share.share_id, round_name, year)
                        sent_count += 1
                        logger.info("Sent reminder to %s for %s %s", share.share_name, round_display, year)
                    except Exception:
                        failed_send += 1
                        db.rollback()
                        logger.exception(
                            "cron.send_round_reminders.commit_failed share_id=%s round=%s",
                            share.share_id,
                            round_name,
                        )
                else:
                    failed_send += 1
                    logger.warning(
                        "cron.send_round_reminders.send_failed share_id=%s share_name=%s round=%s",
                        share.share_id,
                        share.share_name,
                        round_name,
                    )

        logger.info(
            "cron.send_round_reminders.done sent=%s matched_windows=%s skipped_already_sent=%s skipped_no_emails=%s failed=%s",
            sent_count,
            matched_windows,
            skipped_already_sent,
            skipped_no_emails,
            failed_send,
        )
        return {"sent": sent_count}
    except Exception:
        db.rollback()
        logger.exception(
            "cron.send_round_reminders.fatal sent=%s matched_windows=%s skipped_already_sent=%s skipped_no_emails=%s failed=%s",
            sent_count,
            matched_windows,
            skipped_already_sent,
            skipped_no_emails,
            failed_send,
        )
        raise HTTPException(status_code=500, detail="Failed to run send-round-reminders cron")


@router.get("/send-invitation-reminders", dependencies=[Depends(verify_cron_secret)])
def send_invitation_reminders(
    db: DBSession = Depends(get_db),
):
    """Send daily reminders for pending invitations that are still actionable."""
    sent_count = 0
    matched_invitations = 0
    skipped_already_sent = 0
    skipped_expired = 0
    skipped_same_day = 0
    skipped_bad_dates = 0
    failed_send = 0

    try:
        today = get_today(db)
        reminder_date = today.isoformat()

        logger.info(
            "cron.send_invitation_reminders.start today=%s reminder_date=%s",
            today.isoformat(),
            reminder_date,
        )

        invitations = db.query(Invitation).options(
            joinedload(Invitation.share_rel),
        ).filter(
            Invitation.used_at.is_(None),
        ).order_by(Invitation.created_at.asc()).all()

        logger.info(
            "cron.send_invitation_reminders.context candidate_invitations=%s",
            len(invitations),
        )

        for invitation in invitations:
            matched_invitations += 1

            if _invitation_reminder_already_sent(db, invitation.id, reminder_date):
                skipped_already_sent += 1
                logger.info(
                    "cron.send_invitation_reminders.skip_already_sent invitation_id=%s reminder_date=%s",
                    invitation.id,
                    reminder_date,
                )
                continue

            created_at = _parse_datetime(invitation.created_at)
            expires_at = _parse_datetime(invitation.expires_at)
            if not created_at or not expires_at:
                skipped_bad_dates += 1
                logger.warning(
                    "cron.send_invitation_reminders.skip_bad_dates invitation_id=%s created_at=%s expires_at=%s",
                    invitation.id,
                    invitation.created_at,
                    invitation.expires_at,
                )
                continue

            if created_at.date() >= today:
                skipped_same_day += 1
                logger.info(
                    "cron.send_invitation_reminders.skip_same_day invitation_id=%s created_at=%s",
                    invitation.id,
                    invitation.created_at,
                )
                continue

            expired_today = today == date.today() and expires_at <= datetime.utcnow()
            if expires_at.date() < today or expired_today:
                skipped_expired += 1
                logger.info(
                    "cron.send_invitation_reminders.skip_expired invitation_id=%s expires_at=%s",
                    invitation.id,
                    invitation.expires_at,
                )
                continue

            share_name = invitation.share_rel.share_name if invitation.share_rel else invitation.share
            invite_url = MagicLinkService.get_invite_url(invitation.token)

            try:
                success = send_invitation_reminder_email(
                    to_email=invitation.email,
                    first_name=invitation.first_name,
                    invite_url=invite_url,
                    share_name=share_name,
                    expires_at=invitation.expires_at,
                )
            except Exception:
                failed_send += 1
                logger.exception(
                    "cron.send_invitation_reminders.error invitation_id=%s",
                    invitation.id,
                )
                continue

            if success:
                try:
                    _record_invitation_reminder_sent(db, invitation.id, reminder_date)
                    sent_count += 1
                    logger.info(
                        "cron.send_invitation_reminders.sent invitation_id=%s email=%s",
                        invitation.id,
                        invitation.email,
                    )
                except Exception:
                    failed_send += 1
                    db.rollback()
                    logger.exception(
                        "cron.send_invitation_reminders.commit_failed invitation_id=%s reminder_date=%s",
                        invitation.id,
                        reminder_date,
                    )
            else:
                failed_send += 1
                logger.warning(
                    "cron.send_invitation_reminders.send_failed invitation_id=%s email=%s",
                    invitation.id,
                    invitation.email,
                )

        logger.info(
            "cron.send_invitation_reminders.done sent=%s matched_invitations=%s skipped_already_sent=%s skipped_expired=%s skipped_same_day=%s skipped_bad_dates=%s failed=%s",
            sent_count,
            matched_invitations,
            skipped_already_sent,
            skipped_expired,
            skipped_same_day,
            skipped_bad_dates,
            failed_send,
        )
        return {"sent": sent_count}
    except Exception:
        db.rollback()
        logger.exception(
            "cron.send_invitation_reminders.fatal sent=%s matched_invitations=%s skipped_already_sent=%s skipped_expired=%s skipped_same_day=%s skipped_bad_dates=%s failed=%s",
            sent_count,
            matched_invitations,
            skipped_already_sent,
            skipped_expired,
            skipped_same_day,
            skipped_bad_dates,
            failed_send,
        )
        raise HTTPException(status_code=500, detail="Failed to run send-invitation-reminders cron")


@router.get("/send-unpaid-payment-reminders", dependencies=[Depends(verify_cron_secret)])
def send_unpaid_payment_reminders(
    request: Request,
    db: DBSession = Depends(get_db),
):
    """Send payment links to bookers with unpaid reservations."""
    sent = 0
    skipped_no_booker = 0
    skipped_no_email = 0
    failed = 0
    reservation_ids: list[int] = []

    try:
        frontend_base_url = resolve_frontend_base_url(request)
        reservations = db.query(Reservation).options(
            joinedload(Reservation.share_rel),
            joinedload(Reservation.booked_by_shareholder_rel),
        ).filter(
            Reservation.status == "unpaid",
        ).order_by(Reservation.start_date, Reservation.id).all()

        logger.info(
            "cron.send_unpaid_payment_reminders.start candidates=%s",
            len(reservations),
        )

        for reservation in reservations:
            booker = reservation.booked_by_shareholder_rel
            if not booker:
                skipped_no_booker += 1
                logger.warning(
                    "cron.send_unpaid_payment_reminders.skip_no_booker reservation_id=%s share_id=%s",
                    reservation.id,
                    reservation.share,
                )
                continue

            if not booker.email:
                skipped_no_email += 1
                logger.warning(
                    "cron.send_unpaid_payment_reminders.skip_no_email reservation_id=%s shareholder_id=%s",
                    reservation.id,
                    booker.id,
                )
                continue

            try:
                send_unpaid_reservation_payment_link(db, reservation, frontend_base_url)
                sent += 1
                reservation_ids.append(reservation.id)
                logger.info(
                    "cron.send_unpaid_payment_reminders.sent reservation_id=%s shareholder_id=%s email=%s",
                    reservation.id,
                    booker.id,
                    booker.email,
                )
            except UnpaidPaymentEmailError:
                failed += 1
                logger.warning(
                    "cron.send_unpaid_payment_reminders.send_failed reservation_id=%s shareholder_id=%s",
                    reservation.id,
                    booker.id,
                )

        logger.info(
            "cron.send_unpaid_payment_reminders.done sent=%s skipped_no_booker=%s skipped_no_email=%s failed=%s",
            sent,
            skipped_no_booker,
            skipped_no_email,
            failed,
        )
        return {
            "status": "completed",
            "sent": sent,
            "skipped_no_booker": skipped_no_booker,
            "skipped_no_email": skipped_no_email,
            "failed": failed,
            "reservation_ids": reservation_ids,
        }
    except Exception:
        db.rollback()
        logger.exception(
            "cron.send_unpaid_payment_reminders.fatal sent=%s skipped_no_booker=%s skipped_no_email=%s failed=%s",
            sent,
            skipped_no_booker,
            skipped_no_email,
            failed,
        )
        raise HTTPException(status_code=500, detail="Failed to run send-unpaid-payment-reminders cron")


@router.get("/cleanup-unpaid", dependencies=[Depends(verify_cron_secret)])
def cleanup_unpaid(
    db: DBSession = Depends(get_db),
):
    """Delete unpaid reservations older than the Stripe checkout timeout."""
    from config import settings as _settings

    timeout = _settings.stripe_checkout_timeout_minutes
    deleted_ids: list[int] = []

    try:
        is_pg = "postgresql" in str(db.bind.url) if db.bind else False

        logger.info(
            "cron.cleanup_unpaid.start timeout_minutes=%s db=%s",
            timeout,
            "postgresql" if is_pg else "sqlite",
        )

        if is_pg:
            cutoff_expr = func.now() - text(f"interval '{timeout} minutes'")
            created_at_expr = cast(Reservation.created_at, DateTime(timezone=True))
        else:
            # SQLite: datetime('now', '-N minutes')
            cutoff_expr = func.datetime("now", f"-{timeout} minutes")
            created_at_expr = Reservation.created_at

        stale = db.query(Reservation).filter(
            Reservation.status == "unpaid",
            Reservation.stripe_checkout_session_id.isnot(None),
            Reservation.cancelled_at.is_(None),
            Reservation.cancellation_reason.is_(None),
            Reservation.created_at.isnot(None),
            created_at_expr < cutoff_expr,
        ).all()

        count = len(stale)
        logger.info("cron.cleanup_unpaid.found stale_count=%s", count)
        now_iso = datetime.utcnow().isoformat()
        for res in stale:
            logger.info("Cleaning up stale unpaid reservation %d (created %s)", res.id, res.created_at)
            deleted_ids.append(res.id)
            res.status = "cancelled"
            res.cancelled_at = now_iso
            res.cancellation_reason = "cron_cleanup"

        if count:
            db.commit()
            logger.info("cron.cleanup_unpaid.committed cancelled_count=%s reservation_ids=%s", count, deleted_ids)
        else:
            logger.info("cron.cleanup_unpaid.noop detail=%s", "No stale unpaid reservations found")

        return {"deleted": count}
    except Exception:
        db.rollback()
        logger.exception(
            "cron.cleanup_unpaid.fatal timeout_minutes=%s deleted_ids_pending=%s",
            timeout,
            deleted_ids,
        )
        raise HTTPException(status_code=500, detail="Failed to run cleanup-unpaid cron")
