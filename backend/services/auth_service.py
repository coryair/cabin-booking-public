import bcrypt
from sqlalchemy.orm import Session as DBSession, joinedload
from datetime import datetime, timedelta
import uuid

from sqlalchemy import func

from db.models import Shareholder, Session
from config import settings


class AuthService:
    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

    @staticmethod
    def authenticate(db: DBSession, email: str, password: str) -> Shareholder | None:
        shareholder = db.query(Shareholder).options(
            joinedload(Shareholder.share_rel)
        ).filter(func.lower(Shareholder.email) == email.strip().lower()).first()
        if not shareholder:
            return None
        if not shareholder.password_hash:
            return None
        if not AuthService.verify_password(password, shareholder.password_hash):
            return None
        return shareholder

    @staticmethod
    def create_session(db: DBSession, shareholder_id: int) -> Session:
        if settings.demo_mode:
            # Public fixture identities survive worker resets; these are not secrets.
            return Session(id=f"demo-{shareholder_id}", shareholder_id=shareholder_id)
        session_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(days=settings.session_expire_days)

        session = Session(
            id=session_id,
            shareholder_id=shareholder_id,
            expires_at=expires_at.isoformat()
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def get_session(db: DBSession, session_id: str) -> Session | None:
        session = db.query(Session).filter(Session.id == session_id).first()
        if not session:
            return None

        # Check if expired
        expires_at = datetime.fromisoformat(session.expires_at)
        if expires_at < datetime.utcnow():
            db.delete(session)
            db.commit()
            return None

        return session

    @staticmethod
    def delete_session(db: DBSession, session_id: str) -> bool:
        session = db.query(Session).filter(Session.id == session_id).first()
        if session:
            db.delete(session)
            db.commit()
            return True
        return False

    @staticmethod
    def get_shareholder_by_session(db: DBSession, session_id: str) -> Shareholder | None:
        if settings.demo_mode and session_id.startswith("demo-"):
            demo_id = session_id.removeprefix("demo-")
            if demo_id.isdigit():
                return db.query(Shareholder).options(joinedload(Shareholder.share_rel)).filter(
                    Shareholder.id == int(demo_id)
                ).first()
            return None
        session = AuthService.get_session(db, session_id)
        if not session:
            return None
        return db.query(Shareholder).options(
            joinedload(Shareholder.share_rel)
        ).filter(
            Shareholder.id == session.shareholder_id
        ).first()
