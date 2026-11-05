"""
Calendar booked-by label regression checks.

Verifies:
- Calendar entries include booked-by label (`J Smith`) for newly created reservations.
- Calendar display label combines share + booker (`Share Name (J Smith)`).
- Legacy fallback works when `booked_by_shareholder_id` is null (share-only label).

Usage:
    cd backend && source venv/bin/activate
    SEED_PASSWORD=<password> SU_PASSWORD=<password> python tests/calendar_booker_label_regression.py
"""

import os
import sqlite3
import sys
from pathlib import Path

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


def assert_status(result: Result, resp: httpx.Response, expected_status: int, label: str) -> bool:
    if resp.status_code != expected_status:
        result.fail(f"{label}: expected HTTP {expected_status}, got {resp.status_code}: {resp.text}")
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


def clear_all_reservations(admin: httpx.Client):
    resp = admin.get("/api/reservations")
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to list reservations: {resp.status_code} {resp.text}")
    for res in resp.json():
        delete_reservation(admin, int(res["id"]))


def get_auth_shareholder(client: httpx.Client) -> dict:
    resp = client.get("/api/auth/check")
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to fetch auth/check: {resp.status_code} {resp.text}")
    payload = resp.json()
    shareholder = payload.get("shareholder")
    if not shareholder:
        raise RuntimeError("No shareholder data in auth/check response")
    return shareholder


def get_calendar_day(client: httpx.Client, year: int, month: int, date_str: str) -> dict:
    resp = client.get(f"/api/calendar/{year}/{month}")
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to fetch calendar: {resp.status_code} {resp.text}")

    for day in resp.json().get("days", []):
        if day.get("date") == date_str:
            return day
    raise RuntimeError(f"Calendar day not found: {date_str}")


def find_day_reservation(day: dict, reservation_id: int) -> dict | None:
    for row in day.get("reservations", []):
        if int(row.get("id")) == reservation_id:
            return row
    return None


def clear_booker_in_local_sqlite(reservation_id: int):
    db_path = Path(__file__).resolve().parent.parent.parent / "data" / "cabins.db"
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite DB not found at {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("UPDATE reservations SET booked_by_shareholder_id = NULL WHERE id = ?", (reservation_id,))
        conn.commit()
    finally:
        conn.close()


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
        result.ok("Logged in admin + alder")

        clear_date(admin)
        clear_all_reservations(admin)
        set_date(admin, "2026-02-10")  # Offseason, no round-window restrictions.

        result.section("New reservation includes booked-by short label")
        me = get_auth_shareholder(alder)
        expected_short = f"{me['first_name'][0]} {me['last_name']}"

        created = create_reservation(alder, "2026-02-20", "2026-02-21", "pine")
        if not assert_status(result, created, 200, "Create baseline reservation"):
            raise RuntimeError("Cannot continue without baseline reservation")

        body = created.json()
        reservation_id = int(body["id"])
        created_ids.append(reservation_id)
        expected_share = body.get("share_name") or body["share"]
        expected_display = f"{expected_share} ({expected_short})"

        paid_resp = update_reservation(admin, reservation_id, {"status": "paid"})
        if not assert_status(result, paid_resp, 200, "Admin marks baseline reservation paid"):
            raise RuntimeError("Cannot continue without paid baseline reservation")

        day = get_calendar_day(alder, 2026, 2, "2026-02-20")
        row = find_day_reservation(day, reservation_id)
        if not row:
            result.fail("Created reservation missing from calendar day")
        else:
            if row.get("booked_by_short_name") == expected_short:
                result.ok("Calendar includes booked_by_short_name")
            else:
                result.fail(
                    f"Expected booked_by_short_name='{expected_short}', got '{row.get('booked_by_short_name')}'"
                )

            if row.get("calendar_display_name") == expected_display:
                result.ok("Calendar includes combined share + booked-by label")
            else:
                result.fail(
                    f"Expected calendar_display_name='{expected_display}', got '{row.get('calendar_display_name')}'"
                )

        result.section("Legacy fallback uses share-only label")
        if BASE_URL != "http://localhost:8000":
            result.ok("Skipped legacy fallback DB mutation for non-local BASE_URL")
        else:
            try:
                clear_booker_in_local_sqlite(reservation_id)
                day_after = get_calendar_day(alder, 2026, 2, "2026-02-20")
                row_after = find_day_reservation(day_after, reservation_id)
                if not row_after:
                    result.fail("Reservation missing from calendar after nulling booked_by")
                else:
                    if row_after.get("booked_by_short_name") is None:
                        result.ok("booked_by_short_name is null when reservation has no booked_by")
                    else:
                        result.fail(
                            "Expected booked_by_short_name to be null, "
                            f"got '{row_after.get('booked_by_short_name')}'"
                        )

                    if row_after.get("calendar_display_name") == expected_share:
                        result.ok("calendar_display_name falls back to share-only label")
                    else:
                        result.fail(
                            f"Expected share-only fallback '{expected_share}', "
                            f"got '{row_after.get('calendar_display_name')}'"
                        )
            except Exception as exc:
                result.fail(f"Legacy fallback check failed: {exc}")
    finally:
        try:
            if admin:
                for rid in created_ids:
                    try:
                        delete_reservation(admin, rid)
                        result.ok(f"Cleanup deleted reservation id={rid}")
                    except Exception as cleanup_exc:
                        result.fail(f"Cleanup failed for reservation id={rid}: {cleanup_exc}")
        except Exception as exc:
            result.fail(f"Cleanup error: {exc}")
        try:
            if admin:
                clear_date(admin)
        except Exception:
            pass
        try:
            if alder:
                alder.close()
        except Exception:
            pass
        try:
            if admin:
                admin.close()
        except Exception:
            pass

    result.print()
    if result.failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
