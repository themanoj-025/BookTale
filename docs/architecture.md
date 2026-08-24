# Architecture — Book-Tale (Library Management System)

A concise, current map of how Book-Tale is built. The code remains the source
of truth; this is the canonical architecture reference produced during the
v5.0 modernization pass.

## 1. System at a glance

Book-Tale is a full library-management platform: a **Flask** web app with
**Socket.IO** realtime, an **RQ** background worker, a **SQLAlchemy +
PostgreSQL** data layer with **Alembic** migrations, and an ML-powered
recommendation feature (offline comparison notebook + runtime recommender).
Four thin root entry points (`main.py`, `start.py`, `web_app.py`,
`worker.py`) forward into the `app/` package.

## 2. Layered model

```
┌──────────────────────────────────────────────────────────────────────┐
│  Entry points (thin wrappers)                                        │
│   main.py (CLI) · start.py (launcher) · web_app.py (Flask+SocketIO)  │
│   worker.py (RQ) — all forward into app/routes|jobs                  │
├──────────────────────────────────────────────────────────────────────┤
│  Interface / Presentation                                            │
│   app/routes/* (web_app, feature_routes, page_routes, site_pages,    │
│                 social_routes, main CLI)                             │
│   app/templates/* (Jinja) · app/static/* (CSS/JS/fonts/PWA)          │
│   app/realtime/ (Socket.IO events)                                   │
├──────────────────────────────────────────────────────────────────────┤
│  Application / Domain services                                       │
│   services/auth · services/books (library, reviews, series, lists,   │
│     cover_service, backup) · services/reading (diary, progress,      │
│     challenge, wishlist) · services/social (communities,             │
│     gamification) · services/notifications · services/email          │
│   services/recommendations (recommender + seed_data + ml/)           │
├──────────────────────────────────────────────────────────────────────┤
│  Data access                                                         │
│   app/db (database, models, repositories, service, storage_adapter)  │
│   app/storage (legacy adapter) · migrations/ (Alembic)               │
├──────────────────────────────────────────────────────────────────────┤
│  Background jobs                                                     │
│   app/jobs (jobs, tasks, worker) — RQ: cover fetch, overdue emails,  │
│     token purge (cron)                                               │
├──────────────────────────────────────────────────────────────────────┤
│  Cross-cutting / Configuration                                       │
│   app/core (exceptions, logger, utils) · app/config/settings         │
└──────────────────────────────────────────────────────────────────────┘
```

Dependencies flow downward and are acyclic: entry wrappers → routes →
services → db/models → config/core.

## 3. Runtime flows

### 3.1 Web request
`web_app.py` → `app.routes.web_app` Flask app (re-export shim keeps
`from web_app import app` working) → route handlers → domain services →
SQLAlchemy repositories → PostgreSQL. Real-time features (e.g. notifications)
publish via Socket.IO (`app/realtime/`).

### 3.2 Background jobs (RQ)
`worker.py` → `app.jobs.worker` (RQ worker + cron). Tasks in `app/jobs/tasks.py`:
- `job_fetch_book_cover` — async cover/metadata fetch,
- `job_send_overdue_emails` — scheduled batch,
- `job_purge_expired_tokens` — hourly reap.
Each builds its own storage handle and never raises (enhancement, not
critical path).

### 3.3 CLI
`main.py` → `app.routes.main` CLI (rich-rendered management commands).

### 3.4 Recommendations (offline ML)
`services/recommendations/ml/Model/recommendation_ml_comparison.py` benchmarks
candidate models against `ml/Dataset/books.csv` and writes evidence to
`data/generated/comparison_output/` (charts, radar, report — gitignored,
regenerated on demand). The runtime `recommender.py` uses the selected
approach against the live catalog.

## 4. Configuration surface

| Setting / file | Purpose |
|---|---|
| `app/config/settings.py` | `Config` — FLASK_HOST/PORT/DEBUG + env wiring |
| `.env.example` | Required env template |
| `alembic.ini` + `migrations/` | Schema migrations (3 revisions: initial, audit log, auth tokens) |
| `package.json` | Frontend build (`build_frontend.mjs`) → `static/dist` |

## 5. Persistence

| Artifact | Location | Note |
|---|---|---|
| PostgreSQL | external service | primary store (SQLAlchemy 2) |
| Alembic versions | `migrations/versions/` | 3 revisions tracked |
| ML dataset | `services/recommendations/ml/Dataset/books.csv` | tracked benchmark input |
| ML outputs | `data/generated/comparison_output/` | generated on demand by `recommendation_ml_comparison.py` (gitignored) |

## 6. Deployment

- **Docker**: root `Dockerfile` + `docker-compose.yml`; Nginx config in
  `docker/nginx.conf`.
- **CI** (`ci.yml`): lint, `pytest tests/ --cov` with a db-layer coverage gate
  (`--cov=db --cov-fail-under=85`), link-check, security workflows (codeql,
  gitleaks).

## 7. Key design decisions

1. **Thin entry wrappers** — root scripts only set `sys.path` and forward,
   keeping the executable surface tiny and the `app/` package importable.
2. **Backward-compatible re-export** — `web_app.py` re-exports all public
   names so tests/CLI imports keep working after the restructure.
3. **Data-layer coverage gate** — CI enforces ≥85% coverage on `app/db`.
4. **Fail-soft background jobs** — RQ tasks never raise; failures degrade to
   logs.
5. **Deliberate ML evidence** — benchmark outputs are committed as
   reproducible comparison evidence rather than gitignored (flagged for
   review, see analysis §6.1).
