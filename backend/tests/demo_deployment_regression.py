"""Run in isolation: python backend/tests/demo_deployment_regression.py."""
import os
from pathlib import Path
import runpy
from unittest.mock import patch

# Deliberately hostile deployment values must never reach integrations in demo mode.
os.environ.update(DEMO_MODE="true", ENVIRONMENT="production", DATABASE_URL="postgresql://invalid:invalid@invalid.invalid/never_connect", STRIPE_SECRET_KEY="test-disabled", RESEND_API_KEY="test-disabled")
root = Path(__file__).resolve().parents[2]
app = runpy.run_path(str(root / "api" / "index.py"))["app"]
from config import settings
from fastapi.testclient import TestClient
from services.email_service import _use_resend
from db.database import engine

assert settings.environment == "demo"
assert settings.database_url.startswith("sqlite:///") and "cabin-demo-" in settings.database_url
assert not settings.stripe_secret_key and not settings.resend_api_key and not _use_resend()

with patch("stripe.checkout.Session.create", side_effect=AssertionError("Real checkout called")):
    with TestClient(app, base_url="https://demo.example.com") as client:
        assert client.get("/api/cabins").status_code == 401
        login = client.post("/api/auth/login", json={"email":"alder@example.com","password":"password"})
        assert login.status_code == 200, login.text
        assert "Secure" in login.headers["set-cookie"]
        assert client.get("/api/auth/check").status_code == 200
        cabins = client.get("/api/cabins")
        assert {c["cabin_id"] for c in cabins.json()} == {"pine", "cedar"}
        response = client.post("/api/checkout", json={"share":"alder","cabins":["pine"],"start_date":"2026-06-10","end_date":"2026-06-12","guest_count":0,"is_day_use":False})
        assert response.status_code == 200, response.text
        booking = response.json()
        assert booking["checkout_url"].startswith("/booking/success?")
        reservation = client.get(f'/api/reservations/{booking["reservation_id"]}')
        assert reservation.status_code == 200 and reservation.json()["status"] == "paid", reservation.text
        duplicate = client.post("/api/checkout", json={"share":"alder","cabins":["pine"],"start_date":"2026-06-10","end_date":"2026-06-12","guest_count":0,"is_day_use":False})
        assert duplicate.status_code == 400, duplicate.text
        assert client.get("/api/cron/send-round-reminders").status_code in (401,500)
        assert client.post("/api/auth/login", json={"email":"admin@example.com","password":"password"}).status_code == 200
        assert client.get("/api/time-travel").json()["simulated_date"] == "2026-05-25"
engine.dispose()
print("PASS: isolated demo config, member/admin login, secure cookie, seeded calendar, simulated checkout, conflict rejection, and cron protection")
