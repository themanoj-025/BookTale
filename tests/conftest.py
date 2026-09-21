"""Shared pytest fixtures for the Book-Tale test suite.

History: 46 route tests under tests/ referenced an ``app_client`` fixture that
was never committed to this repository, so those tests errored with
``fixture 'app_client' not found``. This conftest restores the fixture using
the same client pattern the passing route tests already use
(``web_app.app`` + ``app.test_client()``), plus the environment defaults every
route test module sets via ``os.environ.setdefault`` (identical values, so the
per-module calls remain no-ops).

A fakeredis TCP server is started on 127.0.0.1:6379 only when no real Redis is
reachable, so integration tests that talk to ``Config.REDIS_URL`` pass locally
and in CI (CI provides a real redis:7-alpine service container).
"""

from __future__ import annotations

import os
import socket

import pytest

# --- Environment defaults -------------------------------------------------
# Must run before any test module (and therefore any app) import. Values are
# identical to what every tests/test_routes_*.py sets with os.environ.setdefault,
# so per-module setdefaults continue to win for anything they override.
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-booktale-suite")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "TestAdmin123")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")
os.environ.setdefault("RATELIMIT_ENABLED", "0")

# --- Data-path sandbox (owned here, once) -----------------------------------
# History: every route/security test module redirected Config data paths to
# its OWN tempdir at import time. Because pytest imports test modules in
# alphabetical order and the app's singletons (storage bootstrap, DB engine)
# freeze on the FIRST ``import web_app``, later modules' reassignments
# orphaned users.json from the bootstrap DB — order-dependent 302/500
# failures. The sandbox therefore lives here exactly once: conftest is
# imported before any test module, so every test sees the same redirected
# paths and one consistent bootstrap state.
import tempfile as _tempfile

import app.config.settings as _settings_mod

_TMP = _tempfile.mkdtemp(prefix="booktale_suite_")
_Config = _settings_mod.Config
_Config.DATA_DIR = os.path.join(_TMP, "data")
_Config.LOGS_DIR = os.path.join(_TMP, "logs")
_Config.BACKUPS_DIR = os.path.join(_TMP, "backups")
_Config.BOOKS_FILE = os.path.join(_Config.DATA_DIR, "books.json")
_Config.USERS_FILE = os.path.join(_Config.DATA_DIR, "users.json")
_Config.TRANSACTIONS_FILE = os.path.join(_Config.DATA_DIR, "transactions.json")
_Config.RESERVATIONS_FILE = os.path.join(_Config.DATA_DIR, "reservations.json")
_Config.FINES_FILE = os.path.join(_Config.DATA_DIR, "fines.json")
_Config.NOTIFICATIONS_FILE = os.path.join(_Config.DATA_DIR, "notifications.json")
_Config.LOG_FILE = os.path.join(_Config.LOGS_DIR, "activity.log")
_Config.JSON_LOG = os.path.join(_Config.LOGS_DIR, "activity.json")
for _d in (_Config.DATA_DIR, _Config.LOGS_DIR, _Config.BACKUPS_DIR):
    os.makedirs(_d, exist_ok=True)


def _redis_reachable(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# --- Redis fallback ---------------------------------------------------------
# Prefer a real Redis when one is listening (CI service container, developer
# machine); otherwise serve the RESP protocol in-process so redis-py clients
# connecting to Config.REDIS_URL (default redis://localhost:6379/0) work.
#
# Background jobs are additionally stubbed per-test (see the
# _disable_background_jobs autouse fixture below): pool threads race the
# suite for the shared JSON data dir and logging capture, causing flaky
# teardown ERRORs and intermittent limiter failures.
_HOST, _PORT = "127.0.0.1", 6379
if not _redis_reachable(_HOST, _PORT):
    try:
        from fakeredis import TcpFakeServer
        import threading

        _server = TcpFakeServer((_HOST, _PORT), server_type="redis")
        _thread = threading.Thread(target=_server.serve_forever, daemon=True)
        _thread.start()
        import atexit

        atexit.register(_server.shutdown)
    except ImportError:
        # fakeredis not installed: Redis-dependent tests will fail or skip on
        # their own, exactly as before this conftest existed.
        pass


# --- Fixtures ---------------------------------------------------------------


@pytest.fixture(autouse=True)
def _disable_background_jobs(request):
    """Stub the jobs funnel (app.jobs.jobs._enqueue_or_fallback) for every
    test EXCEPT the jobs module's own tests (marker-excluded): test_jobs.py
    exercises real dispatch behavior with fakes. Background pool threads race
    the suite for the shared JSON data dir and logging capture — the source
    of the flaky teardown ERRORs and intermittent limiter failures."""
    if request.node.get_closest_marker("slow"):
        yield
        return
    import app.jobs.jobs as _jobs_mod

    original = _jobs_mod._enqueue_or_fallback
    _jobs_mod._enqueue_or_fallback = lambda *a, **k: "disabled-in-tests"
    yield
    _jobs_mod._enqueue_or_fallback = original


@pytest.fixture()
def app_client():
    """Flask test client for the full application.

    Mirrors the ``client`` fixture pattern used by the passing route tests:
    import ``web_app`` lazily (at fixture use, after all test-module Config
    patching has run) and yield a test client.
    """
    from flask.testing import FlaskClient

    from web_app import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client
