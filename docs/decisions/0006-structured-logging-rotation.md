# ADR 0006 — Structured Logging with Rotation (Logger Rewrite)

- **Status:** Accepted (2026-08-01)
- **Deciders:** Project owner, acting senior staff engineer
- **Related code:** `logger.py`, `web_app.py` (`_request_id_middleware` → `set_request_id()`)
- **Related ADRs:** ADR 0008 (health endpoints — the request-ID middleware is defined alongside `/healthz`/`/readyz`)

---

## Context

The legacy `logger.py` was a per-call JSON rewrite: every `log()` call opened the
entire `activity.json` file, read it, appended one entry, and wrote the whole file
back. Consequences:

1. **O(n) per write** — every log call re-serialized the full history.
2. **Unbounded growth** — the file only ever grew; no rotation existed.
3. **Lost-update race** — concurrent requests (threads) each read-modify-write the
   same file with no lock, silently dropping entries.
4. **No request correlation** — log lines had no way to group all entries
   belonging to one HTTP request.

This violated the Phase-7 observability goal (structured, correlated, bounded logs).

## Decision

Replace the per-call rewrite with Python's stdlib `logging`:

- **Two rotating handlers** (`RotatingFileHandler`, 5 MB × 5 backups):
  - a human-readable text log (`Config.LOG_FILE`),
  - a machine-readable JSON log (`Config.JSON_LOG`) via a custom `_JsonFormatter`
    that emits one JSON object per line (timestamp, level, logger, message,
    module, func, line, plus optional `request_id` and structured extras:
    `actor`, `action`, `user_id`, `book_id`).
- **One `write()` per record** — `logging` issues a single write per emit, so
  concurrent appends are safe (no read-modify-write race as with the old
  per-call rewrite). Note: rotation can still interleave under multiple
  *processes*; that's fine for the single-process app today and a non-issue for
  the test suite, which uses one process.
- **Request correlation via `contextvars`** — `set_request_id()` (called by the
  web `before_request` middleware) sets a per-thread/async-task request ID that
  the JSON formatter attaches. No module-level globals, safe under concurrent
  requests and async tasks.
- **Backward-compatible public API** — `log(action, actor, extra, user_id,
  book_id)` and `get_logs(limit)` keep the legacy call signatures, so every
  existing call site (`web_app.py`, route modules, services, CLI) is unchanged.
- **`reset_logger()` test helper** — closes only *file-based* handlers (detected
  via `baseFilename`) and leaves console/stderr handlers alone, because pytest
  owns those streams. This fixes the Windows `PermissionError` where
  `shutil.rmtree` hit an open log handle.
- **Lazy reconfiguration** — `_get_logger()` re-creates handlers when
  `Config.LOG_FILE`/`Config.JSON_LOG` change (test fixtures redirect paths), so
  the test suite can sandbox logs without a restart.

## Consequences

### Positive

- O(1) appends; disk usage bounded by rotation (5 MB × 5 per stream).
- Concurrent-safe writes; structured JSON lines with request correlation.
- Tests can redirect log paths per-fixture (the `test_library.py` fixture calls
  `reset_logger()` before teardown — a regression guard for the Windows lock).

### Negative / Trade-offs

- The lazy path-reconfiguration adds subtle module state (`_log_file_path`
  tracking) that must stay in sync with fixture teardown.
- A flush-on-emit wrapper keeps `get_logs()` immediately fresh; a small
  deviation from stock `RotatingFileHandler` behavior.
- Console (stderr) handler retained for dev convenience; its level follows
  `FLASK_DEBUG`.

## Alternatives considered

- **structlog / loguru** — rejected: new dependency for marginal gain in a
  single-process Flask app; stdlib `logging` is already installed, understood,
  and adequate.
- **`TimedRotatingFileHandler`** — rejected: size-based rotation is simpler and
  sufficient at this scale.
- **Keep the per-call rewrite** — rejected: O(n), racy, unbounded; this was the
  defect being fixed.

## Regression coverage

The full suite (125 tests) passes. `tests/test_library.py::clean_data_dirs`
calls `reset_logger()` in teardown — the regression that would have reproduced
the Windows `PermissionError` before the fix.
