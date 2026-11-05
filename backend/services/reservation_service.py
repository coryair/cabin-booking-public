from sqlalchemy.orm import Session as DBSession, joinedload
from sqlalchemy import and_
from datetime import datetime, date, timedelta
from contextlib import contextmanager
import threading
import json

from db.models import Reservation, Shareholder, Share, Cabin
from models.reservation import ReservationCreate
from services.booking_round_service import BookingRoundService
from services.guest_nights_service import normalize_guest_nights_input, serialize_guest_nights, stay_units


_booking_scope_guard = threading.Lock()
_booking_scope_locks: dict[str, threading.Lock] = {}


class ReservationService:
    @staticmethod
    @contextmanager
    def booking_scope(
        db: DBSession,
        share_id: str,
        cabins: list[str],
    ):
        """
        Serialize booking writes that could contend on the same share/cabin set.

        On Postgres this issues SELECT ... FOR UPDATE. On SQLite the clause is
        ignored, so local dev also acquires an in-process lock for the same
        cabin/share scope.
        """
        normalized_cabins = sorted({cabin for cabin in cabins if cabin})
        scope_keys = [f"share:{share_id}", *(f"cabin:{cabin}" for cabin in normalized_cabins)]
        held_locks: list[threading.Lock] = []

        try:
            if db.bind is not None and db.bind.dialect.name == "sqlite":
                with _booking_scope_guard:
                    for key in scope_keys:
                        _booking_scope_locks.setdefault(key, threading.Lock())
                    held_locks = [_booking_scope_locks[key] for key in scope_keys]
                for lock in held_locks:
                    lock.acquire()

            db.query(Share).filter(
                Share.share_id == share_id
            ).with_for_update().all()

            if normalized_cabins:
                db.query(Cabin).filter(
                    Cabin.cabin_id.in_(normalized_cabins)
                ).order_by(Cabin.cabin_id).with_for_update().all()

            yield
        finally:
            for lock in reversed(held_locks):
                lock.release()

    @staticmethod
    def normalize_reservation_dates(
        start_date: str,
        end_date: str,
        is_day_use: bool
    ) -> tuple[str, str, bool]:
        """
        Normalize reservation date semantics to the canonical half-open model [start, end).

        Rules:
        - If start == end, interpret as same-day day-use and normalize to end = start + 1 day.
        - Day-use reservations must span exactly one day.
        - If end < start, reject.
        - Otherwise preserve dates/is_day_use.
        """
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)

        if start == end:
            return start.isoformat(), (start + timedelta(days=1)).isoformat(), True

        if end < start:
            raise ValueError("end_date must be on or after start_date")

        if is_day_use and (end - start).days != 1:
            raise ValueError("Day-use reservations must be a single day")

        return start.isoformat(), end.isoformat(), is_day_use

    @staticmethod
    def get_conflicting_reservations(
        db: DBSession,
        cabins: list[str],
        start_date: str,
        end_date: str,
        exclude_id: int | None = None
    ) -> list[Reservation]:
        """Find reservations that overlap with the given date range for specified cabins."""
        query = db.query(Reservation).options(
            joinedload(Reservation.share_rel)
        ).filter(
            and_(
                Reservation.start_date < end_date,
                Reservation.end_date > start_date,
                Reservation.status.notin_(["cancelled", "refunded"]),
            )
        )

        if exclude_id:
            query = query.filter(Reservation.id != exclude_id)

        # Filter by cabins - check if any cabin in the reservation overlaps
        all_reservations = query.all()
        conflicts = []
        for res in all_reservations:
            res_cabins = json.loads(res.cabins) if isinstance(res.cabins, str) else res.cabins
            if any(cabin in res_cabins for cabin in cabins):
                conflicts.append(res)

        return conflicts

    @staticmethod
    def check_availability(
        db: DBSession,
        start_date: str,
        end_date: str,
        cabins: list[str] | None = None
    ) -> dict[str, list[Reservation]]:
        """Check availability for each cabin. Returns cabin -> list of conflicting reservations."""
        all_cabins = db.query(Cabin).all()
        cabin_ids = [c.cabin_id for c in all_cabins]

        if cabins:
            cabin_ids = [c for c in cabins if c in cabin_ids]

        # Single query for all conflicts in the date range
        all_conflicts = ReservationService.get_conflicting_reservations(
            db, cabin_ids, start_date, end_date
        )

        # Bucket conflicts by cabin
        result: dict[str, list[Reservation]] = {cid: [] for cid in cabin_ids}
        for res in all_conflicts:
            res_cabins = json.loads(res.cabins) if isinstance(res.cabins, str) else res.cabins
            for cid in cabin_ids:
                if cid in res_cabins:
                    result[cid].append(res)

        return result

    @staticmethod
    def create_reservation(
        db: DBSession,
        reservation: ReservationCreate,
        is_admin: bool = False,
        status: str = "reserved",
        booked_by_shareholder_id: int | None = None
    ) -> tuple[Reservation | None, str | None]:
        """
        Create a reservation with round-based eligibility and conflict checking.
        Cost is computed server-side.
        Returns (reservation, error_message).
        """
        # Normalize same-day requests to canonical day-use storage.
        try:
            normalized_start, normalized_end, normalized_day_use = ReservationService.normalize_reservation_dates(
                reservation.start_date,
                reservation.end_date,
                reservation.is_day_use
            )
        except ValueError as exc:
            return None, str(exc)

        with ReservationService.booking_scope(db, reservation.share, reservation.cabins):
            # Check round eligibility
            eligible, error, context = BookingRoundService.check_round_eligibility(
                db,
                reservation.share,
                normalized_start,
                normalized_end,
                reservation.cabins,
                is_admin=is_admin
            )
            if not eligible:
                return None, error

            # Check for conflicts
            conflicts = ReservationService.get_conflicting_reservations(
                db,
                reservation.cabins,
                normalized_start,
                normalized_end
            )
            if conflicts:
                cabin_names = ", ".join(reservation.cabins)
                return None, f"Conflict: {cabin_names} already booked for these dates"

            # Compute cost server-side
            try:
                normalized_guest_nights = normalize_guest_nights_input(
                    getattr(reservation, "guest_nights", None),
                    reservation.guest_count,
                    max_units=stay_units(normalized_start, normalized_end),
                )
            except ValueError as exc:
                return None, str(exc)

            cost_info = BookingRoundService.compute_reservation_cost(
                db,
                normalized_start,
                normalized_end,
                reservation.cabins,
                is_day_use=normalized_day_use,
                guest_count=reservation.guest_count,
                guest_nights=normalized_guest_nights,
            )

            booking_round = context.get("round") or context.get("current_round", "unknown")

            # Create the reservation
            db_reservation = Reservation(
                share=reservation.share,
                booked_by_shareholder_id=booked_by_shareholder_id,
                guest_count=len(normalized_guest_nights),
                guest_nights_json=serialize_guest_nights(normalized_guest_nights),
                start_date=normalized_start,
                end_date=normalized_end,
                cabins=json.dumps(reservation.cabins),
                cost=cost_info["total"],
                base_cost=cost_info["base_cost"],
                processing_fee=cost_info["processing_fee"],
                is_day_use=1 if normalized_day_use else 0,
                guest_fee=cost_info["guest_fee"] if cost_info["guest_fee"] > 0 else None,
                booking_round=booking_round,
                status=status
            )
            db.add(db_reservation)

            # Update all shareholders' last_booked for this share
            shareholders = db.query(Shareholder).filter(
                Shareholder.share == reservation.share
            ).all()
            for shareholder in shareholders:
                shareholder.last_booked = datetime.utcnow().isoformat()

            db.commit()
        # Eagerly load the share_rel relationship
        db_reservation = db.query(Reservation).options(
            joinedload(Reservation.share_rel)
        ).filter(Reservation.id == db_reservation.id).first()
        return db_reservation, None
