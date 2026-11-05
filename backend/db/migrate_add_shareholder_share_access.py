"""
Migration: add additional share access assignments for shareholders.

Creates:
  - shareholder_share_access

Usage:
  python -m db.migrate_add_shareholder_share_access
  python -m db.migrate_add_shareholder_share_access --pg
"""

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _sqlite_db_path():
    from pathlib import Path
    return Path(__file__).resolve().parent.parent.parent / "data" / "cabins.db"


def migrate_sqlite():
    import sqlite3

    db_path = _sqlite_db_path()
    if not db_path.exists():
        logger.error("Database not found at %s", db_path)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='shareholder_share_access'"
    )
    if cur.fetchone() is None:
        cur.execute(
            """
            CREATE TABLE shareholder_share_access (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              shareholder_id INTEGER NOT NULL,
              share_id TEXT NOT NULL,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY(shareholder_id) REFERENCES shareholders(id) ON DELETE CASCADE,
              FOREIGN KEY(share_id) REFERENCES shares(share_id) ON DELETE CASCADE,
              CONSTRAINT uq_shareholder_share_access UNIQUE (shareholder_id, share_id)
            )
            """
        )
        logger.info("Created shareholder_share_access table")
    else:
        logger.info("shareholder_share_access table already exists")

    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_shareholder_share_access_shareholder_id "
        "ON shareholder_share_access(shareholder_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_shareholder_share_access_share_id "
        "ON shareholder_share_access(share_id)"
    )
    logger.info("Ensured shareholder_share_access indexes")

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
        CREATE TABLE IF NOT EXISTS shareholder_share_access (
          id SERIAL PRIMARY KEY,
          shareholder_id INTEGER NOT NULL REFERENCES shareholders(id) ON DELETE CASCADE,
          share_id TEXT NOT NULL REFERENCES shares(share_id) ON DELETE CASCADE,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          CONSTRAINT uq_shareholder_share_access UNIQUE (shareholder_id, share_id)
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_shareholder_share_access_shareholder_id
        ON shareholder_share_access(shareholder_id)
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_shareholder_share_access_share_id
        ON shareholder_share_access(share_id)
        """
    )
    logger.info("Ensured shareholder_share_access table and indexes")

    conn.commit()
    cur.close()
    conn.close()
    logger.info("Migration complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add shareholder additional share access table")
    parser.add_argument("--pg", action="store_true", help="Use PostgreSQL instead of SQLite")
    args = parser.parse_args()

    if args.pg:
        migrate_postgres()
    else:
        migrate_sqlite()
