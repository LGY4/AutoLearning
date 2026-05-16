from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _create_engine():
    settings = get_settings()
    if settings.repository_backend != "postgres":
        return None
    connect_args = {"connect_timeout": 2} if settings.database_url.startswith("postgresql") else {}
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args=connect_args,
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600,
    )


engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False) if engine else None


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        raise RuntimeError("Database not configured (repository_backend=memory)")
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
