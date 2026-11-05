"""
Booking Round Simulation Test Suite for Cabin Booking.

Simulates the entire 2026 booking season end-to-end by running against the
live backend, using the time-travel API to fast-forward through each family's
booking window from Round 1 Day 1 through Open Season.

Usage:
    cd backend && source venv/bin/activate
    SEED_PASSWORD=<password> python tests/booking_simulation.py
"""

import os
import sys
import httpx

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
PASSWORD = os.environ.get("SEED_PASSWORD", "")

# Families in priority order (priority 1-9).
# (share_id, display_name, email, priority)
FAMILIES = [
    ("aspen", "Aspen",      "aspen@example.com", 1),
    ("maple",  "Demo Four",     "maple@example.com",  2),
    ("oak",     "Oak",          "oak@example.com",     3),
    ("willow",  "Demo Six",     "willow@example.com",  4),
    ("spruce",  "Spruce",       "spruce@example.com",  5),
    ("elm",   "Demo Eight", "elm@example.com",   6),
    ("fir",  "Fir",       "fir@example.com",  7),
    ("alder",    "Alder",         "alder@example.com",    8),
    ("birch",    "Birch",         "birch@example.com",    9),
]

ADMIN_EMAIL = "admin@example.com"

# Pre-planned date ranges for each family's bookings (non-overlapping prime dates).
# Each family gets unique date ranges per round to avoid cabin conflicts.
# Format: (start_date, end_date, cabin)
ROUND1_BOOKINGS = {
    "alder":    ("2026-06-01", "2026-06-04", "pine"),    # 3 nights
    "birch":    ("2026-06-05", "2026-06-08", "pine"),    # 3 nights
    "aspen": ("2026-06-09", "2026-06-12", "cedar"),   # 3 nights
    "maple":  ("2026-06-13", "2026-06-16", "pine"),    # 3 nights
    "oak":     ("2026-06-17", "2026-06-20", "cedar"),   # 3 nights
    "willow":  ("2026-06-21", "2026-06-24", "pine"),    # 3 nights
    "spruce":  ("2026-06-25", "2026-06-28", "cedar"),   # 3 nights
    "elm":   ("2026-06-29", "2026-07-02", "pine"),    # 3 nights
    "fir":  ("2026-07-16", "2026-07-19", "cedar"),   # 3 nights
}

# Alder's 2nd Round 1 booking (testing max 2 reservations)
ALDER_ROUND1_SECOND = ("2026-06-04", "2026-06-07", "cedar")  # 3 nights, no overlap

ROUND2_BOOKINGS = {
    "alder":    ("2026-08-10", "2026-08-13", "pine"),    # 3 nights
    "birch":    ("2026-08-13", "2026-08-16", "cedar"),   # 3 nights
    "aspen": ("2026-08-16", "2026-08-19", "pine"),    # 3 nights
    "maple":  ("2026-08-19", "2026-08-22", "cedar"),   # 3 nights
    "oak":     ("2026-08-22", "2026-08-25", "pine"),    # 3 nights
    "willow":  ("2026-07-01", "2026-07-04", "cedar"),   # 3 nights
    "spruce":  ("2026-07-05", "2026-07-08", "pine"),    # 3 nights
    "elm":   ("2026-07-08", "2026-07-11", "cedar"),   # 3 nights
    "fir":  ("2026-07-11", "2026-07-14", "pine"),    # 3 nights
}

ROUND3_BOOKINGS = {
    "alder":    ("2026-08-25", "2026-08-27", "cedar"),   # 2 nights
    "birch":    ("2026-08-27", "2026-08-29", "pine"),    # 2 nights
    "aspen": ("2026-08-29", "2026-08-31", "cedar"),   # 2 nights
    "maple":  ("2026-09-01", "2026-09-03", "pine"),    # 2 nights
    "oak":     ("2026-09-03", "2026-09-05", "cedar"),   # 2 nights
    "willow":  ("2026-09-05", "2026-09-07", "pine"),    # 2 nights
    "spruce":  ("2026-09-07", "2026-09-09", "cedar"),   # 2 nights
    "elm":   ("2026-09-10", "2026-09-12", "pine"),    # 2 nights
    "fir":  ("2026-09-12", "2026-09-14", "cedar"),   # 2 nights
}

# 2026 booking windows (from seed config)
# Round 1: Apr 1-18, 2-day windows, priority order
ROUND1_WINDOWS = {
    "alder":    ("2026-04-01", "2026-04-02"),
    "birch":    ("2026-04-03", "2026-04-04"),
    "aspen": ("2026-04-05", "2026-04-06"),
    "maple":  ("2026-04-07", "2026-04-08"),
    "oak":     ("2026-04-09", "2026-04-10"),
    "willow":  ("2026-04-11", "2026-04-12"),
    "spruce":  ("2026-04-13", "2026-04-14"),
    "elm":   ("2026-04-15", "2026-04-16"),
    "fir":  ("2026-04-17", "2026-04-18"),
}

# Round 2: Apr 20-May 7, 2-day windows, REVERSE order
ROUND2_WINDOWS = {
    "fir":  ("2026-04-20", "2026-04-21"),
    "elm":   ("2026-04-22", "2026-04-23"),
    "spruce":  ("2026-04-24", "2026-04-25"),
    "willow":  ("2026-04-26", "2026-04-27"),
    "oak":     ("2026-04-28", "2026-04-29"),
    "maple":  ("2026-04-30", "2026-05-01"),
    "aspen": ("2026-05-02", "2026-05-03"),
    "birch":    ("2026-05-04", "2026-05-05"),
    "alder":    ("2026-05-06", "2026-05-07"),
}

# Round 3: May 10-18, 1-day windows, priority order
ROUND3_WINDOWS = {
    "alder":    ("2026-05-10", "2026-05-10"),
    "birch":    ("2026-05-11", "2026-05-11"),
    "aspen": ("2026-05-12", "2026-05-12"),
    "maple":  ("2026-05-13", "2026-05-13"),
    "oak":     ("2026-05-14", "2026-05-14"),
    "willow":  ("2026-05-15", "2026-05-15"),
    "spruce":  ("2026-05-16", "2026-05-16"),
    "elm":   ("2026-05-17", "2026-05-17"),
    "fir":  ("2026-05-18", "2026-05-18"),
}


class SimulationResult:
    """Tracks assertion pass/fail counts and messages."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.messages: list[str] = []

    def ok(self, msg: str):
        self.passed += 1
        self.messages.append(f"  \u2713 {msg}")

    def fail(self, msg: str):
        self.failed += 1
        self.messages.append(f"  \u2717 FAIL: {msg}")

    def header(self, msg: str):
        self.messages.append(f"\n{'=' * 60}")
        self.messages.append(msg)
        self.messages.append('=' * 60)

    def subheader(self, msg: str):
        self.messages.append(f"\n{msg}")

    def print_all(self):
        for m in self.messages:
            print(m)
        print(f"\n{'=' * 60}")
        print(f"SUMMARY: {self.passed + self.failed} assertions, "
              f"{self.passed} passed, {self.failed} failed")
        print('=' * 60)


class BookingSimulator:
    """Helper class for interacting with the backend API."""

    def __init__(self, result: SimulationResult):
        self.result = result
        self._admin_client: httpx.Client | None = None
        self._family_clients: dict[str, httpx.Client] = {}

    def _get_admin_client(self) -> httpx.Client:
        if self._admin_client is None:
            self._admin_client = self._login(ADMIN_EMAIL)
        return self._admin_client

    def _login(self, email: str) -> httpx.Client:
        client = httpx.Client(base_url=BASE_URL)
        resp = client.post("/api/auth/login", json={
            "email": email,
            "password": PASSWORD,
        })
        if resp.status_code != 200:
            raise RuntimeError(f"Login failed for {email}: {resp.status_code} {resp.text}")
        return client

    def get_family_client(self, share_id: str) -> httpx.Client:
        if share_id not in self._family_clients:
            email = next(f[2] for f in FAMILIES if f[0] == share_id)
            self._family_clients[share_id] = self._login(email)
        return self._family_clients[share_id]

    def set_date(self, date_str: str):
        client = self._get_admin_client()
        resp = client.post("/api/time-travel", json={"date": date_str})
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to set date to {date_str}: {resp.status_code} {resp.text}")

    def clear_date(self):
        client = self._get_admin_client()
        resp = client.delete("/api/time-travel")
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to clear time-travel: {resp.status_code} {resp.text}")

    def cleanup_reservations(self):
        """Delete all existing reservations to start from a clean slate."""
        client = self._get_admin_client()
        resp = client.get("/api/reservations")
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to list reservations: {resp.status_code} {resp.text}")
        reservations = resp.json()
        for res in reservations:
            del_resp = client.delete(f"/api/reservations/{res['id']}")
            if del_resp.status_code != 200:
                raise RuntimeError(
                    f"Failed to delete reservation {res['id']}: {del_resp.status_code} {del_resp.text}"
                )
        if reservations:
            print(f"Cleaned up {len(reservations)} existing reservations.")

    def book(self, share_id: str, start: str, end: str, cabin: str, guest_count: int = 0) -> httpx.Response:
        client = self.get_family_client(share_id)
        return client.post("/api/reservations", json={
            "share": share_id,
            "guest_count": guest_count,
            "start_date": start,
            "end_date": end,
            "cabins": [cabin],
            "is_day_use": False,
        })

    def get_booking_status(self, share_id: str) -> dict:
        client = self.get_family_client(share_id)
        resp = client.get("/api/booking-status")
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to get booking status for {share_id}: {resp.status_code} {resp.text}")
        return resp.json()

    def delete_reservation(self, reservation_id: int, share_id: str | None = None):
        """Delete a reservation. Uses admin client if share_id is None."""
        client = self._get_admin_client() if share_id is None else self.get_family_client(share_id)
        resp = client.delete(f"/api/reservations/{reservation_id}")
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to delete reservation {reservation_id}: {resp.status_code} {resp.text}")

    def assert_booking_succeeds(self, share_id: str, start: str, end: str, cabin: str,
                                expected_round: str, label: str = "") -> dict:
        resp = self.book(share_id, start, end, cabin)
        nights = _nights(start, end)
        desc = f"{label}Booked {start} to {end} {cabin} ({nights}n)"
        if resp.status_code == 200:
            data = resp.json()
            actual_round = data.get("booking_round", "")
            if actual_round == expected_round:
                self.result.ok(f"{desc} \u2192 {actual_round}")
            else:
                self.result.fail(f"{desc}: expected round={expected_round}, got {actual_round}")
            return data
        else:
            self.result.fail(f"{desc}: expected 200, got {resp.status_code}: {resp.text}")
            return {}

    def assert_booking_rejected(self, share_id: str, start: str, end: str, cabin: str,
                                 expected_substr: str = "", label: str = ""):
        resp = self.book(share_id, start, end, cabin)
        desc = f"{label}Booking {start} to {end} {cabin}"
        if resp.status_code == 400:
            detail = resp.json().get("detail", "")
            if expected_substr and expected_substr.lower() not in detail.lower():
                self.result.fail(f"{desc}: got 400 but message mismatch. "
                                 f"Expected '{expected_substr}' in '{detail}'")
            else:
                short_detail = detail[:80] + ("..." if len(detail) > 80 else "")
                self.result.ok(f"{desc} rejected: \"{short_detail}\"")
        else:
            self.result.fail(f"{desc}: expected 400, got {resp.status_code}: {resp.text}")

    def assert_status(self, share_id: str, expected_round: str, can_book: bool | None = None,
                      window_start: str | None = None, window_end: str | None = None,
                      label: str = ""):
        status = self.get_booking_status(share_id)
        parts = []
        ok = True

        actual_round = status.get("current_round", "")
        if actual_round != expected_round:
            parts.append(f"round: expected {expected_round}, got {actual_round}")
            ok = False
        else:
            parts.append(f"round={actual_round}")

        if can_book is not None:
            actual_can = status.get("can_book", None)
            if actual_can != can_book:
                parts.append(f"can_book: expected {can_book}, got {actual_can}")
                ok = False
            else:
                parts.append(f"can_book={actual_can}")

        if window_start is not None:
            actual_ws = status.get("window_start", "")
            if actual_ws != window_start:
                parts.append(f"window_start: expected {window_start}, got {actual_ws}")
                ok = False

        if window_end is not None:
            actual_we = status.get("window_end", "")
            if actual_we != window_end:
                parts.append(f"window_end: expected {window_end}, got {actual_we}")
                ok = False

        if window_start and window_end and ok:
            parts.append(f"window={window_start} to {window_end}")

        desc = f"{label}booking-status: {', '.join(parts)}"
        if ok:
            self.result.ok(desc)
        else:
            self.result.fail(desc)

    def close(self):
        if self._admin_client:
            self._admin_client.close()
        for c in self._family_clients.values():
            c.close()


def _nights(start: str, end: str) -> int:
    from datetime import date
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def _family_name(share_id: str) -> str:
    return next((f[1] for f in FAMILIES if f[0] == share_id), share_id)


# ---------------------------------------------------------------------------
# Simulation phases
# ---------------------------------------------------------------------------

def phase_preseason(sim: BookingSimulator):
    """Verify offseason rules before Round 1 starts."""
    sim.result.header("PRE-SEASON (Mar 31, 2026)")
    sim.set_date("2026-03-31")

    # Alder attempts a prime-season booking -> should fail
    sim.result.subheader("[Mar 31] Alder tries prime-season booking")
    sim.assert_booking_rejected(
        "alder", "2026-06-01", "2026-06-04", "pine",
        expected_substr="prime season",
        label="Alder: ",
    )

    # Alder books a non-prime date -> should succeed, then we delete it
    sim.result.subheader("[Mar 31] Alder books non-prime date")
    resp = sim.book("alder", "2026-03-01", "2026-03-03", "pine")
    if resp.status_code == 200:
        res_id = resp.json()["id"]
        sim.result.ok(f"Alder booked non-prime Mar 01-03 pine (offseason) \u2192 id={res_id}")
        sim.delete_reservation(res_id)
        sim.result.ok("Deleted test offseason reservation")
    else:
        sim.result.fail(f"Alder non-prime booking failed: {resp.status_code} {resp.text}")


def phase_round1(sim: BookingSimulator):
    """Round 1: all 9 families, priority order, 2-day windows, max 2 reservations, max 10 nights."""
    sim.result.header("ROUND 1: Priority Order (Apr 1-18)")

    families_priority = list(FAMILIES)  # already in priority order

    for i, (share_id, name, email, priority) in enumerate(families_priority):
        window_start, window_end = ROUND1_WINDOWS[share_id]
        sim.set_date(window_start)

        sim.result.subheader(f"[{window_start}] {name} (priority {priority}) \u2014 Window: {window_start} to {window_end}")

        # 1. Check booking status
        sim.assert_status(
            share_id,
            expected_round="round_1",
            can_book=True,
            window_start=window_start,
            window_end=window_end,
            label=f"{name}: ",
        )

        # 2. Make the booking
        start, end, cabin = ROUND1_BOOKINGS[share_id]
        sim.assert_booking_succeeds(
            share_id, start, end, cabin,
            expected_round="round_1",
            label=f"{name}: ",
        )

        # 3. Wrong-family rejection: the next family tries to book during this window
        if i < len(families_priority) - 1:
            next_share = families_priority[i + 1][0]
            next_name = families_priority[i + 1][1]
            ns, ne, nc = ROUND1_BOOKINGS[next_share]
            sim.assert_booking_rejected(
                next_share, ns, ne, nc,
                expected_substr="window",
                label=f"{next_name} (wrong window): ",
            )

        # 4. Spot-check: Alder makes 2nd booking on day 2, then tries 3rd (should fail)
        if share_id == "alder":
            sim.result.subheader(f"[{window_end}] Alder day 2: 2nd booking + 3rd attempt")
            sim.set_date(window_end)

            s2, e2, c2 = ALDER_ROUND1_SECOND
            sim.assert_booking_succeeds(
                "alder", s2, e2, c2,
                expected_round="round_1",
                label="Alder 2nd: ",
            )

            # 3rd attempt should fail (max 2)
            sim.assert_booking_rejected(
                "alder", "2026-07-01", "2026-07-04", "pine",
                expected_substr="already made",
                label="Alder 3rd attempt: ",
            )


def phase_between_r1_r2(sim: BookingSimulator):
    """Verify booking is blocked between Round 1 and Round 2 for prime dates, but allowed for non-prime."""
    sim.result.header("BETWEEN ROUNDS (Apr 19)")
    sim.set_date("2026-04-19")

    # Prime-season booking should be blocked
    sim.assert_booking_rejected(
        "alder", "2026-07-20", "2026-07-23", "pine",
        expected_substr="not open",
        label="Alder (prime): ",
    )

    sim.assert_status(
        "alder",
        expected_round="between_rounds",
        can_book=False,
        label="Alder: ",
    )

    # Non-prime booking should succeed even between rounds
    sim.result.subheader("[Apr 19] Non-prime booking allowed between rounds")
    resp = sim.book("alder", "2026-10-01", "2026-10-04", "pine")
    if resp.status_code == 200:
        res_id = resp.json()["id"]
        sim.result.ok(f"Alder booked non-prime Oct 01-04 pine between rounds → id={res_id}")
        sim.delete_reservation(res_id)
    else:
        sim.result.fail(f"Alder non-prime between-rounds booking failed: {resp.status_code} {resp.text}")


def phase_round2(sim: BookingSimulator):
    """Round 2: reverse priority order, 2-day windows, max 1 reservation."""
    sim.result.header("ROUND 2: Reverse Priority (Apr 20 - May 7)")

    # Round 2 order: Fir(9) -> Elm(8) -> ... -> Alder(1)
    families_reverse = list(reversed(FAMILIES))

    for i, (share_id, name, email, priority) in enumerate(families_reverse):
        window_start, window_end = ROUND2_WINDOWS[share_id]
        sim.set_date(window_start)

        sim.result.subheader(f"[{window_start}] {name} (priority {priority}) \u2014 Window: {window_start} to {window_end}")

        # 1. Check booking status
        sim.assert_status(
            share_id,
            expected_round="round_2",
            can_book=True,
            window_start=window_start,
            window_end=window_end,
            label=f"{name}: ",
        )

        # 2. Make the booking
        start, end, cabin = ROUND2_BOOKINGS[share_id]
        sim.assert_booking_succeeds(
            share_id, start, end, cabin,
            expected_round="round_2",
            label=f"{name}: ",
        )

        # 3. Wrong-family rejection: a family whose window hasn't started yet
        if i < len(families_reverse) - 1:
            next_share = families_reverse[i + 1][0]
            next_name = families_reverse[i + 1][1]
            ns, ne, nc = ROUND2_BOOKINGS[next_share]
            sim.assert_booking_rejected(
                next_share, ns, ne, nc,
                expected_substr="window",
                label=f"{next_name} (wrong window): ",
            )

        # 4. Spot-check: after booking, same family tries 2nd -> should fail (max 1)
        if share_id == "fir":
            sim.assert_booking_rejected(
                "fir", "2026-07-15", "2026-07-18", "cedar",
                expected_substr="already made",
                label="Fir 2nd attempt: ",
            )


def phase_between_r2_r3(sim: BookingSimulator):
    """Verify blocking between Round 2 and Round 3 for prime dates, but allowed for non-prime."""
    sim.result.header("BETWEEN ROUNDS (May 8)")
    sim.set_date("2026-05-08")

    # Prime-season booking should be blocked
    sim.assert_booking_rejected(
        "alder", "2026-07-20", "2026-07-23", "pine",
        expected_substr="not open",
        label="Alder (prime): ",
    )

    sim.assert_status(
        "birch",
        expected_round="between_rounds",
        can_book=False,
        label="Birch: ",
    )

    # Non-prime booking should succeed even between rounds
    sim.result.subheader("[May 8] Non-prime booking allowed between rounds")
    resp = sim.book("birch", "2026-10-05", "2026-10-08", "cedar")
    if resp.status_code == 200:
        res_id = resp.json()["id"]
        sim.result.ok(f"Birch booked non-prime Oct 05-08 cedar between rounds → id={res_id}")
        sim.delete_reservation(res_id)
    else:
        sim.result.fail(f"Birch non-prime between-rounds booking failed: {resp.status_code} {resp.text}")


def phase_round3(sim: BookingSimulator):
    """Round 3: priority order, 1-day windows, max 1 reservation."""
    sim.result.header("ROUND 3: Priority Order, 1-Day Windows (May 10-18)")

    families_priority = list(FAMILIES)

    for i, (share_id, name, email, priority) in enumerate(families_priority):
        window_start, window_end = ROUND3_WINDOWS[share_id]
        sim.set_date(window_start)

        sim.result.subheader(f"[{window_start}] {name} (priority {priority}) \u2014 Window: {window_start}")

        # 1. Check booking status
        sim.assert_status(
            share_id,
            expected_round="round_3",
            can_book=True,
            window_start=window_start,
            window_end=window_end,
            label=f"{name}: ",
        )

        # 2. Make the booking
        start, end, cabin = ROUND3_BOOKINGS[share_id]
        sim.assert_booking_succeeds(
            share_id, start, end, cabin,
            expected_round="round_3",
            label=f"{name}: ",
        )

        # 3. Wrong-family rejection
        if i < len(families_priority) - 1:
            next_share = families_priority[i + 1][0]
            next_name = families_priority[i + 1][1]
            ns, ne, nc = ROUND3_BOOKINGS[next_share]
            sim.assert_booking_rejected(
                next_share, ns, ne, nc,
                expected_substr="window",
                label=f"{next_name} (wrong window): ",
            )


def phase_between_r3_open(sim: BookingSimulator):
    """Verify blocking between Round 3 and Open Season for prime dates, but allowed for non-prime."""
    sim.result.header("BETWEEN ROUNDS (May 19)")
    sim.set_date("2026-05-19")

    # Prime-season booking should be blocked
    sim.assert_booking_rejected(
        "alder", "2026-07-20", "2026-07-23", "pine",
        expected_substr="not open",
        label="Alder (prime): ",
    )

    sim.assert_status(
        "oak",
        expected_round="between_rounds",
        can_book=False,
        label="Oak: ",
    )

    # Non-prime booking should succeed even between rounds
    sim.result.subheader("[May 19] Non-prime booking allowed between rounds")
    resp = sim.book("oak", "2026-10-10", "2026-10-13", "pine")
    if resp.status_code == 200:
        res_id = resp.json()["id"]
        sim.result.ok(f"Oak booked non-prime Oct 10-13 pine between rounds → id={res_id}")
        sim.delete_reservation(res_id)
    else:
        sim.result.fail(f"Oak non-prime between-rounds booking failed: {resp.status_code} {resp.text}")


def phase_open_season(sim: BookingSimulator):
    """Open Season: first-come-first-serve, 30-day advance limit, cabin conflicts (night cap lifted)."""
    sim.result.header("OPEN SEASON (May 22+)")
    sim.set_date("2026-05-22")

    # 30-day advance booking limit
    sim.result.subheader("[May 22] 30-day advance booking limit")

    sim.assert_status(
        "alder",
        expected_round="open",
        can_book=True,
        label="Alder: ",
    )

    # Reject: start date >30 days out (Jul 1 = 40 days from May 22)
    sim.assert_booking_rejected(
        "alder", "2026-07-01", "2026-07-04", "pine",
        expected_substr="30 days in advance",
        label="Alder (>30 days out): ",
    )

    # Accept: start date exactly 30 days out (Jun 21 = 30 days from May 22)
    exactly_30 = sim.assert_booking_succeeds(
        "alder", "2026-06-21", "2026-06-24", "cedar",
        expected_round="open",
        label="Alder (exactly 30 days): ",
    )
    if exactly_30.get("id"):
        sim.delete_reservation(exactly_30["id"])

    # Multiple families book on the same day (dates within 30 days of May 22)
    sim.result.subheader("[May 22] Multiple families book on the same day")

    # Alder has 3 (R1) + 3 (R1 2nd) + 3 (R2) + 2 (R3) = 11 prime nights, 7 remaining.
    alder_open = sim.assert_booking_succeeds(
        "alder", "2026-05-25", "2026-05-28", "cedar",
        expected_round="open",
        label="Alder: ",
    )

    birch_open = sim.assert_booking_succeeds(
        "birch", "2026-05-25", "2026-05-28", "pine",
        expected_round="open",
        label="Birch: ",
    )

    # Cabin conflict: Oak tries the same cabin+dates as Birch
    sim.result.subheader("[May 22] Cabin conflict test")
    sim.assert_booking_rejected(
        "oak", "2026-05-25", "2026-05-28", "pine",
        expected_substr="conflict",
        label="Oak (conflict with Birch): ",
    )

    # Non-prime booking during open season should succeed
    sim.result.subheader("[May 22] Non-prime booking during open season")
    resp = sim.book("alder", "2026-10-05", "2026-10-08", "pine")
    if resp.status_code == 200:
        nonprime_id = resp.json()["id"]
        sim.result.ok(f"Alder booked non-prime Oct 05-08 pine during open season → id={nonprime_id}")
        sim.delete_reservation(nonprime_id)
    else:
        sim.result.fail(f"Alder non-prime open-season booking failed: {resp.status_code} {resp.text}")

    # Clean up open-season test bookings before straddle test
    if alder_open.get("id"):
        sim.delete_reservation(alder_open["id"])
    if birch_open.get("id"):
        sim.delete_reservation(birch_open["id"])

    # Straddling booking: spans prime boundary (Sep 28 - Oct 2)
    # Advance to Sep 1 so dates are within 30-day limit.
    # Alder has 11 prime nights (3+3+3+2 from rounds). 4 total nights but only 2 prime (Sep 28-30).
    # 11 + 2 = 13 <= 18, should succeed.
    sim.result.subheader("[Sep 1] Straddling prime boundary booking (only prime nights counted)")
    sim.set_date("2026-09-01")
    straddle = sim.assert_booking_succeeds(
        "alder", "2026-09-28", "2026-10-02", "cedar",
        expected_round="open",
        label="Alder (straddle): ",
    )
    if straddle.get("id"):
        sim.delete_reservation(straddle["id"])


def phase_post_season(sim: BookingSimulator):
    """Verify offseason rules return after open season ends."""
    sim.result.header("POST-SEASON (Sep 8)")
    sim.set_date("2026-09-08")

    sim.assert_status(
        "alder",
        expected_round="offseason",
        can_book=True,
        label="Alder: ",
    )

    # Prime-season booking should still work in offseason if dates are available
    # Actually the post-season for THIS year's open_season_end is Sep 7,
    # so Sep 8 is offseason. But prime_season_end is Sep 30.
    # Offseason + overlapping prime season = should be blocked.
    sim.assert_booking_rejected(
        "birch", "2026-09-20", "2026-09-23", "cedar",
        expected_substr="prime season",
        label="Birch (prime dates in offseason): ",
    )

    # Non-prime booking should succeed
    resp = sim.book("birch", "2026-10-01", "2026-10-03", "pine")
    if resp.status_code == 200:
        res_id = resp.json()["id"]
        sim.result.ok(f"Birch booked non-prime Oct 01-03 pine (offseason) \u2192 id={res_id}")
        sim.delete_reservation(res_id)
    else:
        sim.result.fail(f"Birch non-prime booking failed: {resp.status_code} {resp.text}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not PASSWORD:
        print("ERROR: SEED_PASSWORD environment variable must be set.")
        sys.exit(1)

    # Verify backend is reachable
    try:
        resp = httpx.get(f"{BASE_URL}/api/auth/check", timeout=5)
    except httpx.ConnectError:
        print(f"ERROR: Cannot connect to backend at {BASE_URL}")
        print("Make sure the backend is running: uvicorn main:app --reload")
        sys.exit(1)

    result = SimulationResult()
    sim = BookingSimulator(result)

    try:
        print(f"Connecting to {BASE_URL}...")
        print("Cleaning up existing reservations...")
        sim.cleanup_reservations()

        phase_preseason(sim)
        phase_round1(sim)
        phase_between_r1_r2(sim)
        phase_round2(sim)
        phase_between_r2_r3(sim)
        phase_round3(sim)
        phase_between_r3_open(sim)
        phase_open_season(sim)
        phase_post_season(sim)

    except Exception as e:
        result.fail(f"Simulation aborted with error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Always clear time-travel and close clients
        try:
            sim.clear_date()
            print("\nTime-travel cleared.")
        except Exception:
            print("\nWARNING: Failed to clear time-travel date.")
        sim.close()

    result.print_all()
    sys.exit(1 if result.failed > 0 else 0)


if __name__ == "__main__":
    main()
