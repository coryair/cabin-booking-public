from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import Generator

from config import settings

_is_postgres = not settings.database_url.startswith("sqlite")
_connect_args = {} if _is_postgres else {"check_same_thread": False}
_pool_class = NullPool if _is_postgres else None  # None = SQLAlchemy default (StaticPool for SQLite)

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    poolclass=_pool_class,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
