"""
Initialize database schema from SQLAlchemy models.

Usage:
    python3 backend/init_schema.py
"""

from db.database import Base, engine


def main() -> None:
    Base.metadata.create_all(bind=engine)
    print("Schema initialized.")


if __name__ == "__main__":
    main()
