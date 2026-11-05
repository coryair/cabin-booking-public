from fastapi import APIRouter, Depends, HTTPException, Response, Cookie, Request
from sqlalchemy.orm import Session as DBSession
from typing import Optional

from config import settings
from sqlalchemy import func

from db.database import get_db
from db.models import Shareholder
from models.shareholder import ShareholderLogin, ShareholderResponse, AuthCheckResponse, MagicLinkRequest, MagicLinkVerify
from services.auth_service import AuthService
from services.frontend_origin_service import resolve_frontend_base_url
from services.login_token_service import LoginTokenService
from services.share_access_service import ShareAccessService
from services.email_service import send_login_email
from utils.http_cache import set_no_store

router = APIRouter(prefix="/api/auth", tags=["auth"])


def shareholder_to_response(db: DBSession, shareholder: Shareholder) -> ShareholderResponse:
    """Convert a Shareholder ORM model to a ShareholderResponse with share_name."""
    allowed_shares = ShareAccessService.get_allowed_shares(db, shareholder)
    return ShareholderResponse(
        id=shareholder.id,
        share=shareholder.share,
        share_name=shareholder.share_rel.share_name if shareholder.share_rel else None,
        priority=shareholder.share_rel.priority if shareholder.share_rel else 0,
        first_name=shareholder.first_name,
        last_name=shareholder.last_name,
        email=shareholder.email,
        phone_number=shareholder.phone_number,
        last_booked=shareholder.last_booked,
        is_viewer=bool(shareholder.is_viewer),
        is_analytics=bool(shareholder.is_analytics),
        is_admin=bool(shareholder.is_admin),
        is_superadmin=bool(shareholder.is_superadmin),
        tour_seen=bool(shareholder.tour_seen),
        cancellation_availability_emails_enabled=bool(
            shareholder.cancellation_availability_emails_enabled
        ),
        allowed_shares=[
            {
                "share_id": share.share_id,
                "share_name": share.share_name,
                "priority": share.priority,
            }
            for share in allowed_shares
        ],
        can_access_multiple_shares=len(allowed_shares) > 1,
        created_at=shareholder.created_at,
    )


@router.post("/login")
def login(
    credentials: ShareholderLogin,
    response: Response,
    db: DBSession = Depends(get_db)
):
    shareholder = AuthService.authenticate(db, credentials.email, credentials.password)
    if not shareholder:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    session = AuthService.create_session(db, shareholder.id)

    is_production = settings.environment == "production"
    response.set_cookie(
        key="session_id",
        value=session.id,
        httponly=True,
        samesite="lax",
        secure=is_production or settings.demo_mode,
        max_age=60 * 60 * 24 * settings.session_expire_days,
    )

    return {
        "message": "Login successful",
        "shareholder": shareholder_to_response(db, shareholder)
    }


@router.post("/magic-link")
def send_magic_link(
    body: MagicLinkRequest,
    request: Request,
    db: DBSession = Depends(get_db)
):
    """Send a magic link login email. Always returns 200 to avoid leaking whether the email exists."""
    shareholder = db.query(Shareholder).filter(func.lower(Shareholder.email) == body.email.strip().lower()).first()
    if shareholder:
        login_token = LoginTokenService.create_token(db, shareholder.email, shareholder.id)
        frontend_base_url = resolve_frontend_base_url(request)
        login_url = LoginTokenService.get_login_url(login_token.token, frontend_base_url)
        send_login_email(shareholder.email, login_url, shareholder.first_name)

    return {"message": "If an account exists with that email, a sign-in link has been sent."}


@router.post("/magic-link/verify")
def verify_magic_link(
    body: MagicLinkVerify,
    response: Response,
    db: DBSession = Depends(get_db)
):
    """Verify a magic link token and create a session."""
    login_token = LoginTokenService.validate_token(db, body.token)
    if not login_token:
        raise HTTPException(status_code=400, detail="This link is invalid or has expired.")

    shareholder = db.query(Shareholder).filter(Shareholder.id == login_token.shareholder_id).first()
    if not shareholder:
        raise HTTPException(status_code=400, detail="Account not found.")

    session = AuthService.create_session(db, shareholder.id)

    is_production = settings.environment == "production"
    response.set_cookie(
        key="session_id",
        value=session.id,
        httponly=True,
        samesite="lax",
        secure=is_production or settings.demo_mode,
        max_age=60 * 60 * 24 * settings.session_expire_days,
    )

    return {
        "message": "Login successful",
        "shareholder": shareholder_to_response(db, shareholder)
    }


@router.post("/logout")
def logout(
    response: Response,
    session_id: Optional[str] = Cookie(None),
    db: DBSession = Depends(get_db)
):
    if session_id:
        AuthService.delete_session(db, session_id)

    response.delete_cookie("session_id")
    return {"message": "Logged out"}


@router.get("/check", response_model=AuthCheckResponse)
def check_auth(
    response: Response,
    session_id: Optional[str] = Cookie(None),
    db: DBSession = Depends(get_db)
):
    set_no_store(response)
    if not session_id:
        return AuthCheckResponse(authenticated=False)

    shareholder = AuthService.get_shareholder_by_session(db, session_id)
    if not shareholder:
        return AuthCheckResponse(authenticated=False)

    return AuthCheckResponse(
        authenticated=True,
        shareholder=shareholder_to_response(db, shareholder)
    )


def get_current_shareholder(
    session_id: Optional[str] = Cookie(None),
    db: DBSession = Depends(get_db)
) -> Shareholder:
    """Dependency to get the current authenticated shareholder."""
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    shareholder = AuthService.get_shareholder_by_session(db, session_id)
    if not shareholder:
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    return shareholder


def ensure_not_viewer(
    current: Shareholder,
    detail: str = "Viewer accounts can only view the calendar.",
) -> None:
    if current.is_viewer:
        raise HTTPException(status_code=403, detail=detail)


def has_admin_access(current: Shareholder) -> bool:
    return bool(current.is_admin or current.is_superadmin)


def has_analytics_access(current: Shareholder) -> bool:
    return bool(current.is_analytics or has_admin_access(current))


@router.post("/tour-seen")
def mark_tour_seen(
    current: Shareholder = Depends(get_current_shareholder),
    db: DBSession = Depends(get_db)
):
    current.tour_seen = 1
    db.commit()
    return {"ok": True}


def require_admin(
    current: Shareholder = Depends(get_current_shareholder)
) -> Shareholder:
    """Dependency to require admin or superadmin access."""
    if not has_admin_access(current):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current


def require_analytics_access(
    current: Shareholder = Depends(get_current_shareholder)
) -> Shareholder:
    """Dependency to require analytics, admin, or superadmin access."""
    if not has_analytics_access(current):
        raise HTTPException(status_code=403, detail="Analytics access required")
    return current


def require_superadmin(
    current: Shareholder = Depends(get_current_shareholder)
) -> Shareholder:
    """Dependency to require superadmin access."""
    if not current.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return current
