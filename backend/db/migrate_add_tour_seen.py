"""
Migration: Add tour_seen column to shareholders table.

Usage:
    python -m db.migrate_add_tour_seen          # SQLite (default)
    python -m db.migrate_add_tour_seen --pg      # PostgreSQL
"""
import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _column_exists(cursor, table: str, column: str, *, is_pg: bool) -> bool:
    if is_pg:
        cursor.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s",
            (table, column),
        )
        return cursor.fetchone() is not None
    else:
        cursor.execute(f"PRAGMA table_info({table})")
        cols = [row[1] for row in cursor.fetchall()]
        return column in cols


def migrate_sqlite():
    import sqlite3
    from pathlib import Path

    db_path = Path(__file__).resolve().parent.parent.parent / "data" / "cabins.db"
    if not db_path.exists():
        logger.error("Database not found at %s", db_path)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    if _column_exists(cursor, "shareholders", "tour_seen", is_pg=False):
        logger.info("Column 'tour_seen' already exists, skipping")
    else:
        cursor.execute("ALTER TABLE shareholders ADD COLUMN tour_seen INTEGER NOT NULL DEFAULT 0")
        logger.info("Added column 'tour_seen'")

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
    cursor = conn.cursor()

    if _column_exists(cursor, "shareholders", "tour_seen", is_pg=True):
        logger.info("Column 'tour_seen' already exists, skipping")
    else:
        cursor.execute("ALTER TABLE shareholders ADD COLUMN tour_seen INTEGER NOT NULL DEFAULT 0")
        logger.info("Added column 'tour_seen'")

    conn.commit()
    cursor.close()
    conn.close()
    logger.info("Migration complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add tour_seen column to shareholders table")
    parser.add_argument("--pg", action="store_true", help="Use PostgreSQL instead of SQLite")
    args = parser.parse_args()

    if args.pg:
        migrate_postgres()
    else:
        migrate_sqlite()
