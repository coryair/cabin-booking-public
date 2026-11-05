"""
Migration: add reservation booked-by shareholder reference.

Adds to reservations:
  - booked_by_shareholder_id

Usage:
  python -m db.migrate_add_reservation_booker
  python -m db.migrate_add_reservation_booker --pg
"""

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _sqlite_db_path():
    from pathlib import Path
    return Path(__file__).resolve().parent.parent.parent / "data" / "cabins.db"


def _column_exists_sqlite(cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return column in [row[1] for row in cursor.fetchall()]


def migrate_sqlite():
    import sqlite3

    db_path = _sqlite_db_path()
    if not db_path.exists():
        logger.error("Database not found at %s", db_path)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    if not _column_exists_sqlite(cur, "reservations", "booked_by_shareholder_id"):
        cur.execute(
            "ALTER TABLE reservations "
            "ADD COLUMN booked_by_shareholder_id INTEGER "
            "REFERENCES shareholders(id) ON DELETE SET NULL"
        )
        logger.info("Added reservations.booked_by_shareholder_id")
    else:
        logger.info("reservations.booked_by_shareholder_id already exists")

    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_reservations_booked_by_shareholder_id "
        "ON reservations(booked_by_shareholder_id)"
    )
    logger.info("Ensured idx_reservations_booked_by_shareholder_id")

    conn.commit()
    conn.close()
    logger.info("Migration complete")


def migrate_postgres():
    import os
    import psycopg2

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    conn = psycopg2.connect(database_url)
    cur = conn.cursor()

    cur.execute(
        """
        ALTER TABLE reservations
        ADD COLUMN IF NOT EXISTS booked_by_shareholder_id INTEGER
        REFERENCES shareholders(id) ON DELETE SET NULL
        """
    )
    logger.info("Ensured reservations.booked_by_shareholder_id")

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_reservations_booked_by_shareholder_id
        ON reservations(booked_by_shareholder_id)
        """
    )
    logger.info("Ensured idx_reservations_booked_by_shareholder_id")

    conn.commit()
    cur.close()
    conn.close()
    logger.info("Migration complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add reservation booked-by shareholder reference")
    parser.add_argument("--pg", action="store_true", help="Use PostgreSQL instead of SQLite")
    args = parser.parse_args()

    if args.pg:
        migrate_postgres()
    else:
        migrate_sqlite()
