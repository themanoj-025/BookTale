"""
worker.py - RQ worker + cron scheduler entrypoint (Phase 6).

Runs in the docker-compose `worker` service (`python worker.py`) and locally
with `python worker.py`. Two responsibilities:

  1. RQ worker consuming Config.RQ_QUEUE — executes enqueued jobs
     (cover fetch, overdue emails, token purge) with retries and
     Redis-backed durability; works across all app processes.
  2. Scheduler thread — enqueues cron jobs (overdue emails daily,
     token purge hourly) at their next occurrence. Self-rescheduling and
     restart-safe: each occurrence is recorded in Redis so a worker restart
     never double-schedules a run.

Graceful degradation: if Redis is unreachable the worker exits with a clear
error (the APP still runs — jobs simply fall back to the bounded pool in
jobs.py); if rq/croniter are missing the scheduler logs and continues
polling so the stack heals when the dependency lands.

Run:
    python worker.py                  # local, with Redis at Config.REDIS_URL
    docker compose up worker          # inside the compose stack
"""

import os
import sys
import threading
from datetime import datetime

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from app.config.settings import Config
from app.core.logger import log


# ── Cron scheduling (croniter) ──────────────────────────────────────────
def _next_run_after(cron_expr: str, after: datetime | None = None) -> datetime:
    """Next datetime matching a 5-field cron expression, strictly after
    `after` (defaults to now)."""
    from croniter import croniter

    base = after or datetime.now()
    return croniter(cron_expr, base).get_next(datetime)


def _register_cron(
    conn, key_prefix: str, cron_expr: str, job_func, timeout: int
) -> None:
    """Enqueue job_func at its next cron occurrence — idempotent per run.

    Restart-safe: the next-occurrence timestamp is stored in Redis under
    `booktale:cron:<key_prefix>:last`. If it already matches, the occurrence
    was already scheduled (a previous worker start, or a concurrent restart)
    and is NOT enqueued again — so a rolling restart cannot double-fire a
    daily overdue-email run.

    `timeout` is the RQ job_timeout for this specific job (cover fetches are
    short; an overdue-email batch sends SMTP sequentially and needs a much
    larger budget).
    """
    from rq import Queue

    q = Queue(Config.RQ_QUEUE, connection=conn)
    nxt = _next_run_after(cron_expr)
    stamp = nxt.strftime("%Y-%m-%d %H:%M:%S")
    last_key = f"booktale:cron:{key_prefix}:last"
    if conn.get(last_key) == stamp.encode():
        return  # this occurrence already scheduled
    q.enqueue_at(nxt, job_func, timeout=timeout)
    conn.set(last_key, stamp)
    log(f"Scheduled {key_prefix} for {stamp} (cron '{cron_expr}')", "worker")


def _scheduler_loop(stop_event: threading.Event) -> None:
    """Polling loop: keep every cron job scheduled one occurrence ahead."""
    import redis as _redis_client

    from app.jobs.tasks import job_purge_expired_tokens, job_send_overdue_emails

    conn = _redis_client.Redis.from_url(
        Config.REDIS_URL, socket_connect_timeout=2.0, socket_timeout=2.0
    )

    cron_jobs = [
        # (key, cron, job, timeout) — timeouts are per-job: email batches
        # send SMTP sequentially (15 s each) so they get EMAIL_BATCH_*.
        (
            "overdue_emails",
            Config.CRON_OVERDUE_EMAILS,
            job_send_overdue_emails,
            Config.EMAIL_BATCH_TIMEOUT_SECONDS,
        ),
        (
            "token_purge",
            Config.CRON_TOKEN_PURGE,
            job_purge_expired_tokens,
            Config.COVER_FETCH_TIMEOUT_SECONDS,
        ),
    ]
    log(
        f"Cron scheduler started: "
        f"overdue_emails='{Config.CRON_OVERDUE_EMAILS}', "
        f"token_purge='{Config.CRON_TOKEN_PURGE}'",
        "worker",
    )
    while not stop_event.is_set():
        try:
            for prefix, cron_expr, job_func, timeout in cron_jobs:
                _register_cron(conn, prefix, cron_expr, job_func, timeout)
        except Exception as e:
            # Keep polling: a transient Redis blip must not kill the worker;
            # the next iteration re-registers anything missed.
            log(f"Scheduler tick failed: {e}", "worker")
        stop_event.wait(30)  # poll every 30 s (cron resolution is 1 minute)


def _ensure_schema() -> None:
    """Create relational tables if missing in a cold worker process.

    The web app creates the schema at bootstrap via DbStorage.__init__ →
    create_all(); the worker never instantiates DbStorage, so a worker that
    starts before the web app (or against an empty database) would have its
    DB jobs (overdue emails, token purge) fail with "no such table" and sit
    in RQ's failed registry. create_all() is a no-op when tables already
    exist and production runs Alembic ahead of the worker, so this is cheap
    and idempotent. Failure is logged, never fatal — the web app's bootstrap
    recreates the schema on its next start, and the cron scheduler re-enqueues
    the job at the next occurrence (RQ itself does not auto-retry).
    """
    if os.getenv("STORAGE_BACKEND", "db").strip().lower() == "json":
        # Legacy JSON backend needs no relational tables. NOTE: this is a
        # cleanliness measure only — the worker's DB jobs (overdue emails,
        # token purge) are DB-scoped regardless (see ADR 0010), so JSON mode
        # does not imply JSON-backed background jobs.
        return
    try:
        from app.db.database import create_all

        create_all()
        log("Worker: relational schema verified (create_all)", "worker")
    except Exception as e:
        log(
            f"Worker: schema ensure failed (DB jobs will fail until the "
            f"schema exists): {e}",
            "worker",
        )


def main() -> None:
    try:
        import redis as _redis_client
        from rq import Queue, Worker
    except ImportError as e:
        log(
            f"Cannot start worker — missing dependency ({e}). Install "
            f"rq/croniter (requirements.txt) and ensure Redis is running.",
            "worker",
        )
        raise SystemExit(1) from e

    # socket_connect_timeout gives fail-fast startup, but NO socket_timeout:
    # RQ's worker uses this connection for blocking pubsub/BRPOP and a short
    # socket timeout is interpreted as connection loss (worker quits after 2s).
    conn = _redis_client.Redis.from_url(
        Config.REDIS_URL, socket_connect_timeout=2.0
    )
    try:
        conn.ping()
    except Exception as e:
        log(
            f"Cannot start worker — Redis unreachable at {Config.REDIS_URL}: {e}",
            "worker",
        )
        raise SystemExit(1) from e

    # DB jobs (overdue emails, token purge) touch tables the worker process
    # never creates via DbStorage — ensure them before consuming jobs.
    _ensure_schema()

    stop_event = threading.Event()
    sched_thread = threading.Thread(
        target=_scheduler_loop, args=(stop_event,), daemon=True, name="cron-scheduler"
    )
    sched_thread.start()

    # rq 2.x removed the Connection context manager; pass the Redis
    # connection explicitly to Queue/Worker instead (rq >= 2.0 API).
    queue = Queue(Config.RQ_QUEUE, connection=conn)
    worker = Worker([queue], connection=conn, name="booktale-worker")
    log(f"RQ worker started on queue '{Config.RQ_QUEUE}'", "worker")
    try:
        worker.work()  # blocks; consumes jobs forever
    finally:
        stop_event.set()
        log("RQ worker stopping", "worker")


if __name__ == "__main__":
    main()
