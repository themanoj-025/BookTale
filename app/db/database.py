"""
db/database.py - Engine & session management.

- Defaults to SQLite at <DATA_DIR>/booktale.db (dev parity with JSON files).
- Honors DATABASE_URL for PostgreSQL in production (same schema via Alembic).
- SQLite: WAL mode + busy_timeout so concurrent writers queue instead of
  erroring; check_same_thread=False because the web app is multi-threaded.
"""

import os

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config.settings import Config
from typing import Self


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _sqlite_url() -> str:
    db_path = os.path.join(Config.DATA_DIR, "booktale.db")
    return f"sqlite:///{db_path}"


def resolve_database_url() -> str:
    """Return the effective database URL (DATABASE_URL env or SQLite default)."""
    url = getattr(Config, "DATABASE_URL", "") or os.getenv("DATABASE_URL", "")
    return url.strip() or _sqlite_url()


_engine = None
_session_factory = None


def get_engine() -> Engine:
    """Create (once) and return the SQLAlchemy engine for the current URL."""
    global _engine, _session_factory
    url = resolve_database_url()

    if _engine is not None and str(_engine.url) == url:
        return _engine

    connect_args = {}
    if url.startswith("sqlite"):
        # WAL: readers don't block the single writer; busy_timeout makes
        # concurrent writers queue instead of raising "database is locked".
        connect_args = {
            "check_same_thread": False,
            "timeout": 30,
        }
    _engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)

    if url.startswith("sqlite"):

        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
            # Disable pysqlite's implicit transaction so the `begin` event
            # below controls exactly what BEGIN statement is issued.
            dbapi_connection.isolation_level = None

        @event.listens_for(_engine, "begin")
        def _sqlite_begin_immediate(conn):
            # Serialize writers: every transaction takes the write lock up
            # front (BEGIN IMMEDIATE), so two concurrent checkouts cannot both
            # read available_copies=1. This is the documented SQLAlchemy
            # recipe for pysqlite-level transaction control.
            conn.exec_driver_sql("BEGIN IMMEDIATE")

    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> sessionmaker:
    """Return the sessionmaker bound to the current engine."""
    get_engine()
    assert _session_factory is not None
    return _session_factory


def create_all() -> None:
    """Create all tables (dev convenience; production uses Alembic)."""
    import importlib

    importlib.import_module("app.db.models")  # populate Base.metadata
    Base.metadata.create_all(get_engine())


def drop_all() -> None:
    """Drop all tables (test isolation only)."""
    import importlib

    importlib.import_module("app.db.models")
    Base.metadata.drop_all(get_engine())


class session_scope:
    """Context manager providing a bound session with auto commit/rollback.

    Usage:
        with session_scope() as db:
            db.add(...)
    Commits on success, rolls back on exception.
    """

    def __init__(self) -> None:
        self._session = None

    def __enter__(self) -> Self:
        self._session = get_session_factory()()
        return self._session

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                self._session.commit()
            else:
                self._session.rollback()
        finally:
            self._session.close()
