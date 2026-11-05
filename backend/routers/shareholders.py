from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession, joinedload

from db.database import get_db
from db.models import Shareholder, Share, ShareholderShareAccess
from models.shareholder import ShareholderCreate, ShareholderResponse, ShareholderUpdate
from services.auth_service import AuthService
from .auth import get_current_shareholder, require_admin, require_superadmin, shareholder_to_response

router = APIRouter(prefix="/api/shareholders", tags=["shareholders"])


@router.get("", response_model=list[ShareholderResponse])
def list_shareholders(
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(get_current_shareholder)
):
    shareholders = db.query(Shareholder).options(
        joinedload(Shareholder.share_rel)
    ).join(Shareholder.share_rel).order_by(Share.priority).all()
    return [shareholder_to_response(db, s) for s in shareholders]


@router.get("/{shareholder_id}", response_model=ShareholderResponse)
def get_shareholder(
    shareholder_id: int,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(get_current_shareholder)
):
    shareholder = db.query(Shareholder).options(
        joinedload(Shareholder.share_rel)
    ).filter(
        Shareholder.id == shareholder_id
    ).first()
    if not shareholder:
        raise HTTPException(status_code=404, detail="Shareholder not found")
    return shareholder_to_response(db, shareholder)


@router.post("", response_model=ShareholderResponse)
def create_shareholder(
    shareholder: ShareholderCreate,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(require_superadmin)
):
    # Check if email already exists
    existing = db.query(Shareholder).filter(
        Shareholder.email == shareholder.email
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Check if share_id is valid
    share_exists = db.query(Share).filter(Share.share_id == shareholder.share).first()
    if not share_exists:
        raise HTTPException(status_code=400, detail="Invalid share ID")

    db_shareholder = Shareholder(
        share=shareholder.share,
        first_name=shareholder.first_name,
        last_name=shareholder.last_name,
        email=shareholder.email,
        phone_number=shareholder.phone_number,
        is_viewer=1 if shareholder.is_viewer else 0,
        is_analytics=1 if shareholder.is_analytics else 0,
        password_hash=AuthService.hash_password(shareholder.password)
    )
    db.add(db_shareholder)
    db.commit()
    # Refresh with eager loading for share_rel
    db_shareholder = db.query(Shareholder).options(
        joinedload(Shareholder.share_rel)
    ).filter(Shareholder.id == db_shareholder.id).first()
    return shareholder_to_response(db, db_shareholder)


@router.put("/{shareholder_id}", response_model=ShareholderResponse)
def update_shareholder(
    shareholder_id: int,
    update: ShareholderUpdate,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(get_current_shareholder)
):
    shareholder = db.query(Shareholder).options(
        joinedload(Shareholder.share_rel)
    ).filter(
        Shareholder.id == shareholder_id
    ).first()
    if not shareholder:
        raise HTTPException(status_code=404, detail="Shareholder not found")

    # Superadmin can update anyone, others can only update themselves
    is_own_profile = shareholder.id == current.id
    if not is_own_profile and not current.is_superadmin:
        raise HTTPException(status_code=403, detail="Can only update your own profile")

    # Only superadmin can change share or role flags
    if update.share is not None:
        if not current.is_superadmin:
            raise HTTPException(status_code=403, detail="Only superadmin can change share assignment")
        share_exists = db.query(Share).filter(Share.share_id == update.share).first()
        if not share_exists:
            raise HTTPException(status_code=400, detail="Invalid share ID")
        shareholder.share = update.share

    if update.is_viewer is not None:
        if not current.is_superadmin:
            raise HTTPException(status_code=403, detail="Only superadmin can change viewer status")
        shareholder.is_viewer = 1 if update.is_viewer else 0
        if update.is_viewer:
            shareholder.is_analytics = 0
            shareholder.is_admin = 0
            shareholder.is_superadmin = 0

    if update.is_analytics is not None:
        if not current.is_superadmin:
            raise HTTPException(status_code=403, detail="Only superadmin can change analytics status")
        shareholder.is_analytics = 1 if update.is_analytics else 0
        if update.is_analytics:
            shareholder.is_viewer = 0
            shareholder.is_admin = 0
            shareholder.is_superadmin = 0

    if update.is_admin is not None:
        if not current.is_superadmin:
            raise HTTPException(status_code=403, detail="Only superadmin can change admin status")
        shareholder.is_admin = 1 if update.is_admin else 0
        if update.is_admin:
            shareholder.is_viewer = 0
            shareholder.is_analytics = 0

    if update.is_superadmin is not None:
        if not current.is_superadmin:
            raise HTTPException(status_code=403, detail="Only superadmin can change superadmin status")
        shareholder.is_superadmin = 1 if update.is_superadmin else 0
        if update.is_superadmin:
            shareholder.is_viewer = 0
            shareholder.is_analytics = 0

    if update.first_name is not None:
        shareholder.first_name = update.first_name
    if update.last_name is not None:
        shareholder.last_name = update.last_name
    if update.email is not None:
        shareholder.email = update.email
    if update.phone_number is not None:
        shareholder.phone_number = update.phone_number
    if update.password is not None:
        shareholder.password_hash = AuthService.hash_password(update.password)
    if update.cancellation_availability_emails_enabled is not None:
        shareholder.cancellation_availability_emails_enabled = (
            1 if update.cancellation_availability_emails_enabled else 0
        )

    if update.additional_shares is not None:
        if not current.is_superadmin:
            raise HTTPException(status_code=403, detail="Only superadmin can change additional share access")

        target_primary = shareholder.share
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in update.additional_shares:
            share_id = (raw or "").strip()
            if not share_id or share_id == target_primary or share_id in seen:
                continue
            seen.add(share_id)
            cleaned.append(share_id)

        if cleaned:
            existing = db.query(Share.share_id).filter(Share.share_id.in_(cleaned)).all()
            existing_ids = {sid for (sid,) in existing}
            missing = [sid for sid in cleaned if sid not in existing_ids]
            if missing:
                raise HTTPException(status_code=400, detail=f"Invalid additional share ID(s): {', '.join(missing)}")

        db.query(ShareholderShareAccess).filter(
            ShareholderShareAccess.shareholder_id == shareholder.id
        ).delete(synchronize_session=False)
        for share_id in cleaned:
            db.add(ShareholderShareAccess(
                shareholder_id=shareholder.id,
                share_id=share_id,
            ))

    # Ensure primary share never exists in additional-share mapping
    db.query(ShareholderShareAccess).filter(
        ShareholderShareAccess.shareholder_id == shareholder.id,
        ShareholderShareAccess.share_id == shareholder.share,
    ).delete(synchronize_session=False)

    db.commit()
    db.refresh(shareholder)
    return shareholder_to_response(db, shareholder)


@router.delete("/{shareholder_id}")
def delete_shareholder(
    shareholder_id: int,
    db: DBSession = Depends(get_db),
    current: Shareholder = Depends(require_superadmin)
):
    """Delete a shareholder (superadmin only)."""
    shareholder = db.query(Shareholder).filter(
        Shareholder.id == shareholder_id
    ).first()
    if not shareholder:
        raise HTTPException(status_code=404, detail="Shareholder not found")

    # Cannot delete yourself
    if shareholder.id == current.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    db.delete(shareholder)
    db.commit()
    return {"message": "Shareholder deleted"}
