"""
tests/test_jobs.py - Phase 6 background-jobs tests.

Deterministic by construction: no real Redis, no real SMTP, no real network.
Covers the three RQ job functions, the jobs facade's graceful fallback to
the bounded pool when Redis is unreachable, and the cron next-run helper.
"""

import os
import sys


pytestmark = pytest.mark.slow
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

# Set the boot env vars BEFORE importing config (mirrors test_web_security.py):
# config's class body reads SECRET_KEY at import time, so if this module is
# imported before test_web_security sets os.environ, Config.SECRET_KEY would
# freeze to "" and web_app's fail-fast boot would reject the collection.
# Making the env explicit here keeps this module import-order-independent.
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-tests-only")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "TestAdmin123")

# NOTE: this module deliberately does NOT mutate Config.DATA_DIR (or any
# Config path) at import time. Other test modules (test_web_security)
# redirect those paths and the module-global SQLAlchemy engine is cached by
# URL — the last import to touch Config would hijack every later test's
# database. None of these tests need a real DB (storage, LibraryService and
# auth are monkeypatched), so the module stays side-effect-free.

import pytest

from app.config.settings import Config
from app.jobs import jobs, tasks


@pytest.fixture(autouse=True)
def _no_redis(monkeypatch):
    """Force the facade onto its fallback path for every test in this file.

    Tests here must never touch a real Redis. We stub the reachability probe
    to False so _enqueue_or_fallback always degrades to the bounded pool.
    NOTE: the shared jobs._fallback_pool singleton is deliberately left
    alone — other test modules (library → jobs) submit to it, so shutting it
    down here would break them. The pool self-heals on next use.
    """
    monkeypatch.setattr(jobs, "_redis_reachable", lambda force=False: False)
    yield


# ─────────────────────────────────────────────────────────────────────────
# Job functions
# ─────────────────────────────────────────────────────────────────────────


class TestCoverFetchJob:
    def test_persists_cover_on_success(self, monkeypatch):
        """A successful fetch updates cover_url/description/metadata."""
        from app.models.book import Book

        book = Book(
            book_id="BK-2026-0001",
            title="Test Book",
            author="A",
            isbn="123",
            category="Fiction",
            total_copies=1,
            available_copies=1,
        )
        books = {"BK-2026-0001": book}

        class _FakeStorage:
            def load_books(self, force=False):
                return books

            def save_books(self, b):
                books.update(b)

        monkeypatch.setattr(
            "app.services.books.cover_service.fetch_cover",
            lambda **kw: {
                "cover_url": "https://example.com/c.jpg",
                "description": "A great book",
                "cover_source": "openlibrary",
                "dominant_color": "#4f46e5",
                "page_count": 250,
                "genres": ["Fiction"],
            },
        )
        monkeypatch.setattr("app.db.storage_adapter.create_storage", lambda: _FakeStorage())

        result = tasks.job_fetch_book_cover("BK-2026-0001", "Test Book", "A", "123")
        assert result["ok"] is True
        assert book.cover_url == "https://example.com/c.jpg"
        assert book.description == "A great book"
        assert book.cover_fetched is True
        assert book.pages == 250
        assert book.genres == ["Fiction"]

    def test_no_cover_does_not_crash(self, monkeypatch):
        """A failed fetch returns ok=False and leaves the book untouched."""
        from app.models.book import Book

        book = Book(
            book_id="BK-2026-0001",
            title="Test",
            author="A",
            isbn="123",
            category="Fiction",
            total_copies=1,
            available_copies=1,
        )
        books = {"BK-2026-0001": book}

        class _FakeStorage:
            def load_books(self, force=False):
                return books

            def save_books(self, b):
                books.update(b)

        monkeypatch.setattr(
            "app.services.books.cover_service.fetch_cover",
            lambda **kw: {
                "cover_url": "",
                "description": "",
                "cover_source": None,
                "dominant_color": "",
                "page_count": None,
                "genres": [],
            },
        )
        monkeypatch.setattr("app.db.storage_adapter.create_storage", lambda: _FakeStorage())
        result = tasks.job_fetch_book_cover("BK-2026-0001", "Test", "A", "123")
        assert result["ok"] is False
        assert book.cover_fetched is False  # untouched

    def test_missing_book_is_handled(self, monkeypatch):
        class _FakeStorage:
            def load_books(self, force=False):
                return {}

            def save_books(self, b):
                pass

        monkeypatch.setattr(
            "app.services.books.cover_service.fetch_cover",
            lambda **kw: {
                "cover_url": "https://x/y.jpg",
                "cover_source": "openlibrary",
            },
        )
        monkeypatch.setattr("app.db.storage_adapter.create_storage", lambda: _FakeStorage())
        result = tasks.job_fetch_book_cover("BK-NOPE", "T", "A", "1")
        assert result["ok"] is False
        assert result["reason"] == "book_gone"


class TestOverdueEmailJob:
    def test_nothing_overdue_returns_zeros(self, monkeypatch):
        """Empty overdue list -> zero summary, no SMTP attempt."""
        calls = {"batch": 0}
        monkeypatch.setattr(
            "app.db.service.LibraryService",
            type("LS", (), {"get_overdue_list": lambda self: []}),
        )
        monkeypatch.setattr(
            "app.services.email.email_notifier.send_overdue_batch",
            lambda lst: calls.update(batch=calls["batch"] + 1) or {},
        )
        result = tasks.job_send_overdue_emails()
        assert result["total"] == 0
        assert calls["batch"] == 0  # never called send_overdue_batch

    def test_overdue_batch_is_sent(self, monkeypatch):
        overdue = [{"user_id": "U1", "book": "B", "days_overdue": 2}]
        monkeypatch.setattr(
            "app.db.service.LibraryService",
            type("LS", (), {"get_overdue_list": lambda self: overdue}),
        )
        monkeypatch.setattr(
            "app.services.email.email_notifier.send_overdue_batch",
            lambda lst: {"sent": 1, "failed": 0, "skipped": 0, "total": len(lst)},
        )
        result = tasks.job_send_overdue_emails()
        assert result["sent"] == 1
        assert result["total"] == 1


class TestTokenPurgeJob:
    def test_returns_removed_count(self, monkeypatch):
        monkeypatch.setattr("app.services.auth.auth.purge_expired_tokens", lambda: 7)
        assert tasks.job_purge_expired_tokens() == 7


# ─────────────────────────────────────────────────────────────────────────
# Facade (graceful degradation)
# ─────────────────────────────────────────────────────────────────────────


class TestJobsFacade:
    def test_fallback_pool_runs_job(self, monkeypatch):
        """With Redis unreachable, the job still executes on the local pool."""
        captured = []
        monkeypatch.setattr("app.jobs.tasks.job_fetch_book_cover", lambda *a: captured.append(a))

        # Make the pool submit synchronously so the test is deterministic.
        def _sync_submit(fn, *args):
            fn(*args)

        monkeypatch.setattr(
            jobs,
            "_get_pool",
            lambda: type(
                "P",
                (),
                {
                    "submit": staticmethod(_sync_submit),
                    "_shutdown": False,
                    "shutdown": staticmethod(lambda wait=False: None),
                },
            )(),
        )
        result = jobs.enqueue_cover_fetch("BK-1", "T", "A", "123")
        assert result == "pool"
        assert captured  # job executed on the pool path
        # RQ args only (book_id, title, author, isbn) — no storage.
        assert captured[0] == ("BK-1", "T", "A", "123")

    def test_pool_path_keeps_caller_storage(self, monkeypatch):
        """The in-process fallback passes the caller's storage handle through
        so the cover write lands in the caller's data store (the RQ path
        cannot serialize it and the worker builds its own)."""
        captured = []
        fake_storage = object()
        monkeypatch.setattr("app.jobs.tasks.job_fetch_book_cover", lambda *a: captured.append(a))

        def _sync_submit(fn, *args):
            fn(*args)

        monkeypatch.setattr(
            jobs,
            "_get_pool",
            lambda: type(
                "P",
                (),
                {
                    "submit": staticmethod(_sync_submit),
                    "_shutdown": False,
                    "shutdown": staticmethod(lambda wait=False: None),
                },
            )(),
        )
        jobs.enqueue_cover_fetch("BK-1", "T", "A", "123", storage=fake_storage)
        # storage appended after the four RQ args, and is the same object.
        assert captured[0] == ("BK-1", "T", "A", "123", fake_storage)

    def test_rq_path_never_receives_storage(self, monkeypatch):
        """When Redis IS reachable the job is enqueued with the 4 RQ args
        ONLY — the caller's storage handle must never be serialized to RQ
        (the worker builds its own via create_storage)."""

        enqueued = {}

        class _FakeQueue:
            def __init__(self, name, connection=None):
                pass

            def enqueue(self, fn, *args, **kwargs):
                enqueued["fn"] = fn
                enqueued["args"] = args

        monkeypatch.setattr(jobs, "_redis_reachable", lambda force=False: True)
        monkeypatch.setattr("redis.Redis.from_url", lambda *a, **k: object())
        monkeypatch.setattr("rq.Queue", _FakeQueue)
        jobs.enqueue_cover_fetch("BK-1", "T", "A", "123", storage=object())
        assert enqueued["args"] == ("BK-1", "T", "A", "123")

    def test_fallback_path_is_bounded_pool(self):
        """The fallback executor is a ThreadPoolExecutor (bounded), never an
        unbounded raw thread."""
        pool = jobs._get_pool()
        assert isinstance(
            pool,
            __import__("concurrent.futures", fromlist=["ThreadPoolExecutor"]).ThreadPoolExecutor,
        )
        assert pool._max_workers == Config.COVER_FETCH_WORKERS

    def test_disabled_flag_still_runs_on_pool(self, monkeypatch):
        monkeypatch.setattr(Config, "BACKGROUND_JOBS_ENABLED", False)
        calls = []
        monkeypatch.setattr("app.jobs.tasks.job_purge_expired_tokens", lambda: calls.append(1) or 0)

        captured = []

        def _sync_submit(fn, *args):
            captured.append(fn(*args))

        monkeypatch.setattr(
            jobs,
            "_get_pool",
            lambda: type(
                "P",
                (),
                {
                    "submit": staticmethod(_sync_submit),
                    "_shutdown": False,
                    "shutdown": staticmethod(lambda wait=False: None),
                },
            )(),
        )
        assert jobs.enqueue_token_purge() == "pool"
        assert captured


# ─────────────────────────────────────────────────────────────────────────
# Cron scheduling helper (worker.py)
# ─────────────────────────────────────────────────────────────────────────


class TestCronNextRun:
    def test_next_run_after_now_is_strictly_future(self):
        """The computed next run must be strictly after the reference time."""
        pytest.importorskip("croniter")
        from app.jobs import worker

        base = __import__("datetime", fromlist=["datetime"]).datetime.now()
        nxt = worker._next_run_after("0 9 * * *", after=base)
        assert nxt > base

    def test_cron_respects_expression(self):
        """'0 9 * * *' lands on 09:00, minute=0."""
        pytest.importorskip("croniter")
        from datetime import datetime as _dt

        from app.jobs import worker

        base = _dt(2026, 8, 1, 10, 30, 0)
        nxt = worker._next_run_after("0 9 * * *", after=base)
        # Next daily 09:00 after 2026-08-01 10:30 is 2026-08-02 09:00.
        assert nxt == _dt(2026, 8, 2, 9, 0, 0)


# ─────────────────────────────────────────────────────────────────────────
# Worker cold-start schema ensure (worker.py)
# ─────────────────────────────────────────────────────────────────────────


class TestWorkerSchemaEnsure:
    """The worker process never instantiates DbStorage (whose __init__ calls
    create_all), so DB jobs (overdue emails, token purge) would hit "no such
    table" on a cold start. worker._ensure_schema() must create the schema
    before the worker consumes jobs, and must never crash the process when
    the DB is down — the web app's bootstrap recreates the schema on its
    next start and the cron scheduler re-enqueues the job at the next
    occurrence (RQ itself does not auto-retry).
    """

    def test_cold_worker_creates_schema(self, monkeypatch):
        """A worker that starts before the web app still creates tables."""
        called = []
        monkeypatch.setattr("app.db.database.create_all", lambda: called.append(True))
        monkeypatch.delenv("STORAGE_BACKEND", raising=False)
        from app.jobs import worker

        worker._ensure_schema()
        assert called, "create_all() must run on worker startup"

    def test_schema_failure_is_non_fatal(self, monkeypatch):
        """DB down at worker start: log, never raise (RQ retries the job)."""

        def _boom():
            raise RuntimeError("db unreachable")

        monkeypatch.setattr("app.db.database.create_all", _boom)
        monkeypatch.delenv("STORAGE_BACKEND", raising=False)
        from app.jobs import worker

        worker._ensure_schema()  # must not raise

    def test_json_backend_skips_schema(self, monkeypatch):
        """Legacy JSON backend needs no relational tables — skip create_all."""
        called = []
        monkeypatch.setattr("app.db.database.create_all", lambda: called.append(True))
        monkeypatch.setenv("STORAGE_BACKEND", "json")
        from app.jobs import worker


        worker._ensure_schema()
        assert not called
