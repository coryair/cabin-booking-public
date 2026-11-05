"""
Multi-share access regression checks.

Usage:
    cd backend && source venv/bin/activate
    SEED_PASSWORD=<password> SU_PASSWORD=<password> python tests/multi_share_access_regression.py
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


def login(email: str, password: str) -> httpx.Client:
    client = httpx.Client(base_url=BASE_URL)
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        raise RuntimeError(f"Login failed for {email}: {resp.status_code} {resp.text}")
    return client


def set_date(admin: httpx.Client, value: str):
    resp = admin.post("/api/time-travel", json={"date": value})
    resp.raise_for_status()


def clear_date(admin: httpx.Client):
    resp = admin.delete("/api/time-travel")
    resp.raise_for_status()


def find_shareholder_id(admin: httpx.Client, email: str) -> int:
    resp = admin.get("/api/shareholders")
    resp.raise_for_status()
    for sh in resp.json():
        if (sh.get("email") or "").lower() == email.lower():
            return int(sh["id"])
    raise RuntimeError(f"Shareholder not found for email {email}")


def update_additional_shares(admin: httpx.Client, shareholder_id: int, additional_shares: list[str]):
    resp = admin.put(
        f"/api/shareholders/{shareholder_id}",
        json={"additional_shares": additional_shares},
    )
    resp.raise_for_status()


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
    alder_id = None
    created_reservation_id = None
    expected_booker_id = None
    expected_booker_name = None

    try:
        result.section("Login")
        admin = login(ADMIN_EMAIL, SU_PASSWORD)
        alder = login(ALDER_EMAIL, SEED_PASSWORD)
        result.ok("Logged in admin + alder")
        clear_date(admin)
        set_date(admin, "2026-02-10")
        result.ok("Set offseason simulated date for direct-create regression coverage")

        result.section("Grant additional share")
        alder_id = find_shareholder_id(admin, ALDER_EMAIL)
        update_additional_shares(admin, alder_id, ["birch"])
        result.ok("Assigned alder additional share access: birch")

        result.section("Auth payload includes allowed shares")
        check = alder.get("/api/auth/check")
        if assert_status(result, check, 200, "Fetch auth check"):
            body = check.json()
            sh = body.get("shareholder") or {}
            expected_booker_id = sh.get("id")
            first = (sh.get("first_name") or "").strip()
            last = (sh.get("last_name") or "").strip()
            expected_booker_name = " ".join(part for part in [first, last] if part) or None
            allowed = {s.get("share_id") for s in (sh.get("allowed_shares") or [])}
            if "alder" in allowed and "birch" in allowed:
                result.ok("Auth check contains primary + additional allowed shares")
            else:
                result.fail(f"Unexpected allowed shares payload: {allowed}")

        result.section("Booking status share scoping")
        resp = alder.get("/api/booking-status", params={"share": "birch"})
        assert_status(result, resp, 200, "Can fetch booking status for allowed share")

        resp = alder.get("/api/booking-status", params={"share": "fir"})
        assert_status(result, resp, 403, "Cannot fetch booking status for unassigned share")

        result.section("Reservation creation by selected share")
        resp = alder.post("/api/reservations", json={
            "share": "birch",
            "guest_count": 0,
            "start_date": "2026-10-10",
            "end_date": "2026-10-12",
            "cabins": ["pine"],
            "is_day_use": False,
        })
        if assert_status(result, resp, 200, "Can create reservation for allowed selected share"):
            body = resp.json()
            created_reservation_id = int(body["id"])
            if body.get("share") == "birch":
                result.ok("Reservation stored under selected share")
            else:
                result.fail(f"Reservation share mismatch: expected birch, got {body.get('share')}")
            if expected_booker_name and body.get("booked_by_shareholder_name") == expected_booker_name:
                result.ok("Create response includes booked-by shareholder name")
            else:
                result.fail(
                    "Create response missing booked-by shareholder name: "
                    f"expected '{expected_booker_name}', got '{body.get('booked_by_shareholder_name')}'"
                )
            if expected_booker_id is not None and body.get("booked_by_shareholder_id") == expected_booker_id:
                result.ok("Create response includes booked-by shareholder id")
            else:
                result.fail(
                    "Create response missing booked-by shareholder id: "
                    f"expected '{expected_booker_id}', got '{body.get('booked_by_shareholder_id')}'"
                )

        resp = alder.post("/api/reservations", json={
            "share": "fir",
            "guest_count": 0,
            "start_date": "2026-10-14",
            "end_date": "2026-10-16",
            "cabins": ["cedar"],
            "is_day_use": False,
        })
        assert_status(result, resp, 403, "Cannot create reservation for unassigned share")

        result.section("Reservation list includes allowed shares")
        resp = alder.get("/api/reservations")
        if assert_status(result, resp, 200, "List reservations"):
            items = resp.json()
            if created_reservation_id is not None and any(
                int(r.get("id")) == created_reservation_id and r.get("share") == "birch"
                for r in items
            ):
                result.ok("List includes reservation from additional allowed share")
            else:
                result.fail("List did not include reservation from additional allowed share")
            if created_reservation_id is not None:
                created_row = next((r for r in items if int(r.get("id")) == created_reservation_id), None)
                if created_row and expected_booker_name and created_row.get("booked_by_shareholder_name") == expected_booker_name:
                    result.ok("List response includes booked-by shareholder name")
                else:
                    result.fail(
                        "List response missing booked-by shareholder name: "
                        f"expected '{expected_booker_name}', got '{None if created_row is None else created_row.get('booked_by_shareholder_name')}'"
                    )
                if created_row and expected_booker_id is not None and created_row.get("booked_by_shareholder_id") == expected_booker_id:
                    result.ok("List response includes booked-by shareholder id")
                else:
                    result.fail(
                        "List response missing booked-by shareholder id: "
                        f"expected '{expected_booker_id}', got '{None if created_row is None else created_row.get('booked_by_shareholder_id')}'"
                    )

    except Exception as exc:
        result.fail(f"Aborted due to error: {exc}")
    finally:
        if alder and created_reservation_id is not None:
            alder.post(f"/api/reservations/{created_reservation_id}/cancel")
        if admin and alder_id is not None:
            try:
                update_additional_shares(admin, alder_id, [])
            except Exception:
                pass
        if admin:
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
