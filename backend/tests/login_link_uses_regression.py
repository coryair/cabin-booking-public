"""
Regression check for reusable magic login links.

Usage:
    cd backend && python tests/login_link_uses_regression.py
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Base
from db.models import LoginToken, Share, Shareholder
from services.login_token_service import LoginTokenService


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def build_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def seed_shareholder(db):
    share = Share(share_id="alder", share_name="Alder", priority=1)
    shareholder = Shareholder(
        share="alder",
        first_name="Test",
        last_name="User",
        email="test@example.com",
    )
    db.add(share)
    db.add(shareholder)
    db.commit()
    db.refresh(shareholder)
    return shareholder


def main() -> None:
    db = build_session()
    shareholder = seed_shareholder(db)
    login_token = LoginToken(
        id="login-token-id",
        email=shareholder.email,
        token="login-token",
        shareholder_id=shareholder.id,
        expires_at=(datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=30)).isoformat(),
    )
    db.add(login_token)
    db.commit()

    for use_number in range(1, 11):
        valid_token = LoginTokenService.validate_token(db, "login-token")
        assert_true(valid_token is not None, f"token should validate before use {use_number}")

    reusable_token = LoginTokenService.validate_token(db, "login-token")
    assert_true(reusable_token is not None, "token should remain valid after repeated uses")

    stored_token = LoginTokenService.get_by_token(db, "login-token")
    assert_true(stored_token is not None, "token should still exist for auditability")
    assert_true(stored_token.used_at is None, "token should not be marked used by login verification")

    LoginTokenService.create_token(db, shareholder.email, shareholder.id)
    still_current_token = LoginTokenService.validate_token(db, "login-token")
    assert_true(still_current_token is not None, "token should not be invalidated by a newer link")

    login_url = LoginTokenService.get_login_url(
        "token with spaces",
        "https://example.com",
        next_path="/booking/pay?reservation_id=126",
    )
    assert_true(
        login_url == "https://example.com/auth/verify?token=token%20with%20spaces&next=%2Fbooking%2Fpay%3Freservation_id%3D126",
        "login URL should safely encode token and post-login redirect",
    )

    stored_token.expires_at = (datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)).isoformat()
    db.commit()

    expired_token = LoginTokenService.validate_token(db, "login-token")
    assert_true(expired_token is None, "token should be invalid after expiration")

    print("login link reuse regression passed")


if __name__ == "__main__":
    main()
