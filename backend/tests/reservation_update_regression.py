"""
Reservation update regression tests for finding #2:
Reservation updates bypassing booking rules/payment integrity.

Runs against a live backend (same style as booking_simulation.py).

Usage:
    cd backend && source venv/bin/activate
    SEED_PASSWORD=<password> SU_PASSWORD=<password> python tests/reservation_update_regression.py
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


def create_reservation(
    client: httpx.Client,
    start: str,
    end: str,
    cabin: str,
    guest_count: int = 0,
) -> httpx.Response:
    return client.post("/api/reservations", json={
        "share": "",  # ignored by backend; share comes from session
        "guest_count": guest_count,
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


def set_date(admin: httpx.Client, d: str):
    resp = admin.post("/api/time-travel", json={"date": d})
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to set time-travel date {d}: {resp.status_code} {resp.text}")


def clear_date(admin: httpx.Client):
    resp = admin.delete("/api/time-travel")
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to clear time-travel: {resp.status_code} {resp.text}")


def cost_preview(
    client: httpx.Client,
    start: str,
    end: str,
    cabins: str,
    guest_count: int,
) -> float:
    resp = client.get(
        "/api/booking-cost",
        params={
            "start_date": start,
            "end_date": end,
            "cabins": cabins,
            "is_day_use": "false",
            "guest_count": str(guest_count),
        },
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to fetch booking cost: {resp.status_code} {resp.text}")
    return float(resp.json()["total"])


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

        # Keep this deterministic and outside prime-season locks while allowing
        # direct-create regression seeding through the admin-controlled
        # simulation path.
        set_date(admin, "2026-02-10")

        result.section("Seed test reservations")
        alder_create = create_reservation(alder, "2026-10-01", "2026-10-03", "pine", guest_count=0)
        if not assert_status(result, alder_create, 200, "Alder creates baseline reservation"):
            raise RuntimeError("Cannot continue without baseline reservation")
        alder_res = alder_create.json()
        alder_res_id = int(alder_res["id"])
        created_ids.append(alder_res_id)

        birch_create = create_reservation(birch, "2026-10-05", "2026-10-07", "pine", guest_count=0)
        if not assert_status(result, birch_create, 200, "Birch creates conflict target reservation"):
            raise RuntimeError("Cannot continue without conflict target reservation")
        birch_res_id = int(birch_create.json()["id"])
        created_ids.append(birch_res_id)

        result.section("Non-admin update restrictions")
        resp = update_reservation(alder, alder_res_id, {"status": "paid"})
        assert_status(result, resp, 403, "Alder cannot set status", "Only admins can update")

        resp = update_reservation(alder, alder_res_id, {"cost": 1.0})
        assert_status(result, resp, 403, "Alder cannot set cost", "Only admins can update")

        resp = update_reservation(alder, alder_res_id, {"start_date": "2026-10-02"})
        assert_status(result, resp, 403, "Alder cannot change dates", "Only admins can update")

        result.section("Server-side cost recompute")
        expected_total = cost_preview(alder, "2026-10-01", "2026-10-03", "pine", guest_count=2)
        resp = update_reservation(alder, alder_res_id, {"guest_count": 2})
        if assert_status(result, resp, 200, "Alder can update guest_count"):
            body = resp.json()
            actual_total = float(body["cost"])
            if abs(actual_total - expected_total) < 0.0001:
                result.ok(f"Cost recomputed server-side ({actual_total:.2f})")
            else:
                result.fail(f"Cost mismatch after update: expected {expected_total:.2f}, got {actual_total:.2f}")

        result.section("Admin field restrictions and allowed status updates")
        resp = update_reservation(admin, alder_res_id, {"cost": 1.0})
        assert_status(result, resp, 400, "Admin cannot set raw cost", "Unsupported update field")

        resp = update_reservation(admin, alder_res_id, {"status": "paid"})
        if assert_status(result, resp, 200, "Admin can set status"):
            status = resp.json().get("status")
            if status == "paid":
                result.ok("Status changed to paid")
            else:
                result.fail(f"Expected status 'paid', got '{status}'")

        result.section("Conflict and eligibility checks on admin date edits")
        resp = update_reservation(admin, alder_res_id, {
            "start_date": "2026-10-05",
            "end_date": "2026-10-07",
            "cabins": ["pine"],
        })
        assert_status(result, resp, 400, "Admin date/cabin update blocked by conflict", "conflict")

        # During simulation, admin bypass is suppressed; enforce round window rules.
        set_date(admin, "2026-04-05")  # Outside Alder's Round 1 window (Apr 1-2)
        resp = update_reservation(admin, alder_res_id, {
            "start_date": "2026-06-10",
            "end_date": "2026-06-12",
            "cabins": ["cedar"],
        })
        assert_status(result, resp, 400, "Admin date edit enforces round window in simulation", "window")
        clear_date(admin)

    except Exception as exc:
        result.fail(f"Aborted due to error: {exc}")
    finally:
        # Cleanup any reservations created by this script.
        try:
            if admin is not None:
                for rid in reversed(created_ids):
                    try:
                        delete_reservation(admin, rid)
                        result.ok(f"Cleanup deleted reservation id={rid}")
                    except Exception as cleanup_err:
                        result.fail(f"Cleanup failed for id={rid}: {cleanup_err}")
        finally:
            # Best-effort clear simulation and close sessions
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
