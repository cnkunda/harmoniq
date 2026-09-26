from __future__ import annotations

import logging
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger("harmoniq.db")

_engine = None
_session_maker: sessionmaker[Session] | None = None

def get_database_url_sync() -> str:
    url = os.getenv("DATABASE_URL_SYNC", "").strip()
    if url:
        return url
    return "postgresql://harmoniq:harmoniq_dev@localhost:5432/harmoniq"

def init_db() -> None:
    global _engine, _session_maker
    if _engine is not None:
        return
    database_url = get_database_url_sync()
    logger.info("Initializing database: %s", database_url.replace("harmoniq_dev", "****"))
    _engine = create_engine(database_url, echo=False, pool_size=5, max_overflow=10)
    _session_maker = sessionmaker(_engine)

def close_db() -> None:
    global _engine, _session_maker
    if _engine is not None:
        _engine.dispose()
        _engine = None
        _session_maker = None
        logger.info("Database connection closed")

def get_session() -> Session:
    if _session_maker is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _session_maker()

def get_engine():
    return _engine
