from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import date
from sqlalchemy.orm import Session as DBSession

from db.database import get_db
from db.models import Shareholder
from .auth import require_superadmin, get_current_shareholder
from services.date_service import set_simulated_date, get_simulated_date

router = APIRouter(prefix="/api/time-travel", tags=["time-travel"])


class TimeTravelRequest(BaseModel):
    date: str  # YYYY-MM-DD


@router.get("")
def get_time_travel(
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(require_superadmin),
):
    simulated = get_simulated_date(db)
    return {
        "active": simulated is not None,
        "simulated_date": simulated.isoformat() if simulated else None,
        "real_date": date.today().isoformat(),
    }


@router.post("")
def set_time_travel(
    body: TimeTravelRequest,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(require_superadmin),
):
    try:
        d = date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    set_simulated_date(db, d)
    return {
        "active": True,
        "simulated_date": d.isoformat(),
        "real_date": date.today().isoformat(),
    }


@router.delete("")
def clear_time_travel(
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(require_superadmin),
):
    set_simulated_date(db, None)
    return {
        "active": False,
        "simulated_date": None,
        "real_date": date.today().isoformat(),
    }


@router.get("/status")
def get_time_travel_status(
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(get_current_shareholder),
):
    """Public endpoint for any authenticated user to check time travel status."""
    simulated = get_simulated_date(db)
    return {
        "active": simulated is not None,
        "simulated_date": simulated.isoformat() if simulated else None,
    }
