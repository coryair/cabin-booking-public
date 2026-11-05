"""
Migration: add viewer-only role flags to shareholders and invitations.

Usage:
  python -m db.migrate_add_viewer_role
  python -m db.migrate_add_viewer_role --pg
"""

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _sqlite_db_path():
    from pathlib import Path
    return Path(__file__).resolve().parent.parent.parent / "data" / "cabins.db"


def _sqlite_column_exists(cur, table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def migrate_sqlite():
    import sqlite3

    db_path = _sqlite_db_path()
    if not db_path.exists():
        logger.error("Database not found at %s", db_path)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    if not _sqlite_column_exists(cur, "shareholders", "is_viewer"):
        cur.execute("ALTER TABLE shareholders ADD COLUMN is_viewer INTEGER NOT NULL DEFAULT 0")
        logger.info("Added shareholders.is_viewer")
    else:
        logger.info("shareholders.is_viewer already exists")

    if not _sqlite_column_exists(cur, "invitations", "is_viewer"):
        cur.execute("ALTER TABLE invitations ADD COLUMN is_viewer INTEGER NOT NULL DEFAULT 0")
        logger.info("Added invitations.is_viewer")
    else:
        logger.info("invitations.is_viewer already exists")

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
        ALTER TABLE shareholders
        ADD COLUMN IF NOT EXISTS is_viewer INTEGER NOT NULL DEFAULT 0
        """
    )
    cur.execute(
        """
        ALTER TABLE invitations
        ADD COLUMN IF NOT EXISTS is_viewer INTEGER NOT NULL DEFAULT 0
        """
    )

    logger.info("Ensured viewer columns exist")

    conn.commit()
    cur.close()
    conn.close()
    logger.info("Migration complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add viewer-only role flags")
    parser.add_argument("--pg", action="store_true", help="Use PostgreSQL instead of SQLite")
    args = parser.parse_args()

    if args.pg:
        migrate_postgres()
    else:
        migrate_sqlite()
