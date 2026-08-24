# BookTale — Package Overview

## What is BookTale?

A library-management system with a server-rendered web UI (Flask + Jinja2 +
Bootstrap 5), a Socket.IO realtime layer, a relational persistence layer
(SQLAlchemy), background jobs (RQ + Redis), a CLI, and a rule-based
recommendation engine with a Goodreads seed-data cold-start fallback.

## The `app` package — one home for everything

| Subpackage | Responsibility | Key modules |
| ----------- | ---------------- | ------------- |
| `app/config` | Env-driven settings, fail-fast secret validation | `settings.py` |
| `app/core` | Cross-cutting infrastructure | `logger.py`, `exceptions.py`, `utils.py` |
| `app/models` | Domain dataclasses | `book.py`, `user.py` |
| `app/storage` | Legacy JSON persistence | `storage.py` |
| `app/db` | Relational layer (default backend) | `database.py`, `models.py`, `repositories.py`, `service.py`, `storage_adapter.py` |
| `app/routes` | HTTP routes + CLI + launcher | `web_app.py`, `page_routes.py`, `social_routes.py`, `feature_routes.py`, `site_pages.py`, `main.py`, `start.py` |
| `app/services` | Domain services | `auth/`, `books/`, `email/`, `notifications/`, `reading/`, `recommendations/`, `social/` |
| `app/jobs` | Background jobs | `tasks.py`, `jobs.py`, `worker.py` |
| `app/realtime` | Socket.IO wiring | `realtime.py` |
| `app/api` | OpenAPI spec generation | `api_spec.py` |
| `app/templates` | Jinja2 templates | `base.html`, `auth/`, `errors/`, ... |
| `app/static` | Frontend assets + esbuild output | `css/`, `js/`, `fonts/`, `dist/` |

## Root directory — entry points and tooling only

- `web_app.py`, `main.py`, `start.py`, `worker.py` — thin entry points that
  delegate to `app.*`.
- `migrations/` — Alembic versions; `scripts/` — build/seed/smoke/bench;
  `tests/` — pytest suites (unit + security); `docs/` — ADRs, runbooks,
  architecture; `data/`, `logs/` — runtime data (gitignored).

## Design principles

1. **Entry points are thin.** All logic lives in `app/`; root files are 10–20
   line wrappers so `python web_app.py` / `gunicorn web_app:app` / `python
   worker.py` all work unchanged.
2. **No bare top-level imports.** Every intra-app import uses the `app.`
   prefix — no reliance on `sys.path` hacks inside `app/`.
3. **Dependencies flow downward.** routes → services → storage/db →
   core/config/models. Route modules receive dependencies as parameters
   (no circular imports).
4. **Dual storage.** `Storage` (JSON) and `DbStorage` (SQLAlchemy) implement
   the same interface; `create_storage()` selects the backend
   (`STORAGE_BACKEND=db` default).
5. **Graceful degradation.** Rate limiting falls back to in-memory when Redis
   is down; background jobs fall back to a bounded thread pool; seed data
   fills cold-start recommendations; cover fetch never breaks a book.

## Verification status (post-restructure)

- `python -m compileall app scripts tests migrations` — **OK**
- `python -m pytest tests/` — **202 passed, 2 skipped**
- Entry-point import smoke test (`web_app`, `worker`, `main`, `start`) — **OK**
  (138 routes registered)
