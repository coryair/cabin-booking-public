"""Add the default-on cancellation-availability email preference.

Usage:
    python -m db.migrate_add_cancellation_availability_alerts
    python -m db.migrate_add_cancellation_availability_alerts --pg
"""

import argparse
import logging
import os
import sqlite3
import sys
from pathlib import Path


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _sqlite_db_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "data" / "cabins.db"


def migrate_sqlite() -> None:
    db_path = _sqlite_db_path()
    if not db_path.exists():
        logger.error("Database not found at %s", db_path)
        sys.exit(1)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("DROP TABLE IF EXISTS availability_release_deliveries")
        conn.execute("DROP TABLE IF EXISTS availability_release_events")
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(shareholders)").fetchall()
        }
        if "cancellation_availability_emails_enabled" not in columns:
            conn.execute(
                "ALTER TABLE shareholders ADD COLUMN "
                "cancellation_availability_emails_enabled INTEGER NOT NULL DEFAULT 1"
            )
            logger.info("Added shareholders cancellation-availability preference")
        conn.commit()
    logger.info("Migration complete")


def migrate_postgres() -> None:
    import psycopg

    database_url = os.environ.get("POSTGRES_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("POSTGRES_URL or DATABASE_URL is required")
        sys.exit(1)

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS availability_release_deliveries")
            cur.execute("DROP TABLE IF EXISTS availability_release_events")
            cur.execute(
                "ALTER TABLE shareholders ADD COLUMN IF NOT EXISTS "
                "cancellation_availability_emails_enabled INTEGER NOT NULL DEFAULT 1"
            )
        conn.commit()
    logger.info("Migration complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Add the cancellation-availability email preference"
    )
    parser.add_argument("--pg", action="store_true", help="Use PostgreSQL")
    args = parser.parse_args()
    migrate_postgres() if args.pg else migrate_sqlite()
