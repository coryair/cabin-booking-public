import secrets
import uuid
from datetime import datetime, timedelta
from urllib.parse import quote

from sqlalchemy.orm import Session as DBSession

from config import settings

from db.models import LoginToken


class LoginTokenService:
    @staticmethod
    def create_token(db: DBSession, email: str, shareholder_id: int) -> LoginToken:
        """Create a new login token. Login tokens remain valid until they expire."""
        login_token = LoginToken(
            id=str(uuid.uuid4()),
            email=email,
            token=secrets.token_urlsafe(32),
            shareholder_id=shareholder_id,
            expires_at=(datetime.utcnow() + timedelta(minutes=settings.magic_link_expire_minutes)).isoformat(),
        )
        db.add(login_token)
        db.commit()
        db.refresh(login_token)
        return login_token

    @staticmethod
    def get_by_token(db: DBSession, token: str) -> LoginToken | None:
        return db.query(LoginToken).filter(LoginToken.token == token).first()

    @staticmethod
    def validate_token(db: DBSession, token: str) -> LoginToken | None:
        """Return the login token if valid (exists and has not expired)."""
        login_token = LoginTokenService.get_by_token(db, token)
        if not login_token:
            return None
        if datetime.fromisoformat(login_token.expires_at) < datetime.utcnow():
            return None
        return login_token

    @staticmethod
    def get_login_url(token: str, app_url: str | None = None, next_path: str | None = None) -> str:
        base_url = (app_url or settings.app_url).rstrip("/")
        url = f"{base_url}/auth/verify?token={quote(token, safe='')}"
        if next_path:
            url += f"&next={quote(next_path, safe='')}"
        return url
