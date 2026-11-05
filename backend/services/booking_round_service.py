from sqlalchemy.orm import Session as DBSession
from sqlalchemy import and_
from datetime import date, datetime, timedelta
import json

from db.models import BookingSeason, BookingRound, Reservation, Rate, Share
from services.date_service import get_today
from services.guest_nights_service import normalize_guest_nights_input, guest_nights_total
from services.fee_policy_service import FEE_POLICY_PCT


class BookingRoundService:

    @staticmethod
    def get_season_for_date(db: DBSession, target_date: date) -> BookingSeason | None:
        """Get the booking season config for the year of target_date."""
        return db.query(BookingSeason).filter(
            BookingSeason.year == target_date.year
        ).first()

    @staticmethod
    def get_current_season(db: DBSession) -> BookingSeason | None:
        """Get the booking season config for the current year."""
        return db.query(BookingSeason).filter(
            BookingSeason.year == get_today(db).year
        ).first()

    @staticmethod
    def _get_round(season: BookingSeason, round_name: str) -> BookingRound | None:
        """Map 'round_1' → BookingRound with round_number=1."""
        num = int(round_name.split("_")[1])
        return next((r for r in season.rounds if r.round_number == num), None)

    @staticmethod
    def determine_current_round(db: DBSession, today: date | None = None) -> str:
        """
        Determine which booking round is active based on today's date.
        Returns: round_1, round_2, round_3, open, offseason, between_rounds
        """
        if today is None:
            today = get_today(db)

        season = BookingRoundService.get_season_for_date(db, today)
        if not season:
            return "offseason"

        today_str = today.isoformat()

        # Check each round in order
        for i, rnd in enumerate(season.rounds):
            if today_str < rnd.start_date:
                # Before this round - check if we're before the first round or between rounds
                if i == 0:
                    return "offseason"
                return "between_rounds"
            if rnd.start_date <= today_str <= rnd.end_date:
                return f"round_{rnd.round_number}"

        # After all rounds
        last_round = season.rounds[-1] if season.rounds else None
        if last_round and today_str > last_round.end_date and today_str < season.open_season_start:
            return "between_rounds"

        if today_str >= season.open_season_start:
            if today_str <= season.open_season_end:
                return "open"
            else:
                return "offseason"

        return "offseason"

    @staticmethod
    def get_total_shares(db: DBSession) -> int:
        """Get total number of shares."""
        return db.query(Share).count()

    @staticmethod
    def get_shareholder_booking_window(
        db: DBSession,
        share_id: str,
        round_name: str,
        season: BookingSeason
    ) -> tuple[date, date] | None:
        """
        Compute the specific booking window for a share in a given round.
        Returns (window_start, window_end) or None if not applicable.
        """
        rnd = BookingRoundService._get_round(season, round_name)
        if not rnd:
            return None

        share = db.query(Share).filter(Share.share_id == share_id).first()
        if not share:
            return None

        priority = share.priority  # 1-indexed
        total_shares = BookingRoundService.get_total_shares(db)
        round_start = date.fromisoformat(rnd.start_date)

        if rnd.priority_order == "priority":
            offset = (priority - 1) * rnd.window_days
        else:  # "reverse"
            num_booking_shares = total_shares  # All shares participate in booking
            position = num_booking_shares - priority
            offset = position * rnd.window_days

        window_start = round_start + timedelta(days=offset)
        window_end = window_start + timedelta(days=rnd.window_days - 1)
        return (window_start, window_end)

    @staticmethod
    def _sum_merged_nights(ranges: list[tuple[date, date]]) -> int:
        """Merge overlapping/adjacent date ranges and return total nights."""
        if not ranges:
            return 0
        ranges.sort()
        merged = [ranges[0]]
        for start, end in ranges[1:]:
            if start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return sum((end - start).days for start, end in merged)

    @staticmethod
    def get_share_season_nights(db: DBSession, share_id: str, season: BookingSeason) -> int:
        """
        Count total nights booked by this share in prime season.
        Uses checkout model: nights = end_date - start_date in days.
        Only counts nights that fall within prime season.
        """
        reservations = db.query(Reservation).filter(
            and_(
                Reservation.share == share_id,
                Reservation.start_date < season.prime_season_end,
                Reservation.end_date > season.prime_season_start,
                Reservation.status.notin_(["cancelled", "refunded"]),
            )
        ).all()

        prime_start = date.fromisoformat(season.prime_season_start)
        prime_end = date.fromisoformat(season.prime_season_end)

        ranges = []
        for res in reservations:
            res_start = date.fromisoformat(res.start_date)
            res_end = date.fromisoformat(res.end_date)
            effective_start = max(res_start, prime_start)
            effective_end = min(res_end, prime_end)
            if effective_end > effective_start:
                ranges.append((effective_start, effective_end))

        return BookingRoundService._sum_merged_nights(ranges)

    @staticmethod
    def get_share_round_reservation_count(db: DBSession, share_id: str, round_name: str) -> int:
        """Count reservations made by this share in a specific round."""
        return db.query(Reservation).filter(
            and_(
                Reservation.share == share_id,
                Reservation.booking_round == round_name,
                Reservation.status.notin_(["cancelled", "refunded"]),
            )
        ).count()

    @staticmethod
    def _build_round_context(db: DBSession, share_id: str) -> dict:
        """
        Build the shared round context used by both check_round_eligibility and
        get_booking_status. Computes season, round, window, night counts, and
        reservation counts once.
        """
        today = get_today(db)
        season = BookingRoundService.get_season_for_date(db, today)
        current_round = BookingRoundService.determine_current_round(db, today)

        ctx = {
            "today": today,
            "season": season,
            "current_round": current_round,
            "window": None,
            "nights_used": 0,
            "nights_remaining": 0,
            "round_count": 0,
            "round_nights": 0,
            "shareholder": None,
            "priority": None,
            "total_shares": None,
        }

        share = db.query(Share).filter(Share.share_id == share_id).first()
        ctx["share"] = share
        if share:
            ctx["priority"] = share.priority
            ctx["total_shares"] = BookingRoundService.get_total_shares(db)

        if season:
            ctx["nights_used"] = BookingRoundService.get_share_season_nights(db, share_id, season)
            ctx["nights_remaining"] = season.season_max_nights - ctx["nights_used"]

        if season and current_round.startswith("round_"):
            ctx["window"] = BookingRoundService.get_shareholder_booking_window(
                db, share_id, current_round, season
            )
            ctx["round_count"] = BookingRoundService.get_share_round_reservation_count(
                db, share_id, current_round
            )
            rnd = BookingRoundService._get_round(season, current_round)
            if rnd and rnd.max_nights is not None:
                ctx["round_nights"] = BookingRoundService._get_share_round_nights(
                    db, share_id, current_round
                )

        return ctx

    @staticmethod
    def check_round_eligibility(
        db: DBSession,
        share_id: str,
        start_date: str,
        end_date: str,
        cabins: list[str],
        is_admin: bool = False
    ) -> tuple[bool, str | None, dict]:
        """
        Master eligibility check.
        Returns (eligible, error_msg, context_dict).
        """
        result = {}

        # Admin bypass
        if is_admin:
            result["round"] = "admin"
            return True, None, result

        ctx = BookingRoundService._build_round_context(db, share_id)
        today = ctx["today"]
        season = ctx["season"]
        current_round = ctx["current_round"]
        result["current_round"] = current_round

        if current_round == "between_rounds":
            # Allow non-prime dates even between rounds
            if season:
                req_start = date.fromisoformat(start_date)
                req_end = date.fromisoformat(end_date)
                prime_start = date.fromisoformat(season.prime_season_start)
                prime_end = date.fromisoformat(season.prime_season_end)
                if req_start >= prime_end or req_end <= prime_start:
                    result["round"] = "offseason"
                    return True, None, result
            return False, "Booking is not open right now. The next round hasn't started yet.", result

        # Off-season: block reservations that overlap prime season
        if current_round == "offseason":
            result["round"] = "offseason"
            req_start = date.fromisoformat(start_date)
            req_end = date.fromisoformat(end_date)
            years_to_check = {req_start.year}
            if req_end.year != req_start.year:
                years_to_check.add(req_end.year)
            for year in years_to_check:
                year_season = db.query(BookingSeason).filter(BookingSeason.year == year).first()
                if year_season:
                    prime_start = date.fromisoformat(year_season.prime_season_start)
                    prime_end = date.fromisoformat(year_season.prime_season_end)
                    if req_start < prime_end and req_end > prime_start:
                        first_round = year_season.rounds[0] if year_season.rounds else None
                        round_start_str = first_round.start_date if first_round else "TBD"
                        return False, (
                            f"Prime season dates ({year_season.prime_season_start} to "
                            f"{year_season.prime_season_end}) cannot be booked during the off-season. "
                            f"Booking rounds begin {round_start_str}."
                        ), result
            return True, None, result

        # Open season: 30-day advance limit only (prime night cap lifted)
        if current_round == "open":
            if season:
                req_start = date.fromisoformat(start_date)
                req_end = date.fromisoformat(end_date)
                prime_start = date.fromisoformat(season.prime_season_start)
                prime_end = date.fromisoformat(season.prime_season_end)
                # Entirely outside prime season - no restriction
                if req_start >= prime_end or req_end <= prime_start:
                    result["round"] = "offseason"
                    return True, None, result
                # 30-day advance booking limit
                max_advance_date = today + timedelta(days=30)
                if req_start > max_advance_date:
                    result["round"] = "open"
                    return False, (
                        f"During open season, you can only book up to 30 days in advance. "
                        f"The earliest you can book {start_date} is "
                        f"{(req_start - timedelta(days=30)).strftime('%b %d, %Y')}."
                    ), result
            result["round"] = "open"
            return True, None, result

        if not season:
            return False, "No booking season configured for this year.", result

        # Rounds 1-3: if requested dates are entirely outside prime season, allow freely
        req_start = date.fromisoformat(start_date)
        req_end = date.fromisoformat(end_date)
        prime_start = date.fromisoformat(season.prime_season_start)
        prime_end = date.fromisoformat(season.prime_season_end)
        if req_start >= prime_end or req_end <= prime_start:
            result["round"] = "offseason"
            return True, None, result

        # Rounds: check window, reservation count, and night limits
        rnd = BookingRoundService._get_round(season, current_round)

        window = ctx["window"]
        if window:
            result["window_start"] = window[0].isoformat()
            result["window_end"] = window[1].isoformat()

        # Check if today is within the shareholder's window
        if window and not (window[0] <= today <= window[1]):
            round_label = current_round.replace("_", " ").title()
            window_range = f"{window[0].strftime('%b %d')} – {window[1].strftime('%b %d')}"
            if today < window[0]:
                return False, (
                    f"{round_label} opens for your share {window_range}. "
                    f"You can book starting {window[0].strftime('%b %d')}."
                ), result
            return False, (
                f"Your {round_label} booking window was {window_range} and has ended. "
                f"You can book again when the next eligible round opens, if dates are still available."
            ), result

        # Check per-round reservation count limits
        round_count = ctx["round_count"]
        result["round_reservations"] = round_count

        if rnd:
            if round_count >= rnd.max_reservations:
                return False, (
                    f"You've already made {round_count} reservation(s) in "
                    f"{current_round.replace('_', ' ').title()} (max {rnd.max_reservations})."
                ), result

        # Check night limits
        req_nights = (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days
        nights_used = ctx["nights_used"]
        result["nights_used"] = nights_used
        result["nights_remaining"] = ctx["nights_remaining"]

        # Per-round night cap (applies to any round that has it set)
        if rnd and rnd.max_nights is not None:
            round_nights = ctx["round_nights"]
            result["round_nights"] = round_nights
            if round_nights + req_nights > rnd.max_nights:
                return False, (
                    f"This would use {round_nights + req_nights} nights in "
                    f"{current_round.replace('_', ' ').title()} "
                    f"(max {rnd.max_nights}). You have {rnd.max_nights - round_nights} remaining."
                ), result

        # Round 3: only if share has < season_max_nights total
        if current_round == "round_3" and nights_used >= season.season_max_nights:
            return False, (
                f"You already have {nights_used} prime season nights booked "
                f"(max {season.season_max_nights}). Round 3 is only for shareholders who haven't reached the cap."
            ), result

        # Season total cap
        if nights_used + req_nights > season.season_max_nights:
            return False, (
                f"This booking would use {nights_used + req_nights} of your {season.season_max_nights} "
                f"allowed prime season nights. You have {season.season_max_nights - nights_used} remaining."
            ), result

        result["round"] = current_round
        return True, None, result

    @staticmethod
    def _get_share_round_nights(db: DBSession, share_id: str, round_name: str) -> int:
        """Count total calendar nights booked by a share in a specific round."""
        reservations = db.query(Reservation).filter(
            and_(
                Reservation.share == share_id,
                Reservation.booking_round == round_name,
                Reservation.status.notin_(["cancelled", "refunded"]),
            )
        ).all()
        ranges = []
        for res in reservations:
            start = date.fromisoformat(res.start_date)
            end = date.fromisoformat(res.end_date)
            if end > start:
                ranges.append((start, end))
        return BookingRoundService._sum_merged_nights(ranges)

    @staticmethod
    def compute_reservation_cost(
        db: DBSession,
        start_date: str,
        end_date: str,
        cabins: list[str],
        season_override: BookingSeason | None = None,
        is_day_use: bool = False,
        guest_count: int = 0,
        guest_nights: list[int] | None = None,
    ) -> dict:
        """
        Server-side cost computation.
        Returns dict with base_cost, processing_fee, total, nightly_rate, daily_rate,
        nights, cabin_count, guest_fee, guest_fee_rate, guest_count, guest_nights_total.
        """
        today = get_today(db)
        season = season_override or BookingRoundService.get_season_for_date(db, today)

        # Determine if dates fall in on-season or off-season
        res_start = date.fromisoformat(start_date)
        season_type = "offseason"
        if season:
            prime_start = date.fromisoformat(season.prime_season_start)
            prime_end = date.fromisoformat(season.prime_season_end)
            if res_start >= prime_start and res_start <= prime_end:
                season_type = "onseason"

        # Get rate from DB
        rate = db.query(Rate).filter(Rate.season == season_type).order_by(Rate.effective_date.desc()).first()
        nightly_rate = rate.nightly_rate if rate else 50.0
        daily_rate = rate.daily_rate if rate else 25.0

        nights = (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days
        nights = max(1, nights)
        cabin_count = len(cabins)

        # Use daily_rate for day-use, nightly_rate for overnight
        unit_rate = daily_rate if is_day_use else nightly_rate
        base_cost = unit_rate * nights * cabin_count

        normalized_guest_nights = normalize_guest_nights_input(
            guest_nights,
            guest_count,
            max_units=nights,
        )
        normalized_guest_count = len(normalized_guest_nights)
        total_guest_nights = guest_nights_total(normalized_guest_nights)

        # Guest fee: guest_fee_per_day x total guest nights
        guest_fee_rate = season.guest_fee_per_day if season else 10.0
        guest_fee = guest_fee_rate * total_guest_nights if total_guest_nights > 0 else 0.0

        # Flat fee policy source of truth.
        fee_pct = FEE_POLICY_PCT
        processing_fee = round((base_cost + guest_fee) * fee_pct, 2)
        total = round(base_cost + guest_fee + processing_fee, 2)

        return {
            "base_cost": base_cost,
            "processing_fee": processing_fee,
            "total": total,
            "nightly_rate": nightly_rate,
            "daily_rate": daily_rate,
            "nights": nights,
            "cabin_count": cabin_count,
            "season_type": season_type,
            "fee_pct": fee_pct,
            "is_day_use": is_day_use,
            "guest_fee": guest_fee,
            "guest_fee_rate": guest_fee_rate,
            "guest_count": normalized_guest_count,
            "guest_nights_total": total_guest_nights,
        }

    @staticmethod
    def get_booking_status(db: DBSession, share_id: str) -> dict:
        """
        Full booking status for the current user.
        Returns round info, window dates, nights used/remaining, can_book, reason.
        """
        ctx = BookingRoundService._build_round_context(db, share_id)
        today = ctx["today"]
        season = ctx["season"]
        current_round = ctx["current_round"]
        window = ctx["window"]
        nights_used = ctx["nights_used"]
        round_count = ctx["round_count"]

        status = {
            "current_round": current_round,
            "current_round_display": current_round.replace("_", " ").title(),
            "can_book": False,
            "reason": None,
            "window_start": None,
            "window_end": None,
            "nights_used": nights_used,
            "nights_remaining": ctx["nights_remaining"],
            "season_max_nights": 0,
            "round_reservations": round_count,
            "round_max_reservations": 0,
            "round_nights": ctx["round_nights"],
            "round_max_nights": None,
            "now_booking_share_name": None,
            "priority": ctx["priority"],
            "total_shares": ctx["total_shares"],
            "next_phase": None,
            "next_phase_date": None,
            "prime_season_start": season.prime_season_start if season else None,
            "prime_season_end": season.prime_season_end if season else None,
        }

        # Determine which share is currently booking (during rounds)
        if season and current_round.startswith("round_"):
            shares = db.query(Share).all()
            for s in shares:
                s_window = BookingRoundService.get_shareholder_booking_window(
                    db, s.share_id, current_round, season
                )
                if s_window and s_window[0] <= today <= s_window[1]:
                    status["now_booking_share_name"] = s.share_name
                    break

        # Compute next phase info
        if season:
            today_str = today.isoformat()
            rounds = season.rounds

            if current_round == "offseason" and rounds and today_str < rounds[0].start_date:
                status["next_phase"] = f"Round {rounds[0].round_number}"
                status["next_phase_date"] = rounds[0].start_date
            elif current_round.startswith("round_"):
                # Find the next round after current
                rnd = BookingRoundService._get_round(season, current_round)
                if rnd:
                    next_rnd = next((r for r in rounds if r.round_number > rnd.round_number), None)
                    if next_rnd:
                        status["next_phase"] = f"Round {next_rnd.round_number}"
                        status["next_phase_date"] = next_rnd.start_date
                    else:
                        status["next_phase"] = "Open Season"
                        status["next_phase_date"] = season.open_season_start
            elif current_round == "open":
                status["next_phase"] = "Open Season Ends"
                status["next_phase_date"] = season.open_season_end
            elif current_round == "between_rounds":
                # Find the next round whose start_date is after today
                for rnd in rounds:
                    if today_str < rnd.start_date:
                        status["next_phase"] = f"Round {rnd.round_number}"
                        status["next_phase_date"] = rnd.start_date
                        break
                else:
                    if today_str < season.open_season_start:
                        status["next_phase"] = "Open Season"
                        status["next_phase_date"] = season.open_season_start

        if not season:
            status["reason"] = "No booking season configured for this year."
            if current_round == "offseason":
                status["can_book"] = True
                status["reason"] = None
            return status

        status["season_max_nights"] = season.season_max_nights

        if current_round == "offseason":
            status["can_book"] = True
            return status

        if current_round == "between_rounds":
            status["reason"] = "Between booking rounds. The next round hasn't started yet."
            return status

        if current_round == "open":
            status["can_book"] = True
            return status

        # Rounds
        rnd = BookingRoundService._get_round(season, current_round)
        if window:
            status["window_start"] = window[0].isoformat()
            status["window_end"] = window[1].isoformat()

        if rnd:
            status["round_max_reservations"] = rnd.max_reservations
            status["round_max_nights"] = rnd.max_nights

        # Determine if they can book right now
        in_window = window and window[0] <= today <= window[1]
        if not in_window:
            if window:
                round_name = current_round.replace("_", " ").title()
                status["reason"] = (
                    f"Your {round_name} window is {window[0].strftime('%b %d')} – {window[1].strftime('%b %d')}."
                )
            else:
                status["reason"] = "Could not determine your booking window."
            return status

        # Check reservation count
        if rnd and round_count >= rnd.max_reservations:
            status["reason"] = (
                f"You've made {round_count} of {rnd.max_reservations} "
                f"{current_round.replace('_', ' ').title()} reservations."
            )
            return status

        # Round 3: must have < season_max_nights
        if current_round == "round_3" and nights_used >= season.season_max_nights:
            status["reason"] = f"You already have {nights_used} nights (max {season.season_max_nights})."
            return status

        status["can_book"] = True
        return status
