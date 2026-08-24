# ADR 0010: Background jobs with RQ (over Celery)

Status: **Accepted**

Date: 2026-08-01

## Context

Three workloads were running on the request path or on unbounded threads:

1. **Cover/metadata fetch** — `library.add_book` spawned a raw
   `threading.Thread` per book (no pool, no timeout, no backpressure), so a
   bulk import of 50 books created 50 unbounded threads.
2. **Overdue-email reminders** — only triggerable manually from the admin
   CLI/UI ("send now"), never scheduled; the workflow belongs on a cron-like
   schedule, not "triggered on access".
3. **Expired auth-token reaping** — `auth.purge_expired_tokens()` existed
   but had no production call site; stale rows were only reaped on token
   mint (opportunistic) with no periodic sweep.

The app already runs Redis in the compose stack (Flask-Limiter storage and
the Socket.IO backend), so a Redis-backed job queue adds no new
infrastructure. The requirement: move slow I/O (SMTP, external cover APIs)
off the request thread, make the overdue batch a real scheduled job, and
give the token purge a periodic sweep — while degrading gracefully when
Redis is unavailable (local dev, Redis outage).

## Decision

Adopt **RQ** as the background job queue, with a single worker service that
also runs a small cron scheduler thread. Deliverables:

- `tasks.py` — job functions (`job_fetch_book_cover`,
  `job_send_overdue_emails`, `job_purge_expired_tokens`), each building its
  own storage handle. The cover job never raises (a cover is an
  enhancement, not a correctness dependency); the email/purge jobs may
  raise on a DB/SMTP failure so RQ's retry policy can act on it.
- `jobs.py` — a facade used by web/CLI code: enqueue to the RQ queue when
  Redis is reachable, otherwise fall back to a **bounded**
  `ThreadPoolExecutor` (`COVER_FETCH_WORKERS`, default 4). The unbounded
  raw-thread pattern is gone; the fallback is bounded in every mode.
- `worker.py` — the compose `worker` service entrypoint: an RQ `Worker` on
  `Config.RQ_QUEUE` plus a daemon scheduler thread that keeps each cron job
  scheduled one occurrence ahead. Restart-safe via a Redis key per job
  (`booktale:cron:<name>:last`) so a rolling restart cannot double-fire a
  daily run.
- Cron expressions via **croniter** (5-field): overdue emails
  `0 9 * * *` (daily 09:00), token purge `30 * * * *` (hourly). Both
  overridable with `CRON_OVERDUE_EMAILS` / `CRON_TOKEN_PURGE`.

## Why RQ over Celery

- **Fit for purpose:** the workloads are simple, few, and short — RQ's
  model (one queue, function-as-job, Redis durability) maps 1:1. Celery
  brings brokers, beat, result backends, and worker pools sized for far
  more complex graphs; that is overhead, not capability, here.
- **Python-version and dependency surface:** RQ is a single small package
  with no transitive broker client beyond `redis` (already a dependency);
  Celery pulls in `kombu`, `billiard`, and a heavier config surface.
- **Operational simplicity:** `rq worker` semantics are transparent; job
  state lives in the Redis the stack already runs. Debugging is a `redis-cli
  LRANGE booktale` away.
- **Consistency:** Flask-Limiter and Socket.IO already use the same Redis;
  one infrastructure primitive (Redis) for rate limits, realtime, and jobs.

## Consequences

- **Positive:** slow work leaves the request path; the overdue batch runs on
  a real schedule; expired tokens are swept hourly; a Redis outage degrades
  to a bounded local pool instead of failing the feature or spawning
  unbounded threads.
- **Negative/trade-offs:** RQ is in-process only — no cross-language
  producers (not a requirement); no built-in cron (we add a 30-line
  scheduler thread + croniter instead of pulling in rq-scheduler); job
  functions are module-level and importable (they are).
- **Retention:** per-job timeouts — cover fetch and token purge use
  `COVER_FETCH_TIMEOUT_SECONDS` (default 120 s); the overdue-email batch
  (SMTP sends sequentially, 15 s each) uses `EMAIL_BATCH_TIMEOUT_SECONDS`
  (default 1800 s). RQ's default retry policy applies on worker crash;
  failures are logged with full context by the structured logger.

## Tests

`tests/test_jobs.py` covers the three job functions (success, no-op, and
error paths), the facade's graceful fallback to the bounded pool with Redis
unreachable, and the cron next-run helper — all deterministic with no real
Redis/SMTP/network.
