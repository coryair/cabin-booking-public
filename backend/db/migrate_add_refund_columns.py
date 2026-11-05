"""
Migration: Add refund/cancellation columns to reservations table.

Adds: cancelled_at, refund_amount, refunded_at, stripe_refund_id, cancellation_reason
Updates CHECK constraint to allow 'cancelled' and 'refunded' statuses.

Usage:
    python -m db.migrate_add_refund_columns          # SQLite (default)
    python -m db.migrate_add_refund_columns --pg      # PostgreSQL
"""
import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

NEW_COLUMNS = [
    ("cancelled_at", "TEXT"),
    ("refund_amount", "REAL"),
    ("refunded_at", "TEXT"),
    ("stripe_refund_id", "TEXT"),
    ("cancellation_reason", "TEXT"),
]


def _column_exists(cursor, table: str, column: str, *, is_pg: bool) -> bool:
    if is_pg:
        cursor.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s",
            (table, column),
        )
    else:
        cursor.execute(f"PRAGMA table_info({table})")
        cols = [row[1] for row in cursor.fetchall()]
        return column in cols
    return cursor.fetchone() is not None


def migrate_sqlite():
    import sqlite3
    from pathlib import Path

    db_path = Path(__file__).resolve().parent.parent.parent / "data" / "cabins.db"
    if not db_path.exists():
        logger.error("Database not found at %s", db_path)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    added = 0
    for col_name, col_type in NEW_COLUMNS:
        if _column_exists(cursor, "reservations", col_name, is_pg=False):
            logger.info("Column '%s' already exists, skipping", col_name)
            continue
        cursor.execute(f"ALTER TABLE reservations ADD COLUMN {col_name} {col_type}")
        logger.info("Added column '%s' (%s)", col_name, col_type)
        added += 1

    # SQLite doesn't support ALTER CONSTRAINT, so we must rebuild the table to update
    # the CHECK constraint. Without this, status='cancelled'/'refunded' will fail.
    _rebuild_sqlite_check_constraint(cursor)

    conn.commit()
    conn.close()
    logger.info("Migration complete (%d columns added)", added)


def _rebuild_sqlite_check_constraint(cursor):
    """Rebuild the reservations table to update the CHECK constraint for SQLite."""
    # Check if the constraint already allows 'cancelled'
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='reservations'")
    row = cursor.fetchone()
    if not row:
        logger.warning("Could not find reservations table DDL")
        return
    create_sql = row[0]
    if "'cancelled'" in create_sql:
        logger.info("CHECK constraint already includes 'cancelled', skipping rebuild")
        return

    logger.info("Rebuilding reservations table to update CHECK constraint...")

    # Get current column list from pragma
    cursor.execute("PRAGMA table_info(reservations)")
    columns = [col[1] for col in cursor.fetchall()]
    col_list = ", ".join(columns)

    cursor.execute("PRAGMA foreign_keys = OFF")
    cursor.execute(f"ALTER TABLE reservations RENAME TO _reservations_old")

    # Build new CREATE TABLE with updated constraint
    new_create = create_sql.replace(
        "status IN ('reserved', 'unpaid', 'paid')",
        "status IN ('reserved', 'unpaid', 'paid', 'cancelled', 'refunded')",
    )
    cursor.execute(new_create)

    cursor.execute(f"INSERT INTO reservations ({col_list}) SELECT {col_list} FROM _reservations_old")
    cursor.execute("DROP TABLE _reservations_old")
    cursor.execute("PRAGMA foreign_keys = ON")

    logger.info("CHECK constraint updated via table rebuild")


def migrate_postgres():
    import os
    import psycopg2

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    added = 0
    for col_name, col_type in NEW_COLUMNS:
        pg_type = {"TEXT": "TEXT", "REAL": "DOUBLE PRECISION"}[col_type]
        if _column_exists(cursor, "reservations", col_name, is_pg=True):
            logger.info("Column '%s' already exists, skipping", col_name)
            continue
        cursor.execute(f"ALTER TABLE reservations ADD COLUMN {col_name} {pg_type}")
        logger.info("Added column '%s' (%s)", col_name, pg_type)
        added += 1

    # Update CHECK constraint
    try:
        cursor.execute("ALTER TABLE reservations DROP CONSTRAINT IF EXISTS check_status")
        cursor.execute(
            "ALTER TABLE reservations ADD CONSTRAINT check_status "
            "CHECK (status IN ('reserved', 'unpaid', 'paid', 'cancelled', 'refunded'))"
        )
        logger.info("Updated CHECK constraint for status column")
    except Exception as e:
        logger.warning("Could not update CHECK constraint: %s", e)

    conn.commit()
    cursor.close()
    conn.close()
    logger.info("Migration complete (%d columns added)", added)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add refund columns to reservations table")
    parser.add_argument("--pg", action="store_true", help="Use PostgreSQL instead of SQLite")
    args = parser.parse_args()

    if args.pg:
        migrate_postgres()
    else:
        migrate_sqlite()
