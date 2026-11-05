import sys
import runpy
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from config import settings  # noqa: E402

if settings.demo_mode:
    # A fresh fictional database for each function worker, never a production DB.
    runpy.run_path(str(Path(__file__).parent.parent / "backend" / "seed_local.py"))
    from db.database import SessionLocal
    from services.date_service import set_simulated_date

    with SessionLocal() as db:
        set_simulated_date(db, date(2026, 5, 25))

from main import app  # noqa: E402
