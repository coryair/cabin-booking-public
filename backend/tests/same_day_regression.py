"""
Same-day reservation regression tests for finding #3.

Verifies:
- start_date == end_date is normalized to day-use (end_date + 1 day)
- same-day requests cannot bypass conflict checks
- normalized same-day bookings count toward round night caps
- availability/calendar endpoints behave correctly with normalized day-use bookings

Usage:
    cd backend && source venv/bin/activate
    SEED_PASSWORD=<password> SU_PASSWORD=<password> python tests/same_day_regression.py
"""

import os
import sys
import httpx

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
SEED_PASSWORD = os.environ.get("SEED_PASSWORD", "")
SU_PASSWORD = os.environ.get("SU_PASSWORD", SEED_PASSWORD)

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")
ALDER_EMAIL = os.environ.get("ALDER_EMAIL", "alder@example.com")
BIRCH_EMAIL = os.environ.get("BIRCH_EMAIL", "birch@example.com")


class Result:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.lines: list[str] = []

    def ok(self, msg: str):
        self.passed += 1
        self.lines.append(f"  [PASS] {msg}")

    def fail(self, msg: str):
        self.failed += 1
        self.lines.append(f"  [FAIL] {msg}")

    def section(self, msg: str):
        self.lines.append(f"\n=== {msg} ===")

    def print(self):
        for line in self.lines:
            print(line)
        print(f"\nSummary: {self.passed + self.failed} checks, {self.passed} passed, {self.failed} failed")


def assert_status(
    result: Result,
    resp: httpx.Response,
    expected_status: int,
    label: str,
    expected_substr: str | None = None,
) -> bool:
    if resp.status_code != expected_status:
        result.fail(f"{label}: expected HTTP {expected_status}, got {resp.status_code}: {resp.text}")
        return False
    if expected_substr:
        detail = ""
        try:
            detail = (resp.json() or {}).get("detail", "")
        except Exception:
            detail = resp.text
        if expected_substr.lower() not in detail.lower():
            result.fail(f"{label}: expected '{expected_substr}' in '{detail}'")
            return False
    result.ok(f"{label}: HTTP {expected_status}")
    return True


def login(email: str, password: str) -> httpx.Client:
    client = httpx.Client(base_url=BASE_URL)
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        raise RuntimeError(f"Login failed for {email}: {resp.status_code} {resp.text}")
    return client


def set_date(admin: httpx.Client, d: str):
    resp = admin.post("/api/time-travel", json={"date": d})
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to set time-travel date {d}: {resp.status_code} {resp.text}")


def clear_date(admin: httpx.Client):
    resp = admin.delete("/api/time-travel")
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to clear time-travel: {resp.status_code} {resp.text}")


def list_reservations(client: httpx.Client) -> list[dict]:
    resp = client.get("/api/reservations")
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to list reservations: {resp.status_code} {resp.text}")
    return resp.json()


def delete_reservation(client: httpx.Client, reservation_id: int):
    resp = client.delete(f"/api/reservations/{reservation_id}")
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to delete reservation {reservation_id}: {resp.status_code} {resp.text}")


def clear_all_reservations(admin: httpx.Client):
    for res in list_reservations(admin):
        delete_reservation(admin, int(res["id"]))


def create_reservation(
    client: httpx.Client,
    start: str,
    end: str,
    cabin: str,
    is_day_use: bool = False,
    guest_count: int = 0,
) -> httpx.Response:
    return client.post("/api/reservations", json={
        "share": "",
        "guest_count": guest_count,
        "start_date": start,
        "end_date": end,
        "cabins": [cabin],
        "is_day_use": is_day_use,
    })


def update_reservation(client: httpx.Client, reservation_id: int, payload: dict) -> httpx.Response:
    return client.put(f"/api/reservations/{reservation_id}", json=payload)


def get_booking_status(client: httpx.Client) -> dict:
    resp = client.get("/api/booking-status")
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to fetch booking-status: {resp.status_code} {resp.text}")
    return resp.json()


def get_availability(client: httpx.Client, start: str, end: str) -> dict:
    resp = client.get("/api/availability", params={"start_date": start, "end_date": end})
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to fetch availability: {resp.status_code} {resp.text}")
    return resp.json()


def get_calendar(client: httpx.Client, year: int, month: int) -> dict:
    resp = client.get(f"/api/calendar/{year}/{month}")
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to fetch calendar: {resp.status_code} {resp.text}")
    return resp.json()


def day_entry(month_data: dict, target_date: str) -> dict:
    for d in month_data.get("days", []):
        if d.get("date") == target_date:
            return d
    raise RuntimeError(f"Calendar day not found: {target_date}")


def main():
    if not SEED_PASSWORD:
        print("ERROR: SEED_PASSWORD is required.")
        sys.exit(1)
    if not SU_PASSWORD:
        print("ERROR: SU_PASSWORD is required.")
        sys.exit(1)

    try:
        health = httpx.get(f"{BASE_URL}/health", timeout=5)
        if health.status_code != 200:
            print(f"ERROR: Backend not healthy at {BASE_URL}: {health.status_code}")
            sys.exit(1)
    except Exception:
        print(f"ERROR: Cannot connect to backend at {BASE_URL}")
        print("Start backend first (e.g. `uvicorn main:app --reload` from backend/).")
        sys.exit(1)

    result = Result()
    admin = alder = birch = None
    created_ids: list[int] = []

    try:
        result.section("Login")
        admin = login(ADMIN_EMAIL, SU_PASSWORD)
        alder = login(ALDER_EMAIL, SEED_PASSWORD)
        birch = login(BIRCH_EMAIL, SEED_PASSWORD)
        result.ok("Logged in admin + alder + birch")

        clear_date(admin)

        result.section("Fresh start")
        clear_all_reservations(admin)
        remaining = len(list_reservations(admin))
        if remaining == 0:
            result.ok("All reservations cleared")
        else:
            result.fail(f"Expected empty reservations table, found {remaining}")

        result.section("Round-night counting for same-day normalization")
        set_date(admin, "2026-04-01")  # Alder Round 1 window
        same_day_prime = create_reservation(
            alder,
            start="2026-06-01",
            end="2026-06-01",
            cabin="pine",
            is_day_use=False,
        )
        if assert_status(result, same_day_prime, 200, "Same-day prime booking succeeds"):
            body = same_day_prime.json()
            res_id = int(body["id"])
            created_ids.append(res_id)
            if body.get("is_day_use") is True:
                result.ok("Same-day booking normalized to day-use")
            else:
                result.fail(f"Expected is_day_use=true, got {body.get('is_day_use')}")
            if body.get("end_date") == "2026-06-02":
                result.ok("Same-day booking normalized to end_date + 1 day")
            else:
                result.fail(f"Expected end_date 2026-06-02, got {body.get('end_date')}")

            status = get_booking_status(alder)
            if status.get("nights_used") == 1:
                result.ok("Normalized same-day booking counts as 1 night in booking status")
            else:
                result.fail(f"Expected nights_used=1, got {status.get('nights_used')}")

        # With 1 normalized night already used in Round 1, adding 10 should exceed max 10.
        ten_night_attempt = create_reservation(
            alder,
            start="2026-06-03",
            end="2026-06-13",
            cabin="cedar",
            is_day_use=False,
        )
        assert_status(  # message can vary; status code and rejection are key
            result,
            ten_night_attempt,
            400,
            "Round 1 max nights enforced after same-day normalization"
        )
        clear_date(admin)

        result.section("Conflict checks for same-day vs overnight")
        set_date(admin, "2026-02-10")  # Offseason, no round-window restrictions

        overnight = create_reservation(
            birch,
            start="2026-02-20",
            end="2026-02-21",
            cabin="pine",
            is_day_use=False,
        )
        if assert_status(result, overnight, 200, "Overnight baseline booking succeeds"):
            created_ids.append(int(overnight.json()["id"]))

        # Same-day request should normalize and conflict with overnight on same date/cabin.
        same_day_conflict = create_reservation(
            alder,
            start="2026-02-20",
            end="2026-02-20",
            cabin="pine",
            is_day_use=False,
        )
        assert_status(result, same_day_conflict, 400, "Same-day blocked by overnight conflict", "conflict")

        # Create normalized same-day day-use on a new date.
        day_use_norm = create_reservation(
            alder,
            start="2026-02-22",
            end="2026-02-22",
            cabin="pine",
            is_day_use=False,
        )
        day_use_norm_id = None
        if assert_status(result, day_use_norm, 200, "Normalized same-day day-use booking succeeds"):
            body = day_use_norm.json()
            day_use_norm_id = int(body["id"])
            created_ids.append(day_use_norm_id)
            if body.get("end_date") == "2026-02-23":
                result.ok("Day-use normalization persisted as [start, end+1)")
            else:
                result.fail(f"Expected normalized end_date 2026-02-23, got {body.get('end_date')}")

            paid_resp = update_reservation(admin, day_use_norm_id, {"status": "paid"})
            assert_status(result, paid_resp, 200, "Admin can mark normalized day-use reservation paid")

        overnight_conflict = create_reservation(
            birch,
            start="2026-02-22",
            end="2026-02-23",
            cabin="pine",
            is_day_use=False,
        )
        assert_status(result, overnight_conflict, 400, "Overnight blocked by normalized same-day conflict", "conflict")

        result.section("Multi-day day-use backend enforcement")
        multi_day_day_use = create_reservation(
            alder,
            start="2026-02-24",
            end="2026-02-26",
            cabin="cedar",
            is_day_use=True,
        )
        assert_status(
            result,
            multi_day_day_use,
            400,
            "Create rejects multi-day day-use",
            "single day"
        )

        if day_use_norm_id is not None:
            admin_multi_day_update = update_reservation(admin, day_use_norm_id, {
                "start_date": "2026-02-24",
                "end_date": "2026-02-26",
            })
            assert_status(
                result,
                admin_multi_day_update,
                400,
                "Update rejects expanding day-use to multi-day",
                "single day"
            )

        result.section("Availability and calendar behavior")
        avail = get_availability(alder, "2026-02-22", "2026-02-22")
        pine_open = avail.get("cabins", {}).get("pine")
        if pine_open is False:
            result.ok("Availability marks pine unavailable for same-day query")
        else:
            result.fail(f"Expected pine unavailable for same-day query, got {pine_open}")

        # Day-use booking should render on start day only, not the normalized end day.
        if day_use_norm_id is not None:
            cal = get_calendar(alder, 2026, 2)
            day_22 = day_entry(cal, "2026-02-22")
            day_23 = day_entry(cal, "2026-02-23")
            ids_22 = {r["id"] for r in day_22.get("reservations", [])}
            ids_23 = {r["id"] for r in day_23.get("reservations", [])}
            if day_use_norm_id in ids_22:
                result.ok("Normalized day-use appears on selected calendar day")
            else:
                result.fail("Normalized day-use missing from selected calendar day")
            if day_use_norm_id not in ids_23:
                result.ok("Normalized day-use does not appear on next day")
            else:
                result.fail("Normalized day-use incorrectly appears on next day")

        clear_date(admin)

    except Exception as exc:
        result.fail(f"Aborted due to error: {exc}")
    finally:
        try:
            if admin is not None:
                for rid in reversed(created_ids):
                    try:
                        delete_reservation(admin, rid)
                        result.ok(f"Cleanup deleted reservation id={rid}")
                    except Exception as cleanup_err:
                        result.fail(f"Cleanup failed for id={rid}: {cleanup_err}")
                # Leave DB in "fresh start" state per requested policy.
                clear_all_reservations(admin)
                result.ok("Final cleanup: reservations table cleared")
        finally:
            try:
                if admin is not None:
                    clear_date(admin)
            except Exception:
                pass
            for client in [admin, alder, birch]:
                if client is not None:
                    client.close()

    result.print()
    sys.exit(1 if result.failed > 0 else 0)


if __name__ == "__main__":
    main()
