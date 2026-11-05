from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session as DBSession

from db.database import get_db
from db.models import Rate, Shareholder
from models.rate import RateCreate, RateResponse, RateUpdate
from .auth import get_current_shareholder, require_admin
from utils.http_cache import set_private_cache

router = APIRouter(prefix="/api/rates", tags=["rates"])


@router.get("", response_model=list[RateResponse])
def list_rates(
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(get_current_shareholder)
):
    rates = db.query(Rate).order_by(Rate.effective_date.desc()).all()
    return rates


@router.get("/current", response_model=list[RateResponse])
def get_current_rates(
    response: Response,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(get_current_shareholder)
):
    """Get the most recent rates for each season."""
    set_private_cache(response)
    from sqlalchemy import func

    # Subquery to get max effective_date per season
    subq = db.query(
        Rate.season,
        func.max(Rate.effective_date).label("max_date")
    ).group_by(Rate.season).subquery()

    rates = db.query(Rate).join(
        subq,
        (Rate.season == subq.c.season) & (Rate.effective_date == subq.c.max_date)
    ).all()

    return rates


@router.post("", response_model=RateResponse)
def create_rate(
    rate: RateCreate,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(require_admin)
):
    """Create a new rate (admin+ only)."""
    # Check if rate already exists for this season and date
    existing = db.query(Rate).filter(
        Rate.season == rate.season.value,
        Rate.effective_date == rate.effective_date
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Rate for {rate.season} season on {rate.effective_date} already exists"
        )

    db_rate = Rate(
        season=rate.season.value,
        nightly_rate=rate.nightly_rate,
        daily_rate=rate.daily_rate,
        effective_date=rate.effective_date
    )
    db.add(db_rate)
    db.commit()
    db.refresh(db_rate)
    return db_rate


@router.put("/{rate_id}", response_model=RateResponse)
def update_rate(
    rate_id: int,
    update: RateUpdate,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(require_admin)
):
    """Update a rate (admin+ only)."""
    rate = db.query(Rate).filter(Rate.id == rate_id).first()
    if not rate:
        raise HTTPException(status_code=404, detail="Rate not found")

    if update.season is not None:
        rate.season = update.season.value
    if update.nightly_rate is not None:
        rate.nightly_rate = update.nightly_rate
    if update.daily_rate is not None:
        rate.daily_rate = update.daily_rate
    if update.effective_date is not None:
        rate.effective_date = update.effective_date

    db.commit()
    db.refresh(rate)
    return rate


@router.delete("/{rate_id}")
def delete_rate(
    rate_id: int,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(require_admin)
):
    """Delete a rate (admin+ only)."""
    rate = db.query(Rate).filter(Rate.id == rate_id).first()
    if not rate:
        raise HTTPException(status_code=404, detail="Rate not found")

    db.delete(rate)
    db.commit()
    return {"message": "Rate deleted"}
