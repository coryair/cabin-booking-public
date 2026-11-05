from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session as DBSession

from db.database import get_db
from db.models import Cabin, Shareholder
from models.cabin import CabinCreate, CabinResponse, CabinUpdate
from .auth import get_current_shareholder, require_admin
from utils.http_cache import set_private_cache

router = APIRouter(prefix="/api/cabins", tags=["cabins"])


@router.get("", response_model=list[CabinResponse])
def list_cabins(
    response: Response,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(get_current_shareholder)
):
    set_private_cache(response)
    cabins = db.query(Cabin).all()
    return cabins


@router.get("/{cabin_id}", response_model=CabinResponse)
def get_cabin(
    cabin_id: str,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(get_current_shareholder)
):
    cabin = db.query(Cabin).filter(Cabin.cabin_id == cabin_id).first()
    if not cabin:
        raise HTTPException(status_code=404, detail="Cabin not found")
    return cabin


@router.post("", response_model=CabinResponse)
def create_cabin(
    cabin: CabinCreate,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(require_admin)
):
    """Create a new cabin (admin+ only)."""
    existing = db.query(Cabin).filter(Cabin.cabin_id == cabin.cabin_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Cabin already exists")

    db_cabin = Cabin(
        cabin_id=cabin.cabin_id,
        cabin_name=cabin.cabin_name,
        description=cabin.description,
        max_guests=cabin.max_guests
    )
    db.add(db_cabin)
    db.commit()
    db.refresh(db_cabin)
    return db_cabin


@router.put("/{cabin_id}", response_model=CabinResponse)
def update_cabin(
    cabin_id: str,
    update: CabinUpdate,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(require_admin)
):
    """Update a cabin (admin+ only)."""
    cabin = db.query(Cabin).filter(Cabin.cabin_id == cabin_id).first()
    if not cabin:
        raise HTTPException(status_code=404, detail="Cabin not found")

    if update.cabin_name is not None:
        cabin.cabin_name = update.cabin_name
    if update.description is not None:
        cabin.description = update.description
    if update.max_guests is not None:
        cabin.max_guests = update.max_guests

    db.commit()
    db.refresh(cabin)
    return cabin


@router.delete("/{cabin_id}")
def delete_cabin(
    cabin_id: str,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(require_admin)
):
    """Delete a cabin (admin+ only)."""
    cabin = db.query(Cabin).filter(Cabin.cabin_id == cabin_id).first()
    if not cabin:
        raise HTTPException(status_code=404, detail="Cabin not found")

    db.delete(cabin)
    db.commit()
    return {"message": "Cabin deleted"}
