"""
Reservation cancellation ownership regression checks.

Verifies:
- A different user on the same share cannot cancel someone else's reservation.
- Additional share access does not allow cancelling someone else's reservation.
- Reservation owners can still cancel their own reservations.

Usage:
    cd backend && source venv/bin/activate
    SEED_PASSWORD=<password> SU_PASSWORD=<password> python tests/reservation_cancel_ownership_regression.py
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
TEMP_SAME_SHARE_EMAIL = os.environ.get("TEMP_SAME_SHARE_EMAIL", "alder-second@example.com")


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


def list_shareholders(admin: httpx.Client) -> list[dict]:
    resp = admin.get("/api/shareholders")
    resp.raise_for_status()
    return resp.json()


def find_shareholder_id(admin: httpx.Client, email: str) -> int | None:
    for sh in list_shareholders(admin):
        if (sh.get("email") or "").lower() == email.lower():
            return int(sh["id"])
    return None


def create_shareholder(admin: httpx.Client, *, share: str, first_name: str, last_name: str, email: str, password: str):
    resp = admin.post("/api/shareholders", json={
        "share": share,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "password": password,
    })
    resp.raise_for_status()
    return resp.json()


def delete_shareholder(admin: httpx.Client, shareholder_id: int):
    resp = admin.delete(f"/api/shareholders/{shareholder_id}")
    resp.raise_for_status()


def update_additional_shares(admin: httpx.Client, shareholder_id: int, additional_shares: list[str]):
    resp = admin.put(
        f"/api/shareholders/{shareholder_id}",
        json={"additional_shares": additional_shares},
    )
    resp.raise_for_status()


def create_reservation(client: httpx.Client, *, share: str, start: str, end: str, cabin: str) -> httpx.Response:
    return client.post("/api/reservations", json={
        "share": share,
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
    admin = alder = birch = same_share = None
    temp_same_share_id = None
    alder_id = None
    created_ids: list[int] = []

    try:
        result.section("Login and setup")
        admin = login(ADMIN_EMAIL, SU_PASSWORD)
        alder = login(ALDER_EMAIL, SEED_PASSWORD)
        birch = login(BIRCH_EMAIL, SEED_PASSWORD)
        result.ok("Logged in admin, alder, and birch")

        clear_date(admin)
        set_date(admin, "2026-01-01")
        clear_all_reservations(admin)
        set_date(admin, "2026-02-10")
        result.ok("Cleared reservations and set offseason test date")

        existing_temp_id = find_shareholder_id(admin, TEMP_SAME_SHARE_EMAIL)
        if existing_temp_id is not None:
            delete_shareholder(admin, existing_temp_id)

        created_shareholder = create_shareholder(
            admin,
            share="alder",
            first_name="Second",
            last_name="Alder",
            email=TEMP_SAME_SHARE_EMAIL,
            password=SEED_PASSWORD,
        )
        temp_same_share_id = int(created_shareholder["id"])
        same_share = login(TEMP_SAME_SHARE_EMAIL, SEED_PASSWORD)
        result.ok("Created and logged in second user on the alder share")

        alder_id = find_shareholder_id(admin, ALDER_EMAIL)
        if alder_id is None:
            raise RuntimeError("Could not find alder shareholder id")
        update_additional_shares(admin, alder_id, ["birch"])
        result.ok("Granted alder additional access to birch")

        result.section("Same-share non-owner cannot cancel")
        resp = create_reservation(
            alder,
            share="",
            start="2026-03-01",
            end="2026-03-03",
            cabin="pine",
        )
        if not assert_status(result, resp, 200, "Alder creates reservation on primary share"):
            raise RuntimeError("Cannot continue without same-share baseline reservation")
        same_share_reservation_id = int(resp.json()["id"])
        created_ids.append(same_share_reservation_id)

        resp = same_share.post(f"/api/reservations/{same_share_reservation_id}/cancel")
        assert_status(result, resp, 403, "Different user on same share cannot cancel via /cancel")

        resp = get_reservation(alder, same_share_reservation_id)
        if assert_status(result, resp, 200, "Owner can still fetch reservation after blocked cancel"):
            status = resp.json().get("status")
            if status not in ("cancelled", "refunded"):
                result.ok("Blocked same-share cancel left reservation active")
            else:
                result.fail(f"Reservation was unexpectedly changed to status={status}")

        result.section("Additional-share access does not grant cancel rights")
        resp = create_reservation(
            birch,
            share="",
            start="2026-03-05",
            end="2026-03-07",
            cabin="cedar",
        )
        if not assert_status(result, resp, 200, "Birch creates reservation on primary share"):
            raise RuntimeError("Cannot continue without additional-share baseline reservation")
        cross_share_reservation_id = int(resp.json()["id"])
        created_ids.append(cross_share_reservation_id)

        resp = alder.delete(f"/api/reservations/{cross_share_reservation_id}")
        assert_status(result, resp, 403, "Additional share access cannot cancel someone else's reservation via DELETE")

        resp = get_reservation(birch, cross_share_reservation_id)
        if assert_status(result, resp, 200, "Owner can still fetch additional-share reservation after blocked cancel"):
            status = resp.json().get("status")
            if status not in ("cancelled", "refunded"):
                result.ok("Blocked cross-share cancel left reservation active")
            else:
                result.fail(f"Reservation was unexpectedly changed to status={status}")

        result.section("Owners can still cancel their own reservations")
        resp = alder.post(f"/api/reservations/{same_share_reservation_id}/cancel")
        if assert_status(result, resp, 200, "Original owner can cancel own reservation"):
            result.ok(f"Owner cancel response: {resp.json().get('message')}")
        created_ids.remove(same_share_reservation_id)

        resp = birch.post(f"/api/reservations/{cross_share_reservation_id}/cancel")
        if assert_status(result, resp, 200, "Additional-share reservation owner can cancel own reservation"):
            result.ok(f"Owner cancel response: {resp.json().get('message')}")
        created_ids.remove(cross_share_reservation_id)

    except Exception as exc:
        result.fail(f"Aborted due to error: {exc}")
    finally:
        if admin and alder_id is not None:
            try:
                update_additional_shares(admin, alder_id, [])
            except Exception:
                pass
        if admin:
            for reservation_id in list(created_ids):
                try:
                    delete_reservation(admin, reservation_id)
                except Exception:
                    pass
        if admin and temp_same_share_id is not None:
            try:
                delete_shareholder(admin, temp_same_share_id)
            except Exception:
                pass
        if admin:
            try:
                clear_date(admin)
            except Exception:
                pass
        if same_share:
            same_share.close()
        if birch:
            birch.close()
        if alder:
            alder.close()
        if admin:
            admin.close()

    result.print()
    if result.failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
