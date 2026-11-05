from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session as DBSession, joinedload

from config import settings
from db.database import get_db
from db.models import Invitation, Share, Shareholder
from models.shareholder import InvitationCreate, InvitationAccept, InvitationResponse
from services.auth_service import AuthService
from services.email_service import send_invitation_email
from services.magic_link_service import MagicLinkService
from .auth import require_admin

router = APIRouter(prefix="/api/invitations", tags=["invitations"])


def _invitation_to_response(inv: Invitation) -> InvitationResponse:
    return InvitationResponse(
        id=inv.id,
        email=inv.email,
        first_name=inv.first_name,
        last_name=inv.last_name,
        phone_number=inv.phone_number,
        share=inv.share,
        share_name=inv.share_rel.share_name if inv.share_rel else None,
        is_viewer=bool(inv.is_viewer),
        expires_at=inv.expires_at,
        used_at=inv.used_at,
        created_at=inv.created_at,
    )


@router.post("", response_model=InvitationResponse)
def send_invitation(
    body: InvitationCreate,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(require_admin),
):
    # Validate the share exists
    share = db.query(Share).filter(Share.share_id == body.share).first()
    if not share:
        raise HTTPException(status_code=400, detail="Invalid share ID")

    # Check email isn't already a shareholder
    existing_email = db.query(Shareholder).filter(Shareholder.email == body.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already registered as a shareholder")

    invitation = MagicLinkService.create_invitation(
        db,
        body.email,
        body.share,
        body.first_name,
        body.last_name,
        body.phone_number,
        is_viewer=body.is_viewer,
    )
    invite_url = MagicLinkService.get_invite_url(invitation.token)

    sent = send_invitation_email(body.email, invite_url, share.share_name)
    if not sent:
        raise HTTPException(status_code=500, detail="Failed to send invitation email")

    # Reload with relationship
    invitation = db.query(Invitation).options(
        joinedload(Invitation.share_rel)
    ).filter(Invitation.id == invitation.id).first()

    return _invitation_to_response(invitation)


@router.get("", response_model=list[InvitationResponse])
def list_invitations(
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(require_admin),
):
    invitations = db.query(Invitation).options(
        joinedload(Invitation.share_rel)
    ).filter(
        Invitation.used_at.is_(None),
    ).order_by(Invitation.created_at.desc()).all()

    return [_invitation_to_response(inv) for inv in invitations]


@router.delete("/{invitation_id}")
def revoke_invitation(
    invitation_id: str,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(require_admin),
):
    invitation = db.query(Invitation).filter(Invitation.id == invitation_id).first()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")
    db.delete(invitation)
    db.commit()
    return {"message": "Invitation revoked"}


@router.get("/validate")
def validate_invitation(
    token: str,
    db: DBSession = Depends(get_db),
):
    """Public endpoint to check if a token is valid (for the accept form)."""
    invitation = MagicLinkService.validate_token(db, token)
    if not invitation:
        return {"valid": False}
    share = db.query(Share).filter(Share.share_id == invitation.share).first()
    return {
        "valid": True,
        "email": invitation.email,
        "first_name": invitation.first_name,
        "last_name": invitation.last_name,
        "phone_number": invitation.phone_number,
        "share_name": share.share_name if share else invitation.share,
        "is_viewer": bool(invitation.is_viewer),
    }


@router.get("/available-shares")
def available_shares(
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(require_admin),
):
    """List all shares (multiple shareholders can belong to the same share)."""
    shares = db.query(Share).all()
    return [
        {"share_id": s.share_id, "share_name": s.share_name}
        for s in shares
    ]


@router.post("/accept")
def accept_invitation(
    body: InvitationAccept,
    response: Response,
    db: DBSession = Depends(get_db),
):
    invitation = MagicLinkService.validate_token(db, body.token)
    if not invitation:
        raise HTTPException(status_code=400, detail="Invalid or expired invitation")

    if body.email.lower() != invitation.email.lower():
        raise HTTPException(status_code=400, detail="Email does not match invitation")

    # Check email isn't already registered
    existing_email = db.query(Shareholder).filter(Shareholder.email == body.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    shareholder = Shareholder(
        share=invitation.share,
        first_name=body.first_name,
        last_name=body.last_name,
        email=body.email,
        phone_number=body.phone_number,
        is_viewer=1 if invitation.is_viewer else 0,
        password_hash=AuthService.hash_password(body.password) if body.password else None,
    )
    db.add(shareholder)
    MagicLinkService.consume(db, invitation)
    db.commit()

    # Auto-login: create session and set cookie
    session = AuthService.create_session(db, shareholder.id)
    is_production = settings.environment == "production"
    response.set_cookie(
        key="session_id",
        value=session.id,
        httponly=True,
        samesite="lax",
        secure=is_production,
        max_age=60 * 60 * 24 * settings.session_expire_days,
    )

    return {"message": "Account created successfully"}
