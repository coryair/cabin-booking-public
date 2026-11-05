"""
Reservation reminder cron regression tests for time travel support.

Verifies:
- /api/cron/send-reservation-reminders uses simulated date from /api/time-travel
- reminders send at exactly 7 days, 3 days, and day-of
- each reminder offset is idempotent on repeated cron runs

Usage:
    cd backend && source venv/bin/activate
    SEED_PASSWORD=<password> SU_PASSWORD=<password> python tests/cron_reservation_reminder_time_travel_regression.py
"""

import os
import sys
import httpx

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
SEED_PASSWORD = os.environ.get("SEED_PASSWORD", "")
SU_PASSWORD = os.environ.get("SU_PASSWORD", SEED_PASSWORD)
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")


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


def create_reservation(client: httpx.Client, start: str, end: str, cabin: str) -> httpx.Response:
    return client.post("/api/reservations", json={
        "share": "",  # backend resolves this from current session
        "guest_count": 0,
        "start_date": start,
        "end_date": end,
        "cabins": [cabin],
        "is_day_use": False,
    })


def delete_reservation(client: httpx.Client, reservation_id: int):
    resp = client.delete(f"/api/reservations/{reservation_id}")
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to delete reservation {reservation_id}: {resp.status_code} {resp.text}")


def run_reminder_cron() -> httpx.Response:
    return httpx.get(f"{BASE_URL}/api/cron/send-reservation-reminders", timeout=30)


def assert_sent_count(result: Result, resp: httpx.Response, label: str, minimum: int, maximum: int | None = None) -> bool:
    if not assert_status(result, resp, 200, label):
        return False
    try:
        sent = int((resp.json() or {}).get("sent", -1))
    except Exception:
        result.fail(f"{label}: response did not contain integer 'sent': {resp.text}")
        return False
    if sent < minimum:
        result.fail(f"{label}: expected sent >= {minimum}, got {sent}")
        return False
    if maximum is not None and sent > maximum:
        result.fail(f"{label}: expected sent <= {maximum}, got {sent}")
        return False
    result.ok(f"{label}: sent={sent}")
    return True


def main():
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
    admin = None
    reservation_id: int | None = None

    # Use far-future dates to avoid collisions with normal seeded scenarios.
    checkin = "2099-01-08"
    checkout = "2099-01-10"

    try:
        result.section("Login")
        admin = login(ADMIN_EMAIL, SU_PASSWORD)
        result.ok("Logged in admin")

        result.section("Create Reservation")
        clear_date(admin)
        create = create_reservation(admin, checkin, checkout, "pine")
        if not assert_status(result, create, 200, "Admin creates future reservation"):
            raise RuntimeError("Cannot continue without reservation")
        reservation_id = int(create.json()["id"])
        result.ok(f"Created reservation id={reservation_id} ({checkin} -> {checkout})")

        result.section("7-Day Reminder Uses Simulated Date")
        set_date(admin, "2099-01-01")
        assert_sent_count(result, run_reminder_cron(), "First cron run at T-7 sends reminder", minimum=1)
        assert_sent_count(result, run_reminder_cron(), "Second cron run at T-7 is idempotent", minimum=0, maximum=0)

        result.section("3-Day Reminder Uses Simulated Date")
        set_date(admin, "2099-01-05")
        assert_sent_count(result, run_reminder_cron(), "First cron run at T-3 sends reminder", minimum=1)
        assert_sent_count(result, run_reminder_cron(), "Second cron run at T-3 is idempotent", minimum=0, maximum=0)

        result.section("Day-Of Reminder Uses Simulated Date")
        set_date(admin, "2099-01-08")
        assert_sent_count(result, run_reminder_cron(), "First cron run day-of sends reminder", minimum=1)
        assert_sent_count(result, run_reminder_cron(), "Second cron run day-of is idempotent", minimum=0, maximum=0)

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

        if admin is not None:
            admin.close()

    result.print()
    sys.exit(1 if result.failed else 0)


if __name__ == "__main__":
    main()
