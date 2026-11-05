import logging
from datetime import date
from html import escape

from config import settings

logger = logging.getLogger(__name__)


def _use_resend() -> bool:
    """Only send real emails in production with a configured API key."""
    return settings.environment == "production" and bool(settings.resend_api_key)


def send_invitation_email(to_email: str, invite_url: str, share_name: str) -> bool:
    """Send an invitation email. In dev mode, prints to console."""
    if not _use_resend():
        logger.info(
            "\n[DEV] Invitation for %s\n"
            "  Share: %s\n"
            "  URL: %s\n",
            to_email, share_name, invite_url,
        )
        print(
            f"\n[DEV] Invitation for {to_email}\n"
            f"  Share: {share_name}\n"
            f"  URL: {invite_url}\n"
        )
        return True

    import resend

    resend.api_key = settings.resend_api_key

    try:
        resend.Emails.send({
            "from": settings.resend_from_email,
            "to": [to_email],
            "subject": "You've been invited to the Cabin Booking",
            "html": (
                f"<div style=\"font-family:Georgia,serif;max-width:600px;margin:0 auto;\">"
                f"<div style=\"background:#1B3A2D;padding:24px;text-align:center;"
                f"border:3px double #D4A843;border-radius:8px;margin-bottom:24px;\">"
                f"<div style=\"color:#D4A843;font-size:14px;letter-spacing:3px;"
                f"text-transform:uppercase;margin-bottom:4px;\">Cabin Booking</div>"
                f"</div>"
                f"<h2 style=\"color:#1B3A2D;text-align:center;margin-bottom:16px;\">"
                f"You've been invited to the Cabin Booking</h2>"
                f"<p style=\"text-align:center;\">You've been invited to join as a member of the "
                f"<strong>{share_name}</strong> share.</p>"
                f"<p style=\"text-align:center;\"><a href=\"{invite_url}\" style=\"display:inline-block;"
                f"padding:12px 24px;background:#D4A843;color:#1B3A2D;text-decoration:none;"
                f"border-radius:4px;font-weight:bold;\">Accept Invitation</a></p>"
                f"<p style=\"text-align:center;\">This invitation expires in "
                f"{settings.invitation_expire_days} days.</p>"
                f"<p style=\"color:#888;font-size:12px;text-align:center;\">"
                f"If you didn't expect this, you can ignore this email.</p>"
                f"</div>"
            ),
        })
        return True
    except Exception:
        logger.exception("Failed to send invitation email to %s", to_email)
        return False


def send_invitation_reminder_email(
    to_email: str,
    first_name: str,
    invite_url: str,
    share_name: str,
    expires_at: str,
) -> bool:
    """Send a reminder to accept a pending invitation."""
    expires_on = expires_at.split("T", 1)[0] if expires_at else "soon"

    if not _use_resend():
        logger.info(
            "\n[DEV] Invitation reminder for %s (%s)\n"
            "  Share: %s\n"
            "  Expires: %s\n"
            "  URL: %s\n",
            to_email,
            first_name,
            share_name,
            expires_on,
            invite_url,
        )
        print(
            f"\n[DEV] Invitation reminder for {to_email} ({first_name})\n"
            f"  Share: {share_name}\n"
            f"  Expires: {expires_on}\n"
            f"  URL: {invite_url}\n"
        )
        return True

    import resend

    resend.api_key = settings.resend_api_key

    try:
        resend.Emails.send({
            "from": settings.resend_from_email,
            "to": [to_email],
            "subject": "Reminder: accept your Cabin Booking invitation",
            "html": (
                f"<div style=\"font-family:Georgia,serif;max-width:600px;margin:0 auto;\">"
                f"<div style=\"background:#1B3A2D;padding:24px;text-align:center;"
                f"border:3px double #D4A843;border-radius:8px;margin-bottom:24px;\">"
                f"<div style=\"color:#D4A843;font-size:14px;letter-spacing:3px;"
                f"text-transform:uppercase;margin-bottom:4px;\">Cabin Booking</div>"
                f"</div>"
                f"<h2 style=\"color:#1B3A2D;text-align:center;margin-bottom:16px;\">"
                f"Your invitation is still waiting</h2>"
                f"<p style=\"text-align:center;\">Hi {first_name or 'there'},</p>"
                f"<p style=\"text-align:center;\">You still have a pending invitation to join the "
                f"<strong>{share_name}</strong> share on Cabin Booking.</p>"
                f"<p style=\"text-align:center;\">"
                f"<a href=\"{invite_url}\" style=\"display:inline-block;padding:12px 24px;"
                f"background:#D4A843;color:#1B3A2D;text-decoration:none;border-radius:4px;"
                f"font-weight:bold;\">Accept Invitation</a></p>"
                f"<p style=\"text-align:center;\">This invitation expires on <strong>{expires_on}</strong>.</p>"
                f"<p style=\"color:#888;font-size:12px;text-align:center;\">"
                f"This is an automated reminder from Cabin Booking. If you were not expecting it, "
                f"you can ignore this email.</p>"
                f"</div>"
            ),
        })
        return True
    except Exception:
        logger.exception("Failed to send invitation reminder to %s", to_email)
        return False


def _round_display_name(booking_round: str | None) -> str:
    """Human-readable booking round name."""
    mapping = {
        "round_1": "Round 1",
        "round_2": "Round 2",
        "round_3": "Round 3",
        "open": "Open Season",
        "offseason": "Off-Season",
        "admin": "Admin",
    }
    return mapping.get(booking_round or "", booking_round or "N/A")


def send_booking_confirmation_email(
    to_email: str,
    first_name: str,
    start_date: str,
    end_date: str,
    cabins: list[str],
    is_day_use: bool,
    base_cost: float,
    guest_fee: float,
    processing_fee: float,
    total_cost: float,
    *,
    reservation_id: int | None = None,
    share_name: str | None = None,
    booking_round: str | None = None,
    nights: int | None = None,
    guest_count: int = 0,
    nights_used: int | None = None,
    nights_remaining: int | None = None,
    season_max_nights: int | None = None,
    is_prime_season: bool = True,
    admin_contacts: list[dict] | None = None,
) -> bool:
    """Send a booking confirmation email. In dev mode, prints to console."""
    cabin_str = ", ".join(c.title() for c in cabins)
    booking_type = "Day Use" if is_day_use else "Overnight"
    round_name = _round_display_name(booking_round)

    if not _use_resend():
        logger.info(
            "\n[DEV] Booking confirmation for %s (%s)\n"
            "  Confirmation #: %s\n"
            "  Share: %s\n"
            "  Booked during: %s\n"
            "  Dates: %s\n"
            "  Cabins: %s\n"
            "  Type: %s\n"
            "  Nights: %s | Guests: %s\n"
            "  Base cost: $%.2f\n"
            "  Guest fee: $%.2f\n"
            "  Processing fee: $%.2f\n"
            "  Total: $%.2f\n"
            "  Season nights: %s of %s used (%s remaining)%s\n"
            "  Admin contacts: %s\n",
            to_email, first_name,
            reservation_id or "N/A",
            share_name or "N/A",
            round_name,
            start_date if is_day_use else f"{start_date} to {end_date}",
            cabin_str, booking_type,
            nights or 0, guest_count,
            base_cost, guest_fee, processing_fee, total_cost,
            nights_used or 0, season_max_nights or "?", nights_remaining or 0,
            "" if is_prime_season else " (off-season, no cap)",
            ", ".join(f"{c['name']} <{c['email']}>" for c in (admin_contacts or [])) or "none",
        )
        print(
            f"\n[DEV] Booking confirmation for {to_email} ({first_name})\n"
            f"  Confirmation #: {reservation_id or 'N/A'}\n"
            f"  Share: {share_name or 'N/A'}\n"
            f"  Booked during: {round_name}\n"
            f"  Dates: {start_date if is_day_use else f'{start_date} to {end_date}'}\n"
            f"  Cabins: {cabin_str}\n"
            f"  Type: {booking_type}\n"
            f"  Nights: {nights or 0} | Guests: {guest_count}\n"
            f"  Base cost: ${base_cost:.2f}\n"
            f"  Guest fee: ${guest_fee:.2f}\n"
            f"  Processing fee: ${processing_fee:.2f}\n"
            f"  Total: ${total_cost:.2f}\n"
            f"  Season nights: {nights_used or 0} of {season_max_nights or '?'} used"
            f" ({nights_remaining or 0} remaining)"
            f"{'  (off-season, no cap)' if not is_prime_season else ''}\n"
            f"  Admin contacts: {', '.join(f'{c['name']} <{c['email']}>' for c in (admin_contacts or [])) or 'none'}\n"
            f"  Check-in: 1:00 PM | Check-out: 12:00 PM\n"
        )
        return True

    import resend

    resend.api_key = settings.resend_api_key

    td = "padding:8px 12px;border-bottom:1px solid #eee;"

    # Build details rows
    details_rows = ""
    if reservation_id:
        details_rows += (
            f"<tr><td style=\"{td}font-weight:bold;\">Confirmation #</td>"
            f"<td style=\"{td}font-weight:bold;color:#1B3A2D;\">{reservation_id}</td></tr>"
        )
    if share_name:
        details_rows += (
            f"<tr><td style=\"{td}font-weight:bold;\">Share</td>"
            f"<td style=\"{td}\">{share_name}</td></tr>"
        )
    details_rows += (
        f"<tr><td style=\"{td}font-weight:bold;\">Dates</td>"
        f"<td style=\"{td}\">{start_date if is_day_use else f'{start_date} to {end_date}'}</td></tr>"
        f"<tr><td style=\"{td}font-weight:bold;\">Cabin(s)</td>"
        f"<td style=\"{td}\">{cabin_str}</td></tr>"
        f"<tr><td style=\"{td}font-weight:bold;\">Type</td>"
        f"<td style=\"{td}\">{booking_type}</td></tr>"
    )
    if nights is not None:
        details_rows += (
            f"<tr><td style=\"{td}font-weight:bold;\">Nights</td>"
            f"<td style=\"{td}\">{nights}</td></tr>"
        )
    if guest_count > 0:
        details_rows += (
            f"<tr><td style=\"{td}font-weight:bold;\">Guests</td>"
            f"<td style=\"{td}\">{guest_count}</td></tr>"
        )
    details_rows += (
        f"<tr><td style=\"{td}font-weight:bold;\">Booked During</td>"
        f"<td style=\"{td}\">{round_name}</td></tr>"
    )
    # Build cost breakdown rows
    cost_rows = (
        f"<tr><td style=\"{td}\">Base cost</td>"
        f"<td style=\"{td}text-align:right;\">${base_cost:.2f}</td></tr>"
    )
    if guest_fee:
        cost_rows += (
            f"<tr><td style=\"{td}\">Guest fee</td>"
            f"<td style=\"{td}text-align:right;\">${guest_fee:.2f}</td></tr>"
        )
    cost_rows += (
        f"<tr><td style=\"{td}\">Processing fee</td>"
        f"<td style=\"{td}text-align:right;\">${processing_fee:.2f}</td></tr>"
        f"<tr><td style=\"padding:8px 12px;font-weight:bold;\">Total</td>"
        f"<td style=\"padding:8px 12px;text-align:right;font-weight:bold;\">${total_cost:.2f}</td></tr>"
    )

    # Season nights summary (only for prime season)
    season_nights_html = ""
    if is_prime_season and nights_used is not None and season_max_nights:
        season_nights_html = (
            f"<div style=\"background:#f8f5ed;border-radius:6px;padding:12px 16px;margin:16px 0;"
            f"border:1px solid #e8e0cc;text-align:center;\">"
            f"<span style=\"font-size:14px;color:#555;\">"
            f"{nights_used} of {season_max_nights} prime season nights used"
            f" &mdash; <strong>{nights_remaining}</strong> remaining"
            f"</span></div>"
        )

    # Check-in/out callout
    checkin_html = (
        f"<div style=\"background:#1B3A2D;border-radius:6px;padding:16px;margin:20px 0;"
        f"color:#F5EDD8;\">"
        f"<div style=\"font-weight:bold;font-size:15px;letter-spacing:1px;"
        f"text-transform:uppercase;margin-bottom:8px;color:#D4A843;\">Check-in &amp; Check-out</div>"
        f"<table style=\"width:100%;color:#F5EDD8;font-size:15px;\">"
        f"<tr><td style=\"padding:4px 0;\"><strong>Check-in:</strong> 1:00 PM</td></tr>"
        f"<tr><td style=\"padding:4px 0;\"><strong>Check-out:</strong> 12:00 PM</td></tr>"
        f"</table>"
        f"</div>"
    )

    try:
        resend.Emails.send({
            "from": settings.resend_from_email,
            "to": [to_email],
            "subject": f"Booking Confirmed #{reservation_id or ''} - Cabin Booking",
            "html": (
                f"<div style=\"font-family:Georgia,serif;font-size:17px;line-height:1.6;"
                f"color:#333;max-width:600px;margin:0 auto;\">"
                # Header banner
                f"<div style=\"background:#1B3A2D;padding:24px;text-align:center;"
                f"border:3px double #D4A843;border-radius:8px;margin-bottom:24px;\">"
                f"<div style=\"color:#D4A843;font-size:14px;letter-spacing:3px;"
                f"text-transform:uppercase;margin-bottom:4px;\">Cabin Booking</div>"
                f"</div>"
                # Greeting
                f"<h2 style=\"color:#1B3A2D;margin-bottom:8px;\">Hi {first_name},</h2>"
                f"<p>Your reservation has been confirmed! Here are the details:</p>"
                # Details table
                f"<table style=\"width:100%;border-collapse:collapse;margin:16px 0;\">"
                f"{details_rows}"
                f"</table>"
                # Cost breakdown
                f"<h3 style=\"color:#1B3A2D;margin-top:24px;\">Cost Breakdown</h3>"
                f"<table style=\"width:100%;border-collapse:collapse;margin:8px 0;\">"
                f"{cost_rows}"
                f"</table>"
                # Season nights
                f"{season_nights_html}"
                # Check-in/out
                f"{checkin_html}"
                # Footer
                f"<p style=\"margin-top:24px;\">View and manage your reservations at "
                f"<a href=\"https://example.com\" style=\"color:#D4A843;\">example.com</a>.</p>"
                f"</div>"
            ),
        })
        return True
    except Exception:
        logger.exception("Failed to send booking confirmation email to %s", to_email)
        return False


def send_cancellation_confirmation_email(
    to_email: str,
    first_name: str,
    start_date: str,
    end_date: str,
    cabins: list[str],
    *,
    reservation_id: int | None = None,
    share_name: str | None = None,
    nights: int | None = None,
    refund_issued: bool = False,
    refund_amount: float | None = None,
    processing_fee: float = 0.0,
) -> bool:
    """Send a cancellation confirmation email. In dev mode, prints to console."""
    cabin_str = ", ".join(c.title() for c in cabins)

    refund_line = "No refund issued."
    if refund_issued and refund_amount:
        refund_line = (
            f"Refund of ${refund_amount:.2f} issued. "
            f"Processing fee of ${processing_fee:.2f} retained (non-refundable). "
            f"Allow 3-5 business days for the refund to appear."
        )

    if not _use_resend():
        logger.info(
            "\n[DEV] Cancellation confirmation for %s (%s)\n"
            "  Confirmation #: %s\n"
            "  Share: %s\n"
            "  Dates: %s to %s\n"
            "  Cabins: %s\n"
            "  Nights: %s\n"
            "  Refund: %s\n",
            to_email, first_name,
            reservation_id or "N/A",
            share_name or "N/A",
            start_date, end_date,
            cabin_str,
            nights or 0,
            refund_line,
        )
        print(
            f"\n[DEV] Cancellation confirmation for {to_email} ({first_name})\n"
            f"  Confirmation #: {reservation_id or 'N/A'}\n"
            f"  Share: {share_name or 'N/A'}\n"
            f"  Dates: {start_date} to {end_date}\n"
            f"  Cabins: {cabin_str}\n"
            f"  Nights: {nights or 0}\n"
            f"  Refund: {refund_line}\n"
        )
        return True

    import resend

    resend.api_key = settings.resend_api_key

    td = "padding:8px 12px;border-bottom:1px solid #eee;"

    details_rows = ""
    if reservation_id:
        details_rows += (
            f"<tr><td style=\"{td}font-weight:bold;\">Confirmation #</td>"
            f"<td style=\"{td}\">{reservation_id}</td></tr>"
        )
    if share_name:
        details_rows += (
            f"<tr><td style=\"{td}font-weight:bold;\">Share</td>"
            f"<td style=\"{td}\">{share_name}</td></tr>"
        )
    details_rows += (
        f"<tr><td style=\"{td}font-weight:bold;\">Dates</td>"
        f"<td style=\"{td}\">{start_date} to {end_date}</td></tr>"
        f"<tr><td style=\"{td}font-weight:bold;\">Cabin(s)</td>"
        f"<td style=\"{td}\">{cabin_str}</td></tr>"
    )
    if nights is not None:
        details_rows += (
            f"<tr><td style=\"{td}font-weight:bold;\">Nights</td>"
            f"<td style=\"{td}\">{nights}</td></tr>"
        )

    refund_html = ""
    if refund_issued and refund_amount:
        refund_html = (
            f"<div style=\"background:#f0f9f0;border-radius:6px;padding:16px;margin:16px 0;"
            f"border:1px solid #c3e6c3;\">"
            f"<strong style=\"color:#2d7a2d;\">Refund: ${refund_amount:.2f}</strong><br>"
            f"<span style=\"font-size:13px;color:#555;\">Processing fee of ${processing_fee:.2f} "
            f"retained (non-refundable).<br>Allow 3-5 business days for the refund to appear.</span>"
            f"</div>"
        )
    else:
        refund_html = (
            f"<div style=\"background:#fff8e6;border-radius:6px;padding:16px;margin:16px 0;"
            f"border:1px solid #f0d87a;\">"
            f"<span style=\"font-size:13px;color:#555;\">No refund issued for this cancellation.</span>"
            f"</div>"
        )

    try:
        resend.Emails.send({
            "from": settings.resend_from_email,
            "to": [to_email],
            "subject": f"Reservation Cancelled #{reservation_id or ''} - Cabin Booking",
            "html": (
                f"<div style=\"font-family:Georgia,serif;max-width:600px;margin:0 auto;\">"
                f"<div style=\"background:#1B3A2D;padding:24px;text-align:center;"
                f"border:3px double #D4A843;border-radius:8px;margin-bottom:24px;\">"
                f"<div style=\"color:#D4A843;font-size:14px;letter-spacing:3px;"
                f"text-transform:uppercase;margin-bottom:4px;\">Cabin Booking</div>"
                f"</div>"
                f"<h2 style=\"color:#1B3A2D;margin-bottom:8px;\">Hi {first_name},</h2>"
                f"<p>Your reservation has been cancelled. Here are the details:</p>"
                f"<table style=\"width:100%;border-collapse:collapse;margin:16px 0;\">"
                f"{details_rows}"
                f"</table>"
                f"{refund_html}"
                f"<p style=\"margin-top:24px;\">If you'd like to make a new reservation, visit "
                f"<a href=\"https://example.com\" style=\"color:#D4A843;\">example.com</a>.</p>"
                f"<p style=\"color:#888;font-size:12px;margin-top:24px;\">This is an automated notification. "
                f"If you did not cancel this reservation, please contact an administrator.</p>"
                f"</div>"
            ),
        })
        return True
    except Exception:
        logger.exception("Failed to send cancellation confirmation email to %s", to_email)
        return False


def _format_release_range(released: dict) -> str:
    start = date.fromisoformat(str(released["start_date"]))
    end = date.fromisoformat(str(released["end_date"]))
    if released.get("is_day_use"):
        return f"day use on {start.strftime('%b %-d, %Y')}"
    last_night = end.fromordinal(end.toordinal() - 1)
    if start == last_night:
        nights = f"night of {start.strftime('%b %-d, %Y')}"
    else:
        nights = f"nights of {start.strftime('%b %-d')}–{last_night.strftime('%b %-d, %Y')}"
    return f"{nights} (checkout {end.strftime('%b %-d')})"


def send_cancellation_availability_email(
    to_email: str,
    first_name: str,
    released_ranges: list[dict],
    availability_url: str,
    unsubscribe_url: str,
    idempotency_key: str,
) -> bool:
    """Send a private cancellation-availability alert to one shareholder."""
    try:
        formatted = [
            {
                "cabin_name": str(item["cabin_name"]),
                "range": _format_release_range(item),
            }
            for item in released_ranges
        ]
    except (KeyError, TypeError, ValueError):
        logger.exception("Invalid cancellation-availability release ranges")
        return False

    cabin_names = list(dict.fromkeys(item["cabin_name"] for item in formatted))
    if len(cabin_names) == 1:
        subject = f"Dates are available for the {cabin_names[0]} cabin"
    elif cabin_names:
        subject = f"Dates are available for the {', '.join(cabin_names[:-1])} and {cabin_names[-1]} cabins"
    else:
        subject = "Dates are available at Cabin Booking"

    if not _use_resend():
        logger.info(
            "\n[DEV] Cancellation availability alert for %s\n  Ranges: %s\n  URL: %s\n",
            to_email,
            formatted,
            availability_url,
        )
        print(
            f"\n[DEV] Cancellation availability alert for {to_email}\n"
            f"  Ranges: {formatted}\n"
            f"  URL: {availability_url}\n"
        )
        return True

    import resend

    resend.api_key = settings.resend_api_key
    rows = "".join(
        f"<tr><td style=\"padding:10px 12px;border-bottom:1px solid #eee;font-weight:bold;\">"
        f"{escape(item['cabin_name'])} cabin</td>"
        f"<td style=\"padding:10px 12px;border-bottom:1px solid #eee;\">"
        f"{escape(item['range'])}</td></tr>"
        for item in formatted
    )

    try:
        resend.Emails.send(
            {
                "from": settings.resend_from_email,
                "to": [to_email],
                "subject": subject,
                "html": (
                    f"<div style=\"font-family:Georgia,serif;max-width:600px;margin:0 auto;\">"
                    f"<div style=\"background:#1B3A2D;padding:24px;text-align:center;"
                    f"border:3px double #D4A843;border-radius:8px;margin-bottom:24px;\">"
                    f"<div style=\"color:#D4A843;font-size:14px;letter-spacing:3px;"
                    f"text-transform:uppercase;\">Cabin Booking</div></div>"
                    f"<h2 style=\"color:#1B3A2D;\">Hi {escape(first_name or 'there')},</h2>"
                    f"<p>A cancellation made these cabin dates available:</p>"
                    f"<table style=\"width:100%;border-collapse:collapse;margin:16px 0;\">{rows}</table>"
                    f"<p style=\"text-align:center;margin:24px 0;\">"
                    f"<a href=\"{escape(availability_url, quote=True)}\" style=\"display:inline-block;"
                    f"padding:14px 28px;background:#D4A843;color:#1B3A2D;text-decoration:none;"
                    f"border-radius:4px;font-weight:bold;\">View Current Availability</a></p>"
                    f"<p><strong>Availability can change at any time.</strong> Normal booking rules still apply, "
                    f"and this email does not hold or guarantee these dates.</p>"
                    f"<p style=\"color:#888;font-size:12px;margin-top:24px;\">"
                    f"You receive these alerts because cancellation availability emails are enabled for your account. "
                    f"<a href=\"{escape(unsubscribe_url, quote=True)}\">Unsubscribe from only these alerts</a>."
                    f"</p></div>"
                ),
            },
            {"idempotency_key": idempotency_key},
        )
        return True
    except Exception:
        logger.exception("Failed to send cancellation availability email to %s", to_email)
        return False


def send_booking_window_reminder_email(
    to_emails: list[str],
    share_name: str,
    round_display: str,
    window_start: str,
    window_end: str,
    max_reservations: int,
    max_nights: int | None,
) -> bool:
    """Send a reminder that a booking window opens tomorrow. In dev mode, prints to console."""
    if not _use_resend():
        logger.info(
            "\n[DEV] Booking window reminder for %s\n"
            "  To: %s\n"
            "  Round: %s\n"
            "  Window: %s to %s\n"
            "  Max reservations: %d | Max nights: %s\n",
            share_name, ", ".join(to_emails),
            round_display, window_start, window_end,
            max_reservations, max_nights or "no limit",
        )
        print(
            f"\n[DEV] Booking window reminder for {share_name}\n"
            f"  To: {', '.join(to_emails)}\n"
            f"  Round: {round_display}\n"
            f"  Window: {window_start} to {window_end}\n"
            f"  Max reservations: {max_reservations} | Max nights: {max_nights or 'no limit'}\n"
        )
        return True

    import resend

    resend.api_key = settings.resend_api_key

    limits_text = f"Up to {max_reservations} reservation(s)"
    if max_nights:
        limits_text += f", max {max_nights} nights"

    try:
        html = (
            f"<div style=\"font-family:Georgia,serif;max-width:600px;margin:0 auto;\">"
            f"<div style=\"background:#1B3A2D;padding:24px;text-align:center;"
            f"border:3px double #D4A843;border-radius:8px;margin-bottom:24px;\">"
            f"<div style=\"color:#D4A843;font-size:14px;letter-spacing:3px;"
            f"text-transform:uppercase;margin-bottom:4px;\">Cabin Booking</div>"
            f"</div>"
            f"<h2 style=\"color:#1B3A2D;margin-bottom:8px;\">Your Booking Window Opens Tomorrow</h2>"
            f"<p>Your booking window for the <strong>{share_name}</strong> share opens tomorrow "
            f"for <strong>{round_display}</strong>.</p>"
            f"<div style=\"background:#f8f5ed;border-radius:6px;padding:16px;margin:16px 0;"
            f"border:1px solid #e8e0cc;\">"
            f"<table style=\"width:100%;font-size:14px;color:#333;\">"
            f"<tr><td style=\"padding:4px 0;font-weight:bold;\">Window:</td>"
            f"<td style=\"padding:4px 0;\">{window_start} to {window_end}</td></tr>"
            f"<tr><td style=\"padding:4px 0;font-weight:bold;\">Limits:</td>"
            f"<td style=\"padding:4px 0;\">{limits_text}</td></tr>"
            f"</table></div>"
            f"<p style=\"text-align:center;margin:24px 0;\">"
            f"<a href=\"https://example.com\" style=\"display:inline-block;"
            f"padding:14px 28px;background:#D4A843;color:#1B3A2D;text-decoration:none;"
            f"border-radius:4px;font-weight:bold;font-size:16px;\">Sign In</a></p>"
            f"<p style=\"color:#888;font-size:12px;text-align:center;\">This is an automated reminder "
            f"from Cabin Booking.</p>"
            f"</div>"
        )
        for email in to_emails:
            resend.Emails.send({
                "from": settings.resend_from_email,
                "to": [email],
                "subject": f"Your Booking Window Opens Tomorrow ({round_display})",
                "html": html,
            })
        return True
    except Exception:
        logger.exception("Failed to send booking window reminder to %s", to_emails)
        return False


def send_reservation_reminder_email(
    to_emails: list[str],
    first_name: str,
    share_name: str,
    start_date: str,
    end_date: str,
    cabins: list[str],
    days_until: int,
    *,
    reservation_id: int | None = None,
) -> bool:
    """Send a reservation reminder email for 7-day, 3-day, and day-of notifications."""
    cabin_str = ", ".join(c.title() for c in cabins) if cabins else "Your selected cabin(s)"

    if days_until <= 0:
        headline = "Your booking is today"
        subject = "Your booking is today - Cabin Booking"
        lead_text = "This is your same-day reminder for check-in."
    else:
        headline = f"Your booking starts in {days_until} days"
        subject = f"Your booking starts in {days_until} days - Cabin Booking"
        lead_text = f"This is your {days_until}-day reminder."

    if not _use_resend():
        logger.info(
            "\n[DEV] Reservation reminder\n"
            "  To: %s\n"
            "  Headline: %s\n"
            "  Share: %s\n"
            "  Dates: %s to %s\n"
            "  Cabins: %s\n"
            "  Reservation #: %s\n",
            ", ".join(to_emails),
            headline,
            share_name,
            start_date,
            end_date,
            cabin_str,
            reservation_id or "N/A",
        )
        print(
            f"\n[DEV] Reservation reminder\n"
            f"  To: {', '.join(to_emails)}\n"
            f"  Headline: {headline}\n"
            f"  Share: {share_name}\n"
            f"  Dates: {start_date} to {end_date}\n"
            f"  Cabins: {cabin_str}\n"
            f"  Reservation #: {reservation_id or 'N/A'}\n"
        )
        return True

    import resend

    resend.api_key = settings.resend_api_key

    td = "padding:8px 12px;border-bottom:1px solid #eee;"
    details_rows = (
        f"<tr><td style=\"{td}font-weight:bold;\">Share</td><td style=\"{td}\">{share_name}</td></tr>"
        f"<tr><td style=\"{td}font-weight:bold;\">Dates</td><td style=\"{td}\">{start_date} to {end_date}</td></tr>"
        f"<tr><td style=\"{td}font-weight:bold;\">Cabin(s)</td><td style=\"{td}\">{cabin_str}</td></tr>"
    )
    if reservation_id:
        details_rows = (
            f"<tr><td style=\"{td}font-weight:bold;\">Reservation #</td><td style=\"{td}\">{reservation_id}</td></tr>"
            f"{details_rows}"
        )

    try:
        html = (
            f"<div style=\"font-family:Georgia,serif;max-width:600px;margin:0 auto;\">"
            f"<div style=\"background:#1B3A2D;padding:24px;text-align:center;"
            f"border:3px double #D4A843;border-radius:8px;margin-bottom:24px;\">"
            f"<div style=\"color:#D4A843;font-size:14px;letter-spacing:3px;"
            f"text-transform:uppercase;margin-bottom:4px;\">Cabin Booking</div>"
            f"</div>"
            f"<h2 style=\"color:#1B3A2D;margin-bottom:8px;\">Hi {first_name},</h2>"
            f"<p style=\"font-size:20px;font-weight:bold;color:#1B3A2D;margin-bottom:8px;\">{headline}</p>"
            f"<p>{lead_text}</p>"
            f"<table style=\"width:100%;border-collapse:collapse;margin:16px 0;\">"
            f"{details_rows}"
            f"</table>"
            f"<p style=\"text-align:center;margin:24px 0;\">"
            f"<a href=\"https://example.com\" style=\"display:inline-block;"
            f"padding:14px 28px;background:#D4A843;color:#1B3A2D;text-decoration:none;"
            f"border-radius:4px;font-weight:bold;font-size:16px;\">View Booking</a></p>"
            f"<p style=\"color:#888;font-size:12px;text-align:center;\">This is an automated reminder "
            f"from Cabin Booking.</p>"
            f"</div>"
        )
        for email in to_emails:
            resend.Emails.send({
                "from": settings.resend_from_email,
                "to": [email],
                "subject": subject,
                "html": html,
            })
        return True
    except Exception:
        logger.exception("Failed to send reservation reminder to %s", to_emails)
        return False


def send_unpaid_reservation_payment_email(
    to_email: str,
    first_name: str,
    share_name: str,
    start_date: str,
    end_date: str,
    cabins: list[str],
    amount_due: float,
    payment_url: str,
    *,
    reservation_id: int,
) -> bool:
    """Send a payment link for an unpaid reservation."""
    cabin_str = ", ".join(c.title() for c in cabins) if cabins else "Your selected cabin(s)"
    amount = f"${amount_due:.2f}"

    if not _use_resend():
        logger.info(
            "\n[DEV] Unpaid reservation payment link\n"
            "  To: %s\n"
            "  Share: %s\n"
            "  Dates: %s to %s\n"
            "  Cabins: %s\n"
            "  Amount: %s\n"
            "  Reservation #: %s\n"
            "  URL: %s\n",
            to_email,
            share_name,
            start_date,
            end_date,
            cabin_str,
            amount,
            reservation_id,
            payment_url,
        )
        print(
            f"\n[DEV] Unpaid reservation payment link\n"
            f"  To: {to_email}\n"
            f"  Share: {share_name}\n"
            f"  Dates: {start_date} to {end_date}\n"
            f"  Cabins: {cabin_str}\n"
            f"  Amount: {amount}\n"
            f"  Reservation #: {reservation_id}\n"
            f"  URL: {payment_url}\n"
        )
        return True

    import resend

    resend.api_key = settings.resend_api_key

    td = "padding:8px 12px;border-bottom:1px solid #eee;"
    details_rows = (
        f"<tr><td style=\"{td}font-weight:bold;\">Reservation #</td><td style=\"{td}\">{reservation_id}</td></tr>"
        f"<tr><td style=\"{td}font-weight:bold;\">Share</td><td style=\"{td}\">{escape(share_name)}</td></tr>"
        f"<tr><td style=\"{td}font-weight:bold;\">Dates</td><td style=\"{td}\">{escape(start_date)} to {escape(end_date)}</td></tr>"
        f"<tr><td style=\"{td}font-weight:bold;\">Cabin(s)</td><td style=\"{td}\">{escape(cabin_str)}</td></tr>"
        f"<tr><td style=\"{td}font-weight:bold;\">Amount Due</td><td style=\"{td}\">{amount}</td></tr>"
    )

    try:
        resend.Emails.send({
            "from": settings.resend_from_email,
            "to": [to_email],
            "subject": "Payment needed for your Cabin Booking reservation",
            "html": (
                f"<div style=\"font-family:Georgia,serif;max-width:600px;margin:0 auto;\">"
                f"<div style=\"background:#1B3A2D;padding:24px;text-align:center;"
                f"border:3px double #D4A843;border-radius:8px;margin-bottom:24px;\">"
                f"<div style=\"color:#D4A843;font-size:14px;letter-spacing:3px;"
                f"text-transform:uppercase;margin-bottom:4px;\">Cabin Booking</div>"
                f"</div>"
                f"<h2 style=\"color:#1B3A2D;margin-bottom:8px;\">Hi {escape(first_name or 'there')},</h2>"
                f"<p>Your reservation is being held, but payment still needs to be completed.</p>"
                f"<table style=\"width:100%;border-collapse:collapse;margin:16px 0;\">"
                f"{details_rows}"
                f"</table>"
                f"<p style=\"text-align:center;margin:24px 0;\">"
                f"<a href=\"{escape(payment_url, quote=True)}\" style=\"display:inline-block;"
                f"padding:14px 28px;background:#D4A843;color:#1B3A2D;text-decoration:none;"
                f"border-radius:4px;font-weight:bold;font-size:16px;\">Pay Now</a></p>"
                f"<p>This secure link signs you in and opens checkout for this reservation. "
                f"It expires in {settings.magic_link_expire_minutes} minutes.</p>"
                f"<p style=\"color:#888;font-size:12px;text-align:center;\">This is an automated reminder "
                f"from Cabin Booking. If this reservation is not yours, you can ignore this email.</p>"
                f"</div>"
            ),
        })
        return True
    except Exception:
        logger.exception("Failed to send unpaid reservation payment email to %s", to_email)
        return False


def send_login_email(to_email: str, login_url: str, first_name: str) -> bool:
    """Send a magic-link login email. In dev mode, prints to console."""
    if not _use_resend():
        logger.info(
            "\n[DEV] Login link for %s (%s)\n"
            "  URL: %s\n",
            to_email, first_name, login_url,
        )
        print(
            f"\n[DEV] Login link for {to_email} ({first_name})\n"
            f"  URL: {login_url}\n"
        )
        return True

    import resend

    resend.api_key = settings.resend_api_key

    try:
        resend.Emails.send({
            "from": settings.resend_from_email,
            "to": [to_email],
            "subject": "Sign in to Cabin Booking",
            "html": (
                f"<h2>Hi {first_name},</h2>"
                f"<p>Click the button below to sign in to Cabin Booking.</p>"
                f"<p><a href=\"{login_url}\" style=\"display:inline-block;padding:12px 24px;"
                f"background:#D4A843;color:#1B3A2D;text-decoration:none;border-radius:4px;"
                f"font-weight:bold;\">Sign In</a></p>"
                f"<p>This link expires in {settings.magic_link_expire_minutes} minutes.</p>"
                f"<p style=\"color:#888;font-size:12px;\">If you didn't request this, you can ignore this email.</p>"
            ),
        })
        return True
    except Exception:
        logger.exception("Failed to send login email to %s", to_email)
        return False
