import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session as DBSession

from config import settings
from db.models import Invitation


class MagicLinkService:
    @staticmethod
    def create_invitation(
        db: DBSession,
        email: str,
        share: str,
        first_name: str,
        last_name: str,
        phone_number: str | None = None,
        *,
        is_viewer: bool = False,
    ) -> Invitation:
        """Create a new invitation, invalidating any previous unused ones for this email."""
        # Invalidate previous unused invitations for this email
        db.query(Invitation).filter(
            Invitation.email == email,
            Invitation.used_at.is_(None),
        ).delete()

        invitation = Invitation(
            id=str(uuid.uuid4()),
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            token=secrets.token_urlsafe(32),
            share=share,
            is_viewer=1 if is_viewer else 0,
            expires_at=(datetime.utcnow() + timedelta(days=settings.invitation_expire_days)).isoformat(),
        )
        db.add(invitation)
        db.commit()
        db.refresh(invitation)
        return invitation

    @staticmethod
    def get_by_token(db: DBSession, token: str) -> Invitation | None:
        return db.query(Invitation).filter(Invitation.token == token).first()

    @staticmethod
    def validate_token(db: DBSession, token: str) -> Invitation | None:
        """Return the invitation if the token is valid (exists, not used, not expired)."""
        invitation = MagicLinkService.get_by_token(db, token)
        if not invitation:
            return None
        if invitation.used_at:
            return None
        if datetime.fromisoformat(invitation.expires_at) < datetime.utcnow():
            return None
        return invitation

    @staticmethod
    def consume(db: DBSession, invitation: Invitation) -> None:
        """Mark an invitation as used."""
        invitation.used_at = datetime.utcnow().isoformat()
        db.commit()

    @staticmethod
    def get_invite_url(token: str) -> str:
        return f"{settings.app_url}/invite?token={token}"
