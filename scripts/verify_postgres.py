"""
scripts/verify_postgres.py - Postgres schema + adapter verification.

Connects to DATABASE_URL, runs Alembic migrations, verifies schema
integrity, and exercises the DbStorage adapter + LibraryService to
prove the DB layer works against PostgreSQL (not just SQLite).

Usage:
    docker compose up -d db && sleep 5
    DATABASE_URL=postgresql+psycopg2://booktale:booktale@localhost:5432/booktale \
        python scripts/verify_postgres.py

Exit codes: 0 = all checks passed, 1 = any check failed.
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)


# ── Validate URL before importing the app ──────────────────────────────
database_url = os.environ.get("DATABASE_URL", "")
if not database_url:
    logger.error("ERROR: DATABASE_URL env var is not set.")
    logger.info("Example: DATABASE_URL=postgresql+psycopg2://booktale:booktale@localhost:5432/booktale")
    sys.exit(1)
if "sqlite" in database_url.lower():
    logger.warning("WARNING: DATABASE_URL appears to be SQLite, not PostgreSQL.")
    logger.info("This script is designed for Postgres verification.")

# ── Configure app before importing db modules ──────────────────────────
os.environ.setdefault("STORAGE_BACKEND", "db")
import app.db.database as dbmod
from app.config.settings import Config

Config.DATABASE_URL = database_url

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, inspect
import psycopg2
import logging

logger = logging.getLogger(__name__)


EXPECTED_TABLES = sorted(
    [
        "books",
        "users",
        "transactions",
        "reservations",
        "fines",
        "notifications",
        "posts",
        "comments",
        "follows",
        "reviews",
        "bookshelves",
        "diary_entries",
        "wishlist_suggestions",
        "series",
        "communities",
        "reading_challenges",
        "gamification",
    ]
)

passed = 0
failed = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        logger.info(f"  PASS  {label}")
        passed += 1
    else:
        logger.error(f"  FAIL  {label}: {detail}")
        failed += 1


def main() -> int:
    logger.info("\n== Book-Tale Postgres verification ==")
    logger.info(f"   DATABASE_URL: {database_url}\n")

    # ── 1. Alembic upgrade ─────────────────────────────────────────────
    logger.info("-- Alembic migrations --")
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = AlembicConfig(os.path.join(project_root, "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    try:
        command.upgrade(cfg, "head")
        check("alembic upgrade head", True)
    except (psycopg2.OperationalError, OSError) as e:
        check("alembic upgrade head", False, str(e))
        _print_result()
        return 1

    # ── 2. Schema verification ─────────────────────────────────────────
    logger.info("\n-- Schema verification --")
    engine = create_engine(database_url)
    inspector = inspect(engine)
    actual = sorted(inspector.get_table_names())
    # alembic_version is managed by Alembic, not in our model list
    model_tables = sorted(t for t in actual if t != "alembic_version")
    check(
        "all 17 model tables present",
        model_tables == EXPECTED_TABLES,
        f"got {model_tables}",
    )

    # ── 3. Index verification (spot-check) ─────────────────────────────
    logger.info("\n-- Index spot-checks --")
    indexes = inspector.get_indexes("books")
    index_names = {idx["name"] for idx in indexes}
    check("ix_books_title exists", "ix_books_title" in index_names, f"got: {index_names}")
    check(
        "ix_books_author exists",
        "ix_books_author" in index_names,
        f"got: {index_names}",
    )
    indexes_txns = inspector.get_indexes("transactions")
    index_names_txns = {idx["name"] for idx in indexes_txns}
    check(
        "ix_txns_open_due exists",
        "ix_txns_open_due" in index_names_txns,
        f"got: {index_names_txns}",
    )
    indexes_users = inspector.get_indexes("users")
    index_names_users = {idx["name"] for idx in indexes_users}
    check(
        "ix_users_role_status exists",
        "ix_users_role_status" in index_names_users,
        f"got: {index_names_users}",
    )

    # ── 4. DbStorage round-trip ────────────────────────────────────────
    logger.info("\n-- DbStorage round-trip --")
    dbmod._engine = None
    dbmod._session_factory = None
    from app.db.storage_adapter import create_storage

    storage = create_storage()
    books = storage.load_books()
    check("load_books on fresh schema", len(books) == 0, f"got {len(books)}")
    users = storage.load_users()
    check("load_users on fresh schema", len(users) == 0, f"got {len(users)}")
    txns = storage.load_transactions()
    check("load_transactions on fresh schema", len(txns) == 0, f"got {len(txns)}")

    # ── 5. LibraryService on migrated schema ───────────────────────────
    logger.info("\n-- LibraryService on migrated schema --")
    dbmod._engine = None
    dbmod._session_factory = None
    from app.db.database import create_all, get_session_factory
    from app.db.service import LibraryService

    create_all()  # idempotent
    factory = get_session_factory()
    with factory() as db:
        db.add(
            db.models.Book(
                book_id="PG-TEST-001",
                title="Postgres Test Book",
                author="QA Author",
                isbn="9780000000002",
                category="Fiction",
                total_copies=1,
                available_copies=1,
            )
        )
        db.add(
            db.models.User(
                user_id="PG-USER-001",
                name="PG Tester",
                email="pg@test.io",
                password_hash="test",
                role="user",
                membership_status="Active",
            )
        )
        db.commit()

    svc = LibraryService()
    ok, msg = svc.issue_book("PG-USER-001", "PG-TEST-001")
    check("issue_book against Postgres", ok, msg)
    results = svc.search_books(query="Postgres", page=1, per_page=10)
    check("search_books returns results", len(results) >= 1, f"got {len(results)}")
    overdue = svc.get_overdue_list()
    check("get_overdue_list runs without error", isinstance(overdue, list))

    # ── 6. Alembic downgrade ───────────────────────────────────────────
    logger.info("\n-- Alembic downgrade --")
    try:
        command.downgrade(cfg, "base")
        engine2 = create_engine(database_url)
        actual2 = sorted(inspect(engine2).get_table_names())
        check(
            "downgrade base drops all tables",
            len(actual2) == 0,
            f"remaining: {actual2}",
        )
    except (psycopg2.OperationalError, OSError) as e:
        check("downgrade base", False, str(e))

    _print_result()
    return 1 if failed else 0


def _print_result() -> None:
    logger.info(f"\n{'=' * 50}")
    if failed == 0:
        logger.info(f"All {passed} checks PASSED")
    else:
        logger.error(f"{passed} passed, {failed} FAILED")


if __name__ == "__main__":
    sys.exit(main())
