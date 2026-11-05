from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from db.database import get_db
from db.models import Shareholder
from models.shareholder import ShareholderResponse
from services.availability_release_service import validate_unsubscribe_token
from .auth import get_current_shareholder, shareholder_to_response


router = APIRouter(prefix="/api", tags=["availability alerts"])


class NotificationPreferenceUpdate(BaseModel):
    cancellation_availability_emails_enabled: bool


class UnsubscribeRequest(BaseModel):
    token: str


def _masked_email(email: str) -> str:
    local, _, domain = email.partition("@")
    visible = local[:1] if local else ""
    return f"{visible}***@{domain}" if domain else "***"


@router.put("/notification-preferences", response_model=ShareholderResponse)
def update_notification_preferences(
    payload: NotificationPreferenceUpdate,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder),
):
    current.cancellation_availability_emails_enabled = (
        1 if payload.cancellation_availability_emails_enabled else 0
    )
    db.commit()
    db.refresh(current)
    return shareholder_to_response(db, current)


@router.get("/notification-preferences/cancellation-availability/unsubscribe")
def validate_cancellation_availability_unsubscribe(
    token: str = Query(...),
    db: DBSession = Depends(get_db),
):
    shareholder = validate_unsubscribe_token(db, token)
    if not shareholder:
        return {"valid": False, "subscribed": False, "email": None}
    return {
        "valid": True,
        "subscribed": bool(shareholder.cancellation_availability_emails_enabled),
        "email": _masked_email(shareholder.email),
    }


@router.post("/notification-preferences/cancellation-availability/unsubscribe")
def unsubscribe_cancellation_availability(
    payload: UnsubscribeRequest,
    db: DBSession = Depends(get_db),
):
    shareholder = validate_unsubscribe_token(db, payload.token)
    if not shareholder:
        raise HTTPException(status_code=400, detail="This unsubscribe link is invalid")
    shareholder.cancellation_availability_emails_enabled = 0
    db.commit()
    return {
        "unsubscribed": True,
        "email": _masked_email(shareholder.email),
        "message": "Cancellation-availability emails are now turned off.",
    }
