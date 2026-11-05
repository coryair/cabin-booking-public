"""
Payment gating regression checks.

Verifies:
- standard users cannot create confirmed reservations directly through POST /api/reservations
- admin-controlled time travel still permits direct-create test seeding
- unpaid reservations appear on the calendar as payment-due holds

Usage:
    cd backend && source venv/bin/activate
    SEED_PASSWORD=<password> SU_PASSWORD=<password> python tests/payment_gating_regression.py
"""

import os
import sys

import httpx

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
SEED_PASSWORD = os.environ.get("SEED_PASSWORD", "")
SU_PASSWORD = os.environ.get("SU_PASSWORD", SEED_PASSWORD)

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")
ALDER_EMAIL = os.environ.get("ALDER_EMAIL", "alder@example.com")


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


def set_date(admin: httpx.Client, value: str):
    resp = admin.post("/api/time-travel", json={"date": value})
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to set time-travel date {value}: {resp.status_code} {resp.text}")


def clear_date(admin: httpx.Client):
    resp = admin.delete("/api/time-travel")
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to clear time-travel: {resp.status_code} {resp.text}")


def create_reservation(client: httpx.Client, start: str, end: str, cabin: str) -> httpx.Response:
    return client.post("/api/reservations", json={
        "share": "",
        "guest_count": 0,
        "start_date": start,
        "end_date": end,
        "cabins": [cabin],
        "is_day_use": False,
    })


def update_reservation(client: httpx.Client, reservation_id: int, payload: dict) -> httpx.Response:
    return client.put(f"/api/reservations/{reservation_id}", json=payload)


def delete_reservation(client: httpx.Client, reservation_id: int):
    resp = client.delete(f"/api/reservations/{reservation_id}")
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to delete reservation {reservation_id}: {resp.status_code} {resp.text}")


def get_calendar_day(client: httpx.Client, year: int, month: int, date_str: str) -> dict:
    resp = client.get(f"/api/calendar/{year}/{month}")
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to fetch calendar: {resp.status_code} {resp.text}")
    for day in resp.json().get("days", []):
        if day.get("date") == date_str:
            return day
    raise RuntimeError(f"Calendar day not found: {date_str}")


def has_reservation(day: dict, reservation_id: int) -> bool:
    return any(int(row.get("id")) == reservation_id for row in day.get("reservations", []))


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
    admin = alder = None
    reservation_id: int | None = None

    try:
        result.section("Login")
        admin = login(ADMIN_EMAIL, SU_PASSWORD)
        alder = login(ALDER_EMAIL, SEED_PASSWORD)
        result.ok("Logged in admin + alder")

        result.section("Direct user create requires checkout")
        clear_date(admin)
        blocked = create_reservation(alder, "2026-02-20", "2026-02-21", "pine")
        assert_status(result, blocked, 403, "Direct POST blocked outside simulation", "checkout")

        result.section("Unpaid reservations appear as calendar holds")
        set_date(admin, "2026-02-10")
        created = create_reservation(alder, "2026-02-20", "2026-02-21", "pine")
        if not assert_status(result, created, 200, "Direct POST allowed during simulation"):
            raise RuntimeError("Cannot continue without simulated reservation")

        reservation_id = int(created.json()["id"])
        day = get_calendar_day(alder, 2026, 2, "2026-02-20")
        if has_reservation(day, reservation_id):
            result.ok("Unpaid reservation appears on calendar")
        else:
            result.fail("Unpaid reservation missing from calendar")

        unpaid_rows = [row for row in day.get("reservations", []) if int(row.get("id")) == reservation_id]
        if unpaid_rows and unpaid_rows[0].get("status") == "unpaid":
            result.ok("Calendar reservation includes unpaid status")
        else:
            result.fail(f"Expected unpaid calendar status, got {unpaid_rows[0].get('status') if unpaid_rows else 'missing'}")

        paid = update_reservation(admin, reservation_id, {"status": "paid"})
        if not assert_status(result, paid, 200, "Admin can promote reservation to paid"):
            raise RuntimeError("Cannot continue without paid reservation")

        day = get_calendar_day(alder, 2026, 2, "2026-02-20")
        if has_reservation(day, reservation_id):
            result.ok("Paid reservation appears on calendar")
        else:
            result.fail("Paid reservation missing from calendar")

    except Exception as exc:
        result.fail(f"Aborted due to error: {exc}")
    finally:
        try:
            if admin is not None and reservation_id is not None:
                delete_reservation(admin, reservation_id)
                result.ok(f"Cleanup deleted reservation id={reservation_id}")
        except Exception as cleanup_err:
            result.fail(f"Cleanup failed: {cleanup_err}")

        try:
            if admin is not None:
                clear_date(admin)
                result.ok("Cleanup cleared simulated date")
        except Exception as cleanup_err:
            result.fail(f"Cleanup failed clearing simulated date: {cleanup_err}")

        for client in [admin, alder]:
            if client is not None:
                client.close()

    result.print()
    sys.exit(1 if result.failed > 0 else 0)


if __name__ == "__main__":
    main()
