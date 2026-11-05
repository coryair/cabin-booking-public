"""
Reservation cancellation notice-window regression checks.

Verifies:
- Confirmed reservations cannot be cancelled within 15 days of check-in.
- The POST /cancel and DELETE cancellation paths both enforce the window.
- Admin status edits cannot bypass the cancellation window.

Usage:
    cd backend && source venv/bin/activate
    SEED_PASSWORD=<password> SU_PASSWORD=<password> python tests/reservation_cancellation_window_regression.py
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


def assert_status(result: Result, resp: httpx.Response, expected: int, label: str) -> bool:
    if resp.status_code != expected:
        result.fail(f"{label}: expected HTTP {expected}, got {resp.status_code}: {resp.text}")
        return False
    result.ok(f"{label}: HTTP {expected}")
    return True


def assert_detail_contains(result: Result, resp: httpx.Response, expected: str, label: str) -> bool:
    try:
        detail = resp.json().get("detail", "")
    except Exception:
        detail = resp.text

    if expected not in detail:
        result.fail(f"{label}: expected detail containing {expected!r}, got {detail!r}")
        return False

    result.ok(f"{label}: detail includes {expected!r}")
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


def create_reservation(client: httpx.Client, *, start: str, end: str, cabin: str) -> httpx.Response:
    return client.post("/api/reservations", json={
        "share": "",
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


def clear_all_reservations(admin: httpx.Client):
    resp = admin.get("/api/reservations")
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to list reservations: {resp.status_code} {resp.text}")
    for res in resp.json():
        delete_reservation(admin, int(res["id"]))


def get_reservation(client: httpx.Client, reservation_id: int) -> httpx.Response:
    return client.get(f"/api/reservations/{reservation_id}")


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
    created_ids: list[int] = []

    try:
        result.section("Login and setup")
        admin = login(ADMIN_EMAIL, SU_PASSWORD)
        alder = login(ALDER_EMAIL, SEED_PASSWORD)
        result.ok("Logged in admin and alder")

        clear_date(admin)
        set_date(admin, "2026-01-01")
        clear_all_reservations(admin)
        set_date(admin, "2026-02-10")
        result.ok("Cleared reservations and set initial simulated date")

        resp = create_reservation(
            alder,
            start="2026-03-01",
            end="2026-03-03",
            cabin="pine",
        )
        if not assert_status(result, resp, 200, "Owner creates reservation outside cancellation cutoff"):
            raise RuntimeError("Cannot continue without baseline reservation")
        reservation_id = int(resp.json()["id"])
        created_ids.append(reservation_id)

        set_date(admin, "2026-02-20")
        result.ok("Moved simulated date inside the 15-day cancellation window")

        result.section("Self-service cancellation is blocked within 15 days")
        resp = alder.post(f"/api/reservations/{reservation_id}/cancel")
        assert_status(result, resp, 400, "POST /cancel is blocked inside 15 days")
        assert_detail_contains(result, resp, "aren't allowed within 15 days", "POST /cancel explains the policy")

        resp = alder.delete(f"/api/reservations/{reservation_id}")
        assert_status(result, resp, 400, "DELETE cancel path is blocked inside 15 days")
        assert_detail_contains(result, resp, "aren't allowed within 15 days", "DELETE cancel explains the policy")

        result.section("Admin status edits cannot bypass the cutoff")
        resp = admin.put(f"/api/reservations/{reservation_id}", json={"status": "cancelled"})
        assert_status(result, resp, 400, "Admin cannot set status=cancelled inside 15 days")
        assert_detail_contains(result, resp, "aren't allowed within 15 days", "Admin status edit explains the policy")

        resp = get_reservation(alder, reservation_id)
        if assert_status(result, resp, 200, "Owner can still fetch reservation after blocked cancellations"):
            status = resp.json().get("status")
            if status not in ("cancelled", "refunded"):
                result.ok("Blocked cancellations left reservation active")
            else:
                result.fail(f"Reservation was unexpectedly changed to status={status}")

    except Exception as exc:
        result.fail(f"Aborted due to error: {exc}")
    finally:
        if admin:
            try:
                set_date(admin, "2026-01-01")
            except Exception:
                pass
            for reservation_id in list(created_ids):
                try:
                    delete_reservation(admin, reservation_id)
                except Exception:
                    pass
            try:
                clear_date(admin)
            except Exception:
                pass
        if alder:
            alder.close()
        if admin:
            admin.close()

    result.print()
    if result.failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
