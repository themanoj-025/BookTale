"""
jobs.py - Background-job facade (Phase 6).

Web and CLI code never touches RQ directly. They call the helpers here,
which:

  1. Enqueue the job to the RQ queue when Redis is reachable (shared queue
     across all gunicorn workers + the worker service).
  2. Otherwise degrade to a BOUNDED ThreadPoolExecutor (never the unbounded
     raw threads of the pre-Phase-6 code) so the app keeps working without
     Redis, e.g. local dev or a Redis outage.

Reachability is probed with a short timeout and cached briefly so the
per-request path never pays a Redis round-trip per call.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from app.config.settings import Config
from app.core.logger import log

# ── Connection probe (cached for a few seconds) ─────────────────────────
_probe_lock = threading.Lock()
_probe_cache = {"ok": False, "at": datetime.min}
# Rate-limit the "Redis unreachable" log to once per 60 s so a burst of
# add_book calls while Redis is down cannot spam the log.
_fallback_log_lock = threading.Lock()
_last_fallback_log = datetime.min


def _redis_reachable(force: bool = False) -> bool:
    """True when Config.REDIS_URL answers PING (cached ~10 s)."""
    now = datetime.now()
    with _probe_lock:
        if not force and (now - _probe_cache["at"]) < timedelta(seconds=10):
            return _probe_cache["ok"]
        ok = False
        try:
            import redis as _redis_client

            _r = _redis_client.Redis.from_url(
                Config.REDIS_URL, socket_connect_timeout=0.5, socket_timeout=0.5
            )
            ok = bool(_r.ping())
        except (OSError, ConnectionError, ImportError):
            ok = False
        _probe_cache.update(ok=ok, at=now)
        return ok


def _log_fallback(job_name: str, reason: str) -> None:
    """Log a fallback transition at most once per minute."""
    global _last_fallback_log
    now = datetime.now()
    with _fallback_log_lock:
        if (now - _last_fallback_log) < timedelta(seconds=60):
            return
        _last_fallback_log = now
    log(f"Job '{job_name}' fell back to local pool: {reason}", "worker")


# ── Bounded fallback pool (replaces unbounded raw threads) ──────────────
# Sized by COVER_FETCH_WORKERS; used only when Redis/RQ is unreachable.
_fallback_pool = None
_pool_lock = threading.Lock()


def _get_pool() -> ThreadPoolExecutor:
    global _fallback_pool
    with _pool_lock:
        if _fallback_pool is None or _fallback_pool._shutdown:
            _fallback_pool = ThreadPoolExecutor(
                max_workers=Config.COVER_FETCH_WORKERS,
                thread_name_prefix="booktale-job",
            )
        return _fallback_pool


def _enqueue_or_fallback(job_name: str, fn, args: tuple, pool_args: tuple | None = None) -> str:
    """Enqueue fn(*args) to RQ; fall back to the bounded pool if Redis is
    unreachable or rq is not installed. Returns 'rq' or 'pool'.

    `args` are the RQ-serializable arguments (enqueued through Redis).
    `pool_args` may differ when the pool path needs the caller's in-process
    objects (e.g. a storage handle that cannot be serialized to RQ); it
    defaults to `args`.
    """
    if pool_args is None:
        pool_args = args
    if not Config.BACKGROUND_JOBS_ENABLED:
        # BACKGROUND_JOBS_ENABLED=False means "never contact Redis/RQ —
        # always use the bounded local pool" (e.g. CI, tests, single-process
        # dev). Jobs still run; they just never leave the process.
        _get_pool().submit(fn, *pool_args)
        return "pool"
    try:
        if _redis_reachable():
            import redis as _redis_client
            from rq import Queue

            _conn = _redis_client.Redis.from_url(Config.REDIS_URL)
            Queue(Config.RQ_QUEUE, connection=_conn).enqueue(
                fn, *args, timeout=Config.COVER_FETCH_TIMEOUT_SECONDS
            )
            return "rq"
        # Redis unreachable: bounded local pool (rate-limited log).
        _log_fallback(job_name, "Redis unreachable")
    except ImportError:
        # rq not installed: same bounded fallback.
        _log_fallback(job_name, "rq not installed")
    except (OSError, RuntimeError) as e:
        _log_fallback(job_name, f"enqueue failed: {e}")
    _get_pool().submit(fn, *pool_args)
    return "pool"


# ── Public helpers (single call sites) ───────────────────────────────────


def enqueue_cover_fetch(book_id: str, title: str, author: str, isbn: str, storage=None) -> str:
    """Fetch cover/metadata for a book off the request path.

    `storage` is used by the local-pool fallback so the cover write lands in
    the caller's data store; the RQ path cannot serialize it and the worker
    builds its own.
    """
    from app.jobs.tasks import job_fetch_book_cover

    args = (book_id, title, author, isbn)
    pool_args = args if storage is None else (*args, storage)
    return _enqueue_or_fallback("cover_fetch", job_fetch_book_cover, args, pool_args)


def enqueue_overdue_emails() -> str:
    """Trigger the overdue-email batch (used by the scheduler)."""
    from app.jobs.tasks import job_send_overdue_emails

    return _enqueue_or_fallback("overdue_emails", job_send_overdue_emails, ())


def enqueue_token_purge() -> str:
    """Trigger the expired-token purge (used by the scheduler)."""
    from app.jobs.tasks import job_purge_expired_tokens

    return _enqueue_or_fallback("token_purge", job_purge_expired_tokens, ())
