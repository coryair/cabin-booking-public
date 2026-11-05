"""
Migration: add per-guest nights storage and guest adjustment audit table.

Adds to reservations:
  - guest_nights_json
  - guest_fee_refunded

Creates:
  - reservation_guest_adjustments

Usage:
  python -m db.migrate_add_guest_nights_and_adjustments
  python -m db.migrate_add_guest_nights_and_adjustments --pg
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

    if not _column_exists_sqlite(cur, "reservations", "guest_nights_json"):
        cur.execute("ALTER TABLE reservations ADD COLUMN guest_nights_json TEXT")
        logger.info("Added reservations.guest_nights_json")
    else:
        logger.info("reservations.guest_nights_json already exists")

    if not _column_exists_sqlite(cur, "reservations", "guest_fee_refunded"):
        cur.execute("ALTER TABLE reservations ADD COLUMN guest_fee_refunded REAL")
        cur.execute("UPDATE reservations SET guest_fee_refunded = 0 WHERE guest_fee_refunded IS NULL")
        logger.info("Added reservations.guest_fee_refunded")
    else:
        logger.info("reservations.guest_fee_refunded already exists")

    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='reservation_guest_adjustments'"
    )
    if cur.fetchone() is None:
        cur.execute(
            """
            CREATE TABLE reservation_guest_adjustments (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              reservation_id INTEGER NOT NULL,
              before_guest_nights_json TEXT NOT NULL,
              after_guest_nights_json TEXT NOT NULL,
              before_guest_fee REAL NOT NULL DEFAULT 0.0,
              after_guest_fee REAL NOT NULL DEFAULT 0.0,
              before_processing_fee REAL NOT NULL DEFAULT 0.0,
              after_processing_fee REAL NOT NULL DEFAULT 0.0,
              before_total REAL NOT NULL DEFAULT 0.0,
              after_total REAL NOT NULL DEFAULT 0.0,
              delta_guest_fee REAL NOT NULL DEFAULT 0.0,
              delta_processing_fee REAL NOT NULL DEFAULT 0.0,
              delta_total REAL NOT NULL DEFAULT 0.0,
              action TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              stripe_checkout_session_id TEXT,
              stripe_payment_intent_id TEXT,
              stripe_refund_id TEXT,
              created_by_shareholder_id INTEGER,
              error_message TEXT,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT,
              FOREIGN KEY(reservation_id) REFERENCES reservations(id) ON DELETE CASCADE,
              FOREIGN KEY(created_by_shareholder_id) REFERENCES shareholders(id) ON DELETE SET NULL,
              CHECK (action IN ('collect', 'refund', 'apply', 'none')),
              CHECK (status IN ('pending', 'applied', 'paid', 'refunded', 'failed', 'cancelled'))
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_guest_adjustments_reservation_id ON reservation_guest_adjustments(reservation_id)")
        logger.info("Created reservation_guest_adjustments table")
    else:
        logger.info("reservation_guest_adjustments table already exists")

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

    cur.execute("""
      ALTER TABLE reservations
      ADD COLUMN IF NOT EXISTS guest_nights_json TEXT
    """)
    cur.execute("""
      ALTER TABLE reservations
      ADD COLUMN IF NOT EXISTS guest_fee_refunded DOUBLE PRECISION
    """)
    cur.execute("UPDATE reservations SET guest_fee_refunded = 0 WHERE guest_fee_refunded IS NULL")

    cur.execute("""
      CREATE TABLE IF NOT EXISTS reservation_guest_adjustments (
        id SERIAL PRIMARY KEY,
        reservation_id INTEGER NOT NULL REFERENCES reservations(id) ON DELETE CASCADE,
        before_guest_nights_json TEXT NOT NULL,
        after_guest_nights_json TEXT NOT NULL,
        before_guest_fee DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        after_guest_fee DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        before_processing_fee DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        after_processing_fee DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        before_total DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        after_total DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        delta_guest_fee DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        delta_processing_fee DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        delta_total DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        action TEXT NOT NULL CHECK (action IN ('collect', 'refund', 'apply', 'none')),
        status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'applied', 'paid', 'refunded', 'failed', 'cancelled')),
        stripe_checkout_session_id TEXT,
        stripe_payment_intent_id TEXT,
        stripe_refund_id TEXT,
        created_by_shareholder_id INTEGER REFERENCES shareholders(id) ON DELETE SET NULL,
        error_message TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT
      )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_guest_adjustments_reservation_id ON reservation_guest_adjustments(reservation_id)")

    conn.commit()
    cur.close()
    conn.close()
    logger.info("Migration complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add guest nights columns and adjustment audit table")
    parser.add_argument("--pg", action="store_true", help="Use PostgreSQL instead of SQLite")
    args = parser.parse_args()

    if args.pg:
        migrate_postgres()
    else:
        migrate_sqlite()
