from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session as DBSession

from db.database import get_db
from db.models import BookingSeason, BookingRound, Share, Shareholder
from models.booking_season import BookingSeasonCreate, BookingSeasonUpdate, BookingSeasonResponse
from .auth import get_current_shareholder, require_admin
from services.date_service import get_today
from services.booking_round_service import BookingRoundService
from utils.http_cache import set_private_cache

router = APIRouter(prefix="/api/booking-seasons", tags=["booking-seasons"])


@router.get("", response_model=list[BookingSeasonResponse])
def list_seasons(
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(get_current_shareholder)
):
    seasons = db.query(BookingSeason).order_by(BookingSeason.year.desc()).all()
    return seasons


@router.get("/current", response_model=BookingSeasonResponse)
def get_current_season(
    response: Response,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(get_current_shareholder)
):
    set_private_cache(response)
    season = db.query(BookingSeason).filter(
        BookingSeason.year == get_today(db).year
    ).first()
    if not season:
        raise HTTPException(status_code=404, detail="No booking season configured for this year")
    return season


@router.get("/windows")
def get_booking_windows(
    response: Response,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(get_current_shareholder)
):
    """Get all shares' booking windows for each round in the current season."""
    set_private_cache(response)
    today = get_today(db)
    season = db.query(BookingSeason).filter(
        BookingSeason.year == today.year
    ).first()
    if not season:
        raise HTTPException(status_code=404, detail="No booking season configured for this year")

    shares = db.query(Share).all()
    result = {}

    # Exclude any shares with priority 0 - their windows compute to invalid dates
    excluded_share_ids = {
        s.share_id for s in db.query(Share).filter(Share.priority == 0).all()
    }

    for rnd in season.rounds:
        round_name = f"round_{rnd.round_number}"
        windows = []
        for share in shares:
            if share.share_id in excluded_share_ids:
                continue
            window = BookingRoundService.get_shareholder_booking_window(
                db, share.share_id, round_name, season
            )
            if window:
                windows.append({
                    "share_id": share.share_id,
                    "share_name": share.share_name,
                    "window_start": window[0].isoformat(),
                    "window_end": window[1].isoformat(),
                })
        windows.sort(key=lambda w: w["window_start"])
        result[round_name] = windows

    return result


@router.post("", response_model=BookingSeasonResponse)
def create_season(
    data: BookingSeasonCreate,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(require_admin)
):
    existing = db.query(BookingSeason).filter(BookingSeason.year == data.year).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Season for {data.year} already exists")

    season_data = data.model_dump(exclude={"rounds"})
    season = BookingSeason(**season_data)
    for r in data.rounds:
        season.rounds.append(BookingRound(**r.model_dump()))
    db.add(season)
    db.commit()
    db.refresh(season)
    return season


@router.put("/{season_id}", response_model=BookingSeasonResponse)
def update_season(
    season_id: int,
    data: BookingSeasonUpdate,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(require_admin)
):
    season = db.query(BookingSeason).filter(BookingSeason.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    update_data = data.model_dump(exclude_unset=True)
    rounds_data = update_data.pop("rounds", None)

    for key, value in update_data.items():
        if value is not None:
            setattr(season, key, value)

    if rounds_data is not None:
        season.rounds.clear()
        for r in rounds_data:
            season.rounds.append(BookingRound(**r))

    db.commit()
    db.refresh(season)
    return season


@router.delete("/{season_id}")
def delete_season(
    season_id: int,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(require_admin)
):
    season = db.query(BookingSeason).filter(BookingSeason.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    db.delete(season)
    db.commit()
    return {"message": f"Season {season.year} deleted"}
