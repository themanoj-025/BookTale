# Changelog

All notable changes to **Book-Tale** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Security — DB-backed one-time tokens

- Reset/verify tokens moved out of in-memory class dicts into the
  `auth_tokens` table (Alembic migration `0003_auth_tokens`): they survive
  process restarts, expire (15 min reset / 24 h verify), and are consumed
  atomically (no TOCTOU double-use). `purge_expired_tokens()` reaps stale
  rows. Regression suite `tests/test_auth_tokens.py` (10 tests) includes a
  cold-process restart check.

### Security — Upload magic-byte verification

- `POST /api/upload` verifies content with Pillow and re-encodes
  server-side: a file renamed from HTML/JS to `.png` is rejected, and
  payloads embedded in genuine images are stripped before touching disk.
  `Pillow>=10.0.0` added to `requirements.txt`.

### Security — Password policy ≥12

- Every password surface (registration, reset form + POST, settings page +
  settings API) now enforces ≥12 characters server-side; client hints
  (minlength, strength meter) aligned. `TestPasswordPolicy` regression tests
  added; smoke scripts updated; `DEFAULT_ADMIN_PASSWORD` example raised to
  ≥12 chars.

### Added — Centralized error handlers (Phase 7)

- 400/401/403/404/405/413/415/422/429/500 now return a consistent JSON
  envelope for `/api/*` and a styled page
  (`templates/errors/error_page.html`) for browsers; 500s log the exception
  and never leak internals to clients.

### Added — Real API docs (Phase 5)

- `/api/openapi.json` serves a generated OpenAPI 3.1 spec (`api_spec.py`)
  documenting the app's actual endpoints; `/api/docs` renders Swagger UI
  (pinned CDN) with working "Try it out".
- New public trust page at `/security` documenting the security practices.

### Docs & repo hygiene

- Removed the archived `docs/assets/agents/AGENTS.md` (universal master
  prompt, no project content, zero consumers) + `.cursorrules` — the repo's
  real agent instructions live in `.github/copilot-instructions.md`.
  Dropped their `.dockerignore` exclusions (2026-08-15 docs audit).
- `docs/../reference/postmortem-privilege-escalation.md` (blameless postmortem),
  `docs/runbooks/` (deploy, rollback, restore-from-backup,
  rotate-secret-key, incident-response).
- `AGENTS_FIX.md` + `.cursorrules` moved to `docs/agents/`; `AGENTS.md` kept
  at the repo root (it is the repository's agent-instruction file).
- CI now enforces a coverage gate on the `db` data layer
  (`--cov=db --cov-fail-under=85`).

### Added — Background jobs with Redis + RQ (Phase 6)

- **`tasks.py`** — three RQ job functions: `job_fetch_book_cover` (async
  cover/metadata fetch), `job_send_overdue_emails` (scheduled batch),
  `job_purge_expired_tokens` (hourly reap). Each builds its own storage
  handle and never raises — a cover/email is an enhancement, not a
  correctness dependency.
- **`jobs.py`** — facade used by web/CLI code: enqueues to the RQ queue
  when Redis is reachable, otherwise degrades to a **bounded**
  `ThreadPoolExecutor` (`COVER_FETCH_WORKERS`, default 4). The pre-Phase-6
  unbounded raw `threading.Thread` per cover fetch is gone in every mode.
  Reachability is probed with a short timeout and cached (~10 s) so the
  request path never pays a Redis round-trip per call.
- **`worker.py`** — the compose `worker` service entrypoint: an RQ `Worker`
  on `Config.RQ_QUEUE` plus a cron scheduler thread (croniter) keeping each
  job one occurrence ahead. Restart-safe via a per-job Redis key so a
  rolling restart cannot double-fire a daily run. Cron defaults:
  `CRON_OVERDUE_EMAILS=0 9 * * *` (daily 09:00),
  `CRON_TOKEN_PURGE=30 * * * *` (hourly).
- **`docker-compose.yml`** — worker service now runs `python worker.py`
  (was a log-only stub) with DB/Redis/SMTP/cron env passthrough.
- `library.add_book` cover fetch now routes through the facade; overdue
  rows gain `book_id` (needed by the email batch). `rq>=1.15.0` +
  `croniter>=2.0.0` added to `requirements.txt`.
- New `tests/test_jobs.py` (deterministic — no real Redis/SMTP/network):
  job success/no-op/error paths, facade bounded-pool fallback, cron
  next-run helper. See **ADR 0010**
  (`docs/adr/../decisions/0010-background-jobs-rq.md`) for the RQ-over-Celery decision.

---

### Security — Rate limiting on sensitive `/api` endpoints

Flask-Limiter is now on by default (`RATELIMIT_ENABLED=1`) on top of the
app-wide `200/min` default, with explicit per-route ceilings:

- **Auth routes:** `/login` `10/min` (POST-only — `deduct_when` counts only
  **failed** credential attempts; GET page loads exempt), `/register`,
  `/forgot-password`, `/reset-password` `5/min` (POST-only — GET page loads
  exempt; they were initially scoped as plain `5/min` so the 6th page load in
  a minute 429'd — exposed by the new real-HTTP `scripts/smoke_live.py` run
  and fixed + regression-tested).
- **Password-change endpoints** (`/api/settings/save`,
  `/api/admin/settings/save`): `10/min` keyed **per account**
  (`key_func=_user_key` → `user:<id>`), so a compromised account can't be
  brute-forced from distributed IPs; `deduct_when` counts only failed attempts
  (ordinary settings toggles and successful changes are never throttled).
- **Email change** (`/api/profile/update`): `10/min`, counts only requests that
  submit an `email` field (account-takeover vector).
- **Uploads** `10/min`; **admin destructive/moderation** (series delete,
  wishlist moderate) `20/min`.
- **Shared-surface & engagement POSTs** (audit of the remaining non-sensitive
  endpoints): content spam — posts, reposts, comments, replies, reviews, lists,
  shelves — `30/min` (POST-only on GET+POST comment routes so page loads never
  consume the budget); create-heavy surfaces (clubs, wishlist suggestions)
  `10/min`; AI companion chat `30/min`; engagement manipulation (likes, votes,
  helpful, follows, list upvotes, club joins) `60/min`. Self-scoped writes
  (notifications read, bookshelves, favorites, diary, bookmarks, progress,
  deletes) deliberately stay at the `200/min` default.

### Security — Rate-limit storage moved to Redis

- Flask-Limiter now uses **Redis** (`Config.REDIS_URL`, default
  `redis://localhost:6379/0`; the compose stack passes `redis://redis:6379/0`)
  instead of per-process in-memory storage, so rate-limit budgets survive
  process restarts and are **shared across multiple gunicorn workers**.
  Override with `RATELIMIT_STORAGE_URI=memory://` for single-process runs.
- `in_memory_fallback_enabled=True`: if Redis is unreachable, limiting
  degrades to a per-process in-memory budget (fail-open, logged) instead of
  500ing every limited request — same stance as the `/readyz` DB probe.
- `redis>=5.0.0` declared in `requirements.txt`; `REDIS_URL` added to
  `.env.example`.

### Security — CSRF enabled by default

- Flask-WTF `CSRFProtect` initialized by default (`WTF_CSRF_ENABLED=1`) across
  all state-changing endpoints, with a meta-tag + fetch interceptor covering
  the entire JS API surface.

### Security — Fail-fast boot

- Refuses to start with an unset or default `SECRET_KEY` (`validate_secure_config`).

### Tests

- `tests/security/test_web_security.py` rate-limit coverage expanded
  (decorator-presence checks, `deduct_when` behavior probes, per-account keying
  probes, plain-limit 429 breach, GET/POST split probe, plus auth-form
  GET-exempt probes for register/forgot/reset: 40 GET page loads never 429,
  POST budget intact, and a decorator-scoping assertion).
- **New `scripts/smoke_live.py`**: boots a real HTTP server with CSRF + rate
  limiting **ON** (production defaults) and drives 19 journeys over real
  sockets — page loads never 429, valid register/login/password-change
  succeed, per-IP/per-user failure throttles fire 429 only on abuse, CSRF
  tokenless POST → 400, `/healthz` + `/readyz` 200. `scripts/smoke_checklist.py`
  now runs with rate limiting enabled via `RATELIMIT_ENABLED=1` (env
  overridable) — **37/37 journeys pass with limits ON**.

### Added — Admin audit trail

- **`audit_logs` table** (Alembic migration `0002_audit_log`, `db/models.py`
  `AuditLog`): append-only record of WHO changed WHAT admin setting, WHEN, and
  FROM WHERE — `admin_id`, `action`, `target`, `old_value`/`new_value`,
  `ip_address`, `user_agent`, `created_at`, with indexes on
  `(admin_id, created_at)` and `(action, created_at)`.
- **`AuditLogRepository`** (`db/repositories.py`): `add()` + indexed,
  paginated `search()`/`count()` with free-text and admin/action filters.
- **`/api/admin/settings/save` now writes audit rows**: `settings.update` per
  changed key (old → new value), `auth.failed` on failed admin-password
  verification, `admin.password_change` on rotation. SMTP/admin passwords are
  **never stored raw** — recorded as `[redacted]`. Writes are non-fatal (a
  failure is logged, never breaks the save).
- **Searchable admin UI at `/admin/audit`**: filters by text, admin ID, and
  action, with pagination; admin-only (nav link in the admin sidebar).

### Tests

- `TestAdminAuditLog` (web): page renders for admins, denied for non-admins
  (with no audit markup leaked), save writes a `settings.update` row with
  old/new/IP, failed verification writes `auth.failed`, and secret values never
  appear raw in the trail.
- `test_db_wiring.py`: audit round-trip, search/filters, and newest-first
  pagination. Suite: **157 passing**.

### Documentation

- **ADR 0007** (`docs/adr/../decisions/0007-csrf-default-on-rate-limited-auth.md`) extended
  with the full rate-limit matrix: per-IP vs per-account keying, the
  shared-surface/engagement tiers, and the explicit list of endpoints left at
  the `200/min` default.
- **README** security section updated to describe the actual limits (auth,
  password-change, upload/admin, shared-surface tiers) and refreshed test
  counts (see the Tests sections below).

---

## [1.0.0] — 2026-06-01

### Added

#### Core Application
- Flask web application with Jinja2 templating
- Book CRUD with metadata, genres, tags, and cover images
- User registration, login, and profile management
- Role-based access control: Member, Librarian, Admin
- Session-based authentication with Flask sessions

#### Social Features
- Book reviews, ratings, and comments
- User communities and groups
- Reading lists (custom shelves)
- Bookmarking system
- 25+ social API endpoints for community interactions

#### Reading Experience
- Reading progress tracking with page/percentage updates
- Reading challenges with goals and achievements
- Reading calendar and streak tracking
- Gamification: badges, XP, leaderboards
- Wishlist management

#### Discovery & Recommendations
- Book recommendation engine
- Series management and tracking
- Search and browse by genre, author, tags
- Trending and popular books

#### Real-Time Features
- Flask-SocketIO integration for real-time updates
- Live notifications for social interactions
- PWA support for mobile-friendly experience

#### AI Integration
- AI Reading Companion for book recommendations and discussions
- Personalized book suggestions based on reading history

#### Administration
- Admin dashboard with analytics
- User management and moderation tools
- Content management for books and reviews
- System settings configuration

#### Infrastructure
- JSON file-based storage with backup and recovery
- Email notifications via SMTP
- QR code generation for sharing
- Comprehensive logging with `rich` console output
- CORS support for API access

---

## [0.1.0] — Initial Development

### Added
- Project scaffolding and Flask application setup
- Basic book and user models
- Initial template structure
- Authentication foundation
