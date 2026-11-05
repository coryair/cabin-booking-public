"""
Concurrent reservation regression test for same-cabin double-booking races.

Verifies that two simultaneous requests for the same cabin/date range serialize so
only one reservation is created and the loser receives a conflict response.

Usage:
    cd backend && source venv/bin/activate
    SEED_PASSWORD=<password> SU_PASSWORD=<password> python tests/double_booking_race_regression.py
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import os
import sys
import threading

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


def login(email: str, password: str) -> httpx.Client:
    client = httpx.Client(base_url=BASE_URL, timeout=15.0)
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


def delete_reservation(client: httpx.Client, reservation_id: int):
    resp = client.delete(f"/api/reservations/{reservation_id}")
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to delete reservation {reservation_id}: {resp.status_code} {resp.text}")


def find_open_window(client: httpx.Client, cabin: str, seed: date) -> tuple[str, str]:
    for offset in range(0, 45, 3):
        start = seed + timedelta(days=offset)
        end = start + timedelta(days=2)
        resp = client.get(
            "/api/availability",
            params={
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "cabins": cabin,
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Availability lookup failed: {resp.status_code} {resp.text}")
        body = resp.json()
        if body.get("cabins", {}).get(cabin) is True:
            return start.isoformat(), end.isoformat()
    raise RuntimeError(f"Could not find an open {cabin} window starting from {seed.isoformat()}")


def create_reservation(client: httpx.Client, start: str, end: str, cabin: str) -> httpx.Response:
    return client.post("/api/reservations", json={
        "share": "",
        "guest_count": 0,
        "start_date": start,
        "end_date": end,
        "cabins": [cabin],
        "is_day_use": False,
    })


def list_reservations(client: httpx.Client, start: str, end: str, cabin: str) -> list[dict]:
    resp = client.get("/api/reservations", params={
        "start_date": start,
        "end_date": end,
        "cabin": cabin,
    })
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to list reservations: {resp.status_code} {resp.text}")
    return resp.json()


def concurrent_create(
    email: str,
    password: str,
    start: str,
    end: str,
    cabin: str,
    barrier: threading.Barrier,
) -> tuple[int, dict | str]:
    client = login(email, password)
    try:
        barrier.wait(timeout=10)
        resp = create_reservation(client, start, end, cabin)
        try:
            body: dict | str = resp.json()
        except Exception:
            body = resp.text
        return resp.status_code, body
    finally:
        client.close()


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
    admin = None
    created_ids: list[int] = []

    try:
        result.section("Setup")
        admin = login(ADMIN_EMAIL, SU_PASSWORD)
        result.ok("Logged in admin")
        set_date(admin, "2026-02-10")
        result.ok("Enabled simulation so direct reservation creates are allowed")

        result.section("Concurrent booking race")
        cabin = "pine"
        start_date, end_date = find_open_window(admin, cabin, date(2026, 11, 1))
        result.ok(f"Found open test window {start_date} -> {end_date} for {cabin}")

        barrier = threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(concurrent_create, ALDER_EMAIL, SEED_PASSWORD, start_date, end_date, cabin, barrier),
                executor.submit(concurrent_create, BIRCH_EMAIL, SEED_PASSWORD, start_date, end_date, cabin, barrier),
            ]
        responses = [future.result() for future in futures]

        success_bodies: list[dict] = []
        conflict_count = 0
        for status_code, body in responses:
            if status_code == 200 and isinstance(body, dict):
                success_bodies.append(body)
            elif status_code == 400 and isinstance(body, dict) and "conflict" in str(body.get("detail", "")).lower():
                conflict_count += 1
            else:
                result.fail(f"Unexpected concurrent result: HTTP {status_code} body={body}")

        if len(success_bodies) == 1:
            reservation_id = int(success_bodies[0]["id"])
            created_ids.append(reservation_id)
            result.ok("Exactly one concurrent request succeeded")
        else:
            result.fail(f"Expected exactly one success, saw {len(success_bodies)}")

        if conflict_count == 1:
            result.ok("The losing concurrent request returned a booking conflict")
        else:
            result.fail(f"Expected exactly one conflict response, saw {conflict_count}")

        reservations = list_reservations(admin, start_date, end_date, cabin)
        active_ids = [int(res["id"]) for res in reservations if res["start_date"] == start_date and res["end_date"] == end_date]
        if len(active_ids) == 1:
            result.ok("Only one active reservation exists for the contested cabin/date range")
        else:
            result.fail(f"Expected 1 active reservation after race, found {len(active_ids)}: {active_ids}")

    except Exception as exc:
        result.fail(f"Aborted due to error: {exc}")
    finally:
        try:
            if admin is not None:
                for reservation_id in reversed(created_ids):
                    try:
                        delete_reservation(admin, reservation_id)
                        result.ok(f"Cleanup deleted reservation id={reservation_id}")
                    except Exception as cleanup_err:
                        result.fail(f"Cleanup failed for id={reservation_id}: {cleanup_err}")
        finally:
            try:
                if admin is not None:
                    clear_date(admin)
            except Exception:
                pass
            if admin is not None:
                admin.close()

    result.print()
    sys.exit(1 if result.failed > 0 else 0)


if __name__ == "__main__":
    main()
