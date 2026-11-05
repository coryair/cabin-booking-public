"""
Viewer-role regression checks.

Coverage:
- viewer invitations validate with the viewer flag
- accepting a viewer invitation creates a viewer-only shareholder on the assigned share
- viewer accounts can load booking status but cannot list or create reservations

Usage:
    cd backend
    SU_PASSWORD=<password> python tests/viewer_role_regression.py
"""

import os
import sys
import uuid
from pathlib import Path

import httpx

sys.path.append(str(Path(__file__).resolve().parents[1]))

from db.database import SessionLocal
from db.models import Invitation, Shareholder
from services.magic_link_service import MagicLinkService

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")


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


def create_viewer_invitation(email: str, share: str) -> str:
    db = SessionLocal()
    try:
        db.query(Invitation).filter(Invitation.email == email).delete()
        db.query(Shareholder).filter(Shareholder.email == email).delete()
        invitation = MagicLinkService.create_invitation(
            db,
            email,
            share,
            "Calendar",
            "Viewer",
            None,
            is_viewer=True,
        )
        return invitation.token
    finally:
        db.close()


def cleanup_viewer(email: str):
    db = SessionLocal()
    try:
        db.query(Invitation).filter(Invitation.email == email).delete()
        db.query(Shareholder).filter(Shareholder.email == email).delete()
        db.commit()
    finally:
        db.close()


def main():
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
    viewer = None
    viewer_email = f"viewer-{uuid.uuid4().hex[:8]}@example.com"

    try:
        result.section("Create viewer invitation")
        token = create_viewer_invitation(viewer_email, "alder")
        result.ok("Created viewer invitation directly in DB")

        resp = httpx.get(f"{BASE_URL}/api/invitations/validate", params={"token": token})
        if assert_status(result, resp, 200, "Validate invitation token"):
            body = resp.json()
            if body.get("valid") is True and body.get("is_viewer") is True:
                result.ok("Invitation validate response includes viewer flag")
            else:
                result.fail(f"Unexpected validate payload: {body}")

        result.section("Accept viewer invitation")
        viewer = httpx.Client(base_url=BASE_URL)
        resp = viewer.post("/api/invitations/accept", json={
            "token": token,
            "first_name": "Calendar",
            "last_name": "Viewer",
            "email": viewer_email,
            "phone_number": None,
        })
        assert_status(result, resp, 200, "Accept viewer invitation")

        resp = viewer.get("/api/auth/check")
        if assert_status(result, resp, 200, "Auth check after accept"):
            body = resp.json()
            shareholder = body.get("shareholder") or {}
            if body.get("authenticated") and shareholder.get("is_viewer") is True:
                result.ok("Accepted account is authenticated as viewer")
            else:
                result.fail(f"Unexpected auth payload: {body}")
            if shareholder.get("share") == "alder":
                result.ok("Viewer stays assigned to the invited share")
            else:
                result.fail(f"Unexpected invited share: {shareholder.get('share')}")

        result.section("Viewer is calendar-only")
        resp = viewer.get("/api/booking-status")
        if assert_status(result, resp, 200, "Viewer can load booking status"):
            body = resp.json()
            if body.get("can_book") is False and "Viewer access" in (body.get("reason") or ""):
                result.ok("Booking status reports calendar-only access")
            else:
                result.fail(f"Unexpected booking status payload: {body}")

        resp = viewer.get("/api/reservations")
        assert_status(result, resp, 403, "Viewer cannot list reservations outside calendar")

        resp = viewer.post("/api/checkout", json={
            "share": "alder",
            "guest_count": 0,
            "start_date": "2026-10-10",
            "end_date": "2026-10-12",
            "cabins": ["pine"],
            "is_day_use": False,
        })
        assert_status(result, resp, 403, "Viewer cannot create checkout bookings")

    except Exception as exc:
        result.fail(f"Aborted due to error: {exc}")
    finally:
        try:
            cleanup_viewer(viewer_email)
        except Exception:
            pass
        if viewer is not None:
            viewer.close()

    result.print()
    if result.failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
