from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session as DBSession

from config import settings
from db.models import AppSetting

SIMULATED_DATE_KEY = "simulated_date"


def _get_business_today() -> date:
    """Returns today's date in the configured booking business timezone."""
    return datetime.now(ZoneInfo(settings.booking_timezone)).date()


def get_today(db: DBSession) -> date:
    """Returns the simulated date if set, otherwise the real date."""
    sim = get_simulated_date(db)
    return sim if sim is not None else _get_business_today()


def set_simulated_date(db: DBSession, d: date | None) -> None:
    """Set or clear the simulated date in the database."""
    row = db.query(AppSetting).filter(AppSetting.key == SIMULATED_DATE_KEY).first()
    if d is None:
        if row:
            db.delete(row)
    else:
        if row:
            row.value = d.isoformat()
        else:
            db.add(AppSetting(key=SIMULATED_DATE_KEY, value=d.isoformat()))
    db.commit()


def get_simulated_date(db: DBSession) -> date | None:
    """Get the current simulated date from the database, or None if not set."""
    row = db.query(AppSetting).filter(AppSetting.key == SIMULATED_DATE_KEY).first()
    if row and row.value:
        return date.fromisoformat(row.value)
    return None
