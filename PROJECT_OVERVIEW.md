# Book-Tale — Library Management System

> **Full-featured library management system with catalog, lending, reservations, fines, reading challenges, social feed, realtime notifications, and book recommendations — built with Flask + SQLAlchemy + Socket.IO.**

---

## Table of Contents

- [1. Title & Badges](#1-title--badges)
- [2. Executive Summary](#2-executive-summary)
- [3. Tech Stack & Core Technologies](#3-tech-stack--core-technologies)
- [4. High-Level Architecture](#4-high-level-architecture)
- [5. Complete Folder Structure Tree](#5-complete-folder-structure-tree)
- [6. Exhaustive File-by-File & Folder-by-Folder Breakdown](#6-exhaustive-file-by-file--folder-by-folder-breakdown)
- [7. Data Models & Schemas](#7-data-models--schemas)
- [8. API Surface](#8-api-surface)
- [9. Configuration & Environment Variables](#9-configuration--environment-variables)
- [10. Build, Run & Deployment Instructions](#10-build-run--deployment-instructions)
- [11. Data & Control Flow Walkthroughs](#11-data--control-flow-walkthroughs)
- [12. Dependency Graph Summary](#12-dependency-graph-summary)
- [13. Testing Strategy](#13-testing-strategy)
- [14. Known Issues, Technical Debt & Assumptions](#14-known-issues-technical-debt--assumptions)
- [15. Glossary](#15-glossary)
- [16. Changelog / Version History Summary](#16-changelog--version-history-summary)
- [17. Appendix](#17-appendix)
- [Security Notes](#security-notes)
- [Performance Considerations](#performance-considerations)
- [Suggested Onboarding Path](#suggested-onboarding-path)

---

## 1. Title & Badges

| | |
|---|---|
| **Project Name** | Book-Tale |
| **Tagline** | Community-driven library management system |
| **License** | MIT |
| **Tests** | 202 passing |
| **Routes** | 132 registered |
| **Seed Catalog** | 11,127 books |

![Tests](https://img.shields.io/badge/tests-202_passing-brightgreen)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Python](https://img.shields.io/badge/Python-3.10-blue)
![Flask](https://img.shields.io/badge/Flask-3.x-green)

---

## 2. Executive Summary

**Book-Tale** is a comprehensive library management system that digitizes library operations while adding a modern social layer. It addresses the problem that small libraries and community book exchanges lack affordable digital tools combining traditional library operations (catalog, loans, fines) with community engagement features (reviews, recommendations, reading challenges).

### What it does:

**Core Library Operations:**
- Book catalog with search, filtering, and category browsing
- Issue/return/reserve flows with concurrency-safe transactions
- Borrow limits, membership expiry, fine calculation
- Overdue tracking and borrowing history
- Reports and statistics

**Reader & Community Features:**
- Reading progress tracking + reading challenges with streaks
- Wishlist, reading lists, book reviews & ratings
- Social feed with posts, comments, likes, and follows
- Communities, book series tracking, personal reading diary
- Notifications — in-app + realtime via Socket.IO
- Gamification: badges, streaks, reading goals
- Book recommendations — rule-based "for you" and trending

**Accounts & Administration:**
- Registration/login/logout with bcrypt password hashing
- Email verification and password reset with expiring tokens
- Role-based access: user, librarian, admin
- Admin dashboard: member management, book management, settings
- Admin audit trail: append-only log of every admin-settings change

**Operations:**
- `/healthz` and `/readyz` probes
- Background jobs (Redis + RQ): cover fetch, overdue emails, token purge
- Structured logging with request IDs
- Docker: multi-stage build + docker-compose

### Key Stats:
- **202 tests** passing (unit + integration + security)
- **132 routes** registered on the Flask app
- **11,127 books** in seed catalog

---

## 3. Tech Stack & Core Technologies

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| **Language** | Python | 3.10+ | Core runtime |
| **Web Framework** | Flask | ≥3.1 | Web application |
| **ORM** | SQLAlchemy | ≥2.0 | Database ORM |
| **Migrations** | Alembic | ≥1.18 | Schema migrations |
| **Templates** | Jinja2 | — | Server-side rendering |
| **Realtime** | Flask-SocketIO | — | WebSocket communication |
| **Background Jobs** | RQ | ≥1.15,<2.0 | Task queue |
| **Cache/Queue** | Redis | ≥5.0 | Rate limiting, job queue |
| **Auth** | bcrypt | ≥4.0 | Password hashing |
| **CSRF** | Flask-WTF | ≥1.3 | CSRF protection |
| **Rate Limiting** | Flask-Limiter | ≥4.1 | Request throttling |
| **Database** | PostgreSQL | — | Production storage |
| **Database** | SQLite | — | Development storage |
| **Frontend Build** | esbuild | — | JS/CSS bundling |
| **Testing** | pytest | ≥7.4 | Unit + integration |
| **Coverage** | pytest-cov | ≥7.1 | Test coverage |
| **Code Quality** | Ruff | — | Linting |
| **Formatting** | Black | — | Code formatting |
| **Containerization** | Docker | — | Multi-stage builds |
| **CI/CD** | GitHub Actions | — | Automated pipeline |

---

## 4. High-Level Architecture

```
┌──────────────────────── Browser ────────────────────────┐
│  Jinja2 templates (base.html, macros)  +  bundled JS    │
│  (static/js → esbuild → static/dist, content-hashed)    │
└───────────────┬───────────────────────────┬─────────────┘
                │ HTTP                      │ WebSocket (Socket.IO)
┌───────────────▼───────────────────────────▼─────────────┐
│                     Flask app (web_app.py)              │
│  security headers · request-ID · CSRF · rate limiting   │
│  /healthz · /readyz                                     │
└───────────────┬─────────────────────────────────────────┘
                │ route modules (init_* on the app)
┌───────────────▼─────────────────────────────────────────┐
│  page_routes.py · social_routes.py · new_features_routes│
│  site_pages.py · auth (login/register/reset)            │
└───────────────┬─────────────────────────────────────────┘
                │ services layer
┌───────────────▼─────────────────────────────────────────┐
│  library · auth · recommender · notifications · social  │
│  reviews · gamification · series · challenges · diary   │
│  wishlist · reading_progress · communities · lists      │
└───────────────┬─────────────────────────────────────────┘
                │ storage adapter (db/storage_adapter.py)
┌───────────────▼─────────────────────────────────────────┐
│  SQLAlchemy ORM (db/models.py, db/repositories.py)      │
│  Alembic migrations (migrations/versions/)              │
│  SQLite (dev) ── PostgreSQL (prod, docker-compose)      │
└─────────────────────────────────────────────────────────┘
                │ background jobs
┌───────────────▼─────────────────────────────────────────┐
│  RQ queue + Redis                                       │
│  worker.py: RQ worker + cron scheduler                  │
│  overdue emails · cover fetch · token purge             │
└─────────────────────────────────────────────────────────┘
```

**Architectural Pattern:** Monolithic Flask with clear layering

- **Routes** call **Services**
- **Services** call **Storage Adapter**
- **Storage Adapter** owns SQLAlchemy sessions
- **Background Jobs** run via RQ + Redis

---

## 5. Complete Folder Structure Tree

```
Book-Tale/
├── web_app.py                    # Flask app setup + core routes
├── main.py                       # CLI entry point
├── start.py                      # Alternative entry point
├── worker.py                     # RQ worker + cron scheduler
├── seed_data.py                  # Seed catalog (11,127 books)
├── seed_users.py                 # Seed user accounts
├── app/
│   ├── config/
│   │   └── settings.py           # Env-driven config + fail-fast
│   ├── core/
│   │   ├── exceptions.py         # Custom exceptions
│   │   ├── logger.py             # Logging configuration
│   │   └── utils.py              # Shared utilities
│   ├── models/
│   │   ├── book.py               # Book domain dataclass
│   │   └── user.py               # User domain dataclass
│   ├── storage/
│   │   └── storage.py            # Legacy JSON persistence
│   ├── db/
│   │   ├── storage_adapter.py    # Storage adapter
│   │   ├── database.py           # SQLAlchemy setup
│   │   ├── models.py             # ORM models
│   │   ├── repositories.py       # Data access layer
│   │   └── service.py            # DB service layer
│   ├── routes/
│   │   ├── page_routes.py        # Page routes
│   │   ├── social_routes.py      # Social API routes
│   │   ├── new_features_routes.py # Challenges, lists, etc.
│   │   └── auth.py               # Auth routes
│   ├── services/
│   │   ├── library.py            # Core library operations
│   │   ├── auth.py               # Authentication
│   │   ├── recommender.py        # Recommendation engine
│   │   ├── notifications.py      # In-app notifications
│   │   ├── email_notifier.py     # SMTP email alerts
│   │   ├── social.py             # Social graph, feed
│   │   ├── reviews.py            # Book reviews
│   │   ├── gamification.py       # XP, badges, streaks
│   │   ├── reading_challenge.py  # Reading challenges
│   │   ├── reading_progress.py   # Progress tracking
│   │   ├── series.py             # Book series
│   │   ├── wishlist.py           # Wishlists
│   │   ├── lists.py              # Custom book lists
│   │   ├── communities.py        # Communities
│   │   ├── diary.py              # Reading diary
│   │   ├── cover_service.py      # Cover image fetching
│   │   └── recommendations/
│   │       └── ml/
│   │           └── Dataset/
│   │               └── books.csv # Seed catalog data
│   ├── jobs/
│   │   ├── tasks.py              # RQ task definitions
│   │   ├── jobs.py               # Job facade
│   │   └── worker.py             # Worker utilities
│   ├── realtime/
│   │   └── realtime.py           # Socket.IO handlers
│   ├── api/
│   │   └── openapi.py            # OpenAPI spec generation
│   ├── templates/                # Jinja2 templates
│   │   ├── base.html
│   │   ├── macros.html
│   │   └── ...
│   └── static/
│       ├── js/                   # Source JavaScript
│       ├── css/                  # Stylesheets
│       ├── fonts/                # Web fonts
│       └── dist/                 # esbuild output
├── migrations/                   # Alembic versions
├── scripts/
│   ├── build_frontend.mjs        # esbuild build script
│   └── seed_*.py                 # Seed scripts
├── tests/
│   ├── security/
│   │   └── test_web_security.py  # Security tests (90)
│   ├── test_auth_tokens.py       # Token tests (10)
│   ├── test_jobs.py              # Background job tests (16)
│   ├── test_db_wiring.py         # DB adapter tests (18)
│   ├── test_library.py           # Library operation tests (53)
│   ├── test_db_layer.py          # Concurrency tests (14)
│   └── test_reading_progress.py  # Progress tests (2)
├── docs/
│   ├── adr/                      # Architecture Decision Records
│   ├── runbooks/                 # Deploy/rollback runbooks
│   └── reference/                # Perf reports, postmortems
├── requirements.txt              # Python dependencies
├── Dockerfile                    # Multi-stage Docker build
├── docker-compose.yml            # App + PostgreSQL + Redis
├── .github/workflows/ci.yml      # CI pipeline
├── Makefile                      # Build/test commands
├── pyproject.toml                # Project metadata
├── README.md                     # Documentation
├── LICENSE                       # MIT License
├── CHANGELOG.md                  # Release notes
└── SMOKE_TEST.md                 # Smoke test checklist
```

---

## 6. Exhaustive File-by-File & Folder-by-Folder Breakdown

### 6.1 Root Entry Points

#### `web_app.py`
- **Purpose:** Flask application factory + Socket.IO initialization
- **Key Components:**
  - Security headers middleware
  - Request ID middleware
  - CSRF protection (Flask-WTF)
  - Rate limiting (Flask-Limiter)
  - Route registration
  - `/healthz` and `/readyz` endpoints
- **Runs:** `python web_app.py`

#### `main.py`
- **Purpose:** CLI entry point
- **Logic:** Imports CLI from `app/routes/main.py`

#### `worker.py`
- **Purpose:** RQ worker + cron scheduler
- **Background Jobs:**
  - Cover/metadata fetch
  - Overdue-email reminders (daily 09:00)
  - Expired token purge (hourly)

### 6.2 `app/config/settings.py`

- **Type:** Configuration class
- **Purpose:** Centralized config with env var support
- **Key Settings:**
  - `SECRET_KEY` — Fail-fast if unset/default
  - `DATABASE_URL` — PostgreSQL (prod) / SQLite (dev)
  - `REDIS_URL` — For rate limiting, job queue
  - `SMTP_*` — Email configuration
  - `RQ_QUEUE` — Queue name
  - `CRON_OVERDUE_EMAILS` — Cron schedule
- **Security:** `_INSECURE_SECRET_KEYS` set prevents known defaults

### 6.3 `app/db/` — Database Layer

#### `app/db/models.py`
- **Purpose:** SQLAlchemy ORM models
- **Key Models:** User, Book, Transaction, Reservation, Fine, Post, Comment, Review, Notification, AuditLog, etc.

#### `app/db/repositories.py`
- **Purpose:** Data access layer
- **Pattern:** Repository pattern wrapping SQLAlchemy queries

#### `app/db/storage_adapter.py`
- **Purpose:** Storage adapter interface
- **Role:** Routes → Services → Storage Adapter → ORM

### 6.4 `app/services/` — Business Logic

#### `app/services/library.py`
- **Purpose:** Core library operations
- **Key Functions:**
  - `checkout_book()` — Issue book with concurrency safety
  - `return_book()` — Return with fine calculation
  - `reserve_book()` — Reserve with waitlist
  - `search_books()` — Search with filtering

#### `app/services/recommender.py`
- **Purpose:** Rule-based recommendation engine
- **Strategies:**
  - Personalized (reading history + category affinity)
  - Trending (recent popular books)
  - All-time best

#### `app/services/social.py`
- **Purpose:** Social graph and feed generation
- **Features:** Follows, posts, comments, likes, hashtags

#### `app/services/gamification.py`
- **Purpose:** XP, badges, streaks, achievements
- **Gamification:** 50 levels, 20+ badges

### 6.5 `app/routes/` — Route Modules

#### `app/routes/page_routes.py`
- **Purpose:** Web page routes
- **Key Routes:** `/explore`, `/shelves`, `/recommendations`, `/analytics`, `/admin/*`

#### `app/routes/social_routes.py`
- **Purpose:** Social API endpoints
- **Key Routes:** `/api/feed`, `/api/posts`, `/api/follow/*`, `/api/search`

#### `app/routes/new_features_routes.py`
- **Purpose:** Challenges, lists, communities
- **Key Routes:** `/api/challenges`, `/api/lists`, `/api/communities`

### 6.6 `app/jobs/` — Background Jobs

#### `app/jobs/tasks.py`
- **Purpose:** RQ task definitions
- **Tasks:**
  - `fetch_book_cover()` — Async cover download
  - `send_overdue_emails()` — Batch email reminders
  - `purge_expired_tokens()` — Token cleanup

#### `app/jobs/jobs.py`
- **Purpose:** Job facade with bounded pool fallback
- **Logic:** Uses RQ if Redis available, else bounded thread pool

### 6.7 `tests/` — Test Suite

| File | Tests | Purpose |
|------|-------|---------|
| `security/test_web_security.py` | 90 | Privilege escalation, CSRF, XSS, rate limiting |
| `test_auth_tokens.py` | 10 | DB-backed token lifecycle |
| `test_jobs.py` | 16 | RQ job execution |
| `test_db_wiring.py` | 18 | Storage adapter ↔ DB |
| `test_library.py` | 53 | Core library operations |
| `test_db_layer.py` | 14 | Concurrency, atomicity |
| `test_reading_progress.py` | 2 | Progress tracking |
| **Total** | **202** | |

---

## 7. Data Models & Schemas

### Core Entities

#### User
| Field | Type | Description |
|-------|------|-------------|
| `id` | str | MEM-XXXX identifier |
| `username` | str | Unique username |
| `password_hash` | str | bcrypt hash |
| `role` | str | user/librarian/admin |
| `membership_expiry` | date | Membership validity |

#### Book
| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Primary key |
| `title` | str | Book title |
| `author` | str | Author name |
| `isbn` | str | ISBN-13 |
| `category` | str | Genre/category |
| `copies` | int | Total copies |
| `available` | int | Available copies |

#### Transaction
| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Primary key |
| `user_id` | FK → User | Borrower |
| `book_id` | FK → Book | Book |
| `issue_date` | datetime | When issued |
| `due_date` | datetime | When due |
| `return_date` | datetime | When returned (nullable) |
| `fine` | float | Late fee |

#### Post (Social)
| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Primary key |
| `user_id` | FK → User | Author |
| `content` | text | Post content |
| `created_at` | datetime | Timestamp |
| `likes` | int | Like count |

#### AuditLog
| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Primary key |
| `admin_id` | FK → User | Admin who made change |
| `action` | str | What changed |
| `old_value` | str | Previous value |
| `new_value` | str | New value |
| `ip_address` | str | Client IP |
| `timestamp` | datetime | When |

---

## 8. API Surface

### JSON Endpoints (`/api/*`)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/feed` | Social feed |
| `POST` | `/api/posts` | Create post |
| `POST` | `/api/posts/<id>/like` | Like/unlike |
| `POST` | `/api/follow/<user_id>` | Follow/unfollow |
| `GET` | `/api/search` | Search books/users |
| `POST` | `/api/reviews/<book_id>` | Add review |
| `POST` | `/api/settings/save` | Save settings |
| `GET` | `/api/analytics/monthly` | Monthly stats |
| `POST` | `/api/ai/chat` | AI Reading Companion |

### Page Routes

| Path | Purpose |
|------|---------|
| `/` | Home dashboard |
| `/books` | Book catalog |
| `/explore` | Discover books/readers |
| `/shelves` | Personal shelves |
| `/recommendations` | Book recommendations |
| `/analytics` | Reading analytics |
| `/admin/users` | User management |
| `/admin/audit` | Audit trail |
| `/settings` | User settings |
| `/healthz` | Liveness probe |
| `/readyz` | Readiness probe |

### OpenAPI

- **Live docs:** `/api/docs` (Swagger UI)
- **Spec:** `/api/openapi.json` (OpenAPI 3.1)

---

## 9. Configuration & Environment Variables

| Variable | Purpose | Default | Required |
|----------|---------|---------|----------|
| `SECRET_KEY` | Flask session secret | — | **Yes (fail-fast)** |
| `DEFAULT_ADMIN_PASSWORD` | Admin account password | — | **Yes (fail-fast)** |
| `DATABASE_URL` | PostgreSQL connection | SQLite fallback | No |
| `REDIS_URL` | Redis connection | `redis://localhost:6379/0` | No |
| `SMTP_HOST` | SMTP server | — | Optional |
| `SMTP_PORT` | SMTP port | `587` | Optional |
| `SMTP_USER` | SMTP username | — | Optional |
| `SMTP_PASSWORD` | SMTP password | — | Optional |
| `SMTP_FROM` | Sender email | `noreply@libraryms.com` | Optional |
| `FLASK_HOST` | Bind address | `0.0.0.0` | No |
| `FLASK_PORT` | Server port | `5000` | No |
| `FLASK_DEBUG` | Debug mode | `False` | No |
| `RQ_QUEUE` | Job queue name | `booktale` | No |
| `COVER_FETCH_WORKERS` | Background threads | `4` | No |
| `CRON_OVERDUE_EMAILS` | Email cron | `0 9 * * *` | No |
| `CRON_TOKEN_PURGE` | Token purge cron | `30 * * * *` | No |

---

## 10. Build, Run & Deployment Instructions

### Prerequisites
- Python 3.10+
- PostgreSQL (prod) / SQLite (dev)
- Redis (for rate limiting + jobs)
- Node.js (for frontend build)

### Local Development

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set required env vars
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export DEFAULT_ADMIN_PASSWORD="$(python -c 'import secrets; print(secrets.token_urlsafe(16))')"

# 3. Seed the catalog
python seed_data.py
python seed_users.py

# 4. Run
python web_app.py
```

### Docker

```bash
docker compose up --build
```

Services: app (:5000) + PostgreSQL + Redis + worker + nginx

### Testing

```bash
pytest tests/                    # All 202 tests
pytest tests/ --cov=db --cov-fail-under=85  # Coverage gate
```

### Frontend Build

```bash
node scripts/build_frontend.mjs
```

---

## 11. Data & Control Flow Walkthroughs

### Flow 1: Book Checkout

```
1. User searches catalog → /books page
2. User clicks "Checkout" → POST /checkout
3. login_required decorator verifies session
4. library.py checkout_book():
   a. Check user role and borrow limits
   b. Check book availability (copies > 0)
   c. Create Transaction record
   d. Decrement book.available
   e. Commit atomically (no oversell)
5. Return success → UI shows confirmation
```

### Flow 2: Social Post + Realtime

```
1. User creates post → POST /api/posts
2. social.py stores post in DB
3. Socket.IO emits "new_post" event
4. All followers' browsers receive event
5. Feed updates in real-time without refresh
```

### Flow 3: Background Cover Fetch

```
1. Book added without cover image
2. RQ job enqueued: fetch_book_cover(book_id)
3. Worker downloads from OpenLibrary API
4. Image saved to uploads directory
5. Book record updated with cover URL
6. UI shows cover on next page load
```

---

## 12. Dependency Graph Summary

### Internal Dependencies

```
web_app.py
  ├── routes/page_routes.py → services/*
  ├── routes/social_routes.py → services/social.py
  ├── routes/new_features_routes.py → services/*
  └── db/storage_adapter.py → db/models.py

worker.py
  ├── jobs/tasks.py → services/*
  └── jobs/jobs.py → jobs/tasks.py
```

### External Package Purposes

| Package | Purpose |
|---------|---------|
| `flask` | Web framework |
| `sqlalchemy` | ORM |
| `alembic` | Migrations |
| `flask-socketio` | WebSockets |
| `flask-wtf` | CSRF protection |
| `flask-limiter` | Rate limiting |
| `rq` | Background jobs |
| `redis` | Cache + job queue |
| `bcrypt` | Password hashing |
| `croniter` | Cron schedule parsing |
| `esbuild` | Frontend bundling |

---

## 13. Testing Strategy

### Test Composition

| Category | Files | Tests | Coverage |
|----------|-------|-------|----------|
| Security | `test_web_security.py` | 90 | Privilege escalation, CSRF, XSS |
| Auth Tokens | `test_auth_tokens.py` | 10 | Token lifecycle |
| Background Jobs | `test_jobs.py` | 16 | RQ execution |
| DB Wiring | `test_db_wiring.py` | 18 | Storage adapter |
| Library Core | `test_library.py` | 53 | Checkout, return, search |
| DB Layer | `test_db_layer.py` | 14 | Concurrency, atomicity |
| Progress | `test_reading_progress.py` | 2 | Reading totals |
| **Total** | | **202** | |

### Coverage Gate
- CI enforces ≥85% line coverage on `db` layer

### Running Tests

```bash
pytest tests/ -v
pytest tests/ -m "not integration"
pytest tests/security/ -v
```

---

## 14. Known Issues, Technical Debt & Assumptions

### Known Issues
1. **2 tests skipped:** Redis-dependent tests skipped when Redis unavailable
2. **Search performance:** `search_books()` loads full catalog and filters in Python

### Technical Debt
1. **App initialization:** Module-level init (not app-factory pattern)
2. **Legacy storage:** `storage.py` JSON persistence still present
3. **AI companion:** Keyword-intent, not true LLM

### Assumptions
- PostgreSQL for production, SQLite for development
- Redis available for rate limiting + job queue
- SMTP configured for email notifications

---

## 15. Glossary

| Term | Definition |
|------|------------|
| **RQ** | Redis Queue — Python job queue |
| **Socket.IO** | Real-time WebSocket communication |
| **CSRF** | Cross-Site Request Forgery |
| **ADR** | Architecture Decision Record |
| **SMOTE** | Synthetic Minority Over-sampling (not used here) |

---

## 16. Changelog / Version History Summary

Based on README.md and CHANGELOG.md:
- **Current state:** 202 tests passing, 132 routes
- **Recent additions:** RQ background jobs, admin audit trail, security headers
- **Planned:** Versioned API, Redis-backed Socket.IO, Playwright E2E

---

## 17. Appendix

### License
MIT — see LICENSE file

### Seed Data
- **Books:** 11,127 entries from `app/services/recommendations/ml/Dataset/books.csv`
- **Users:** Created via `seed_users.py`

### Architecture Decision Records
Located in `docs/adr/`:
- 0001: Fail-fast secrets
- 0002: Registration role whitelist
- 0003-0005: Template migration
- 0004: DB-backed storage
- 0006: Structured logging
- 0007: CSRF + rate-limited auth
- 0008: Health endpoints + security headers
- 0009: Multi-stage Docker
- 0010: Background jobs with RQ

---

## Security Notes

- **CSRF protection:** Enabled by default via Flask-WTF
- **Rate limiting:** Login 10/min, register 5/min, uploads 10/min
- **Password policy:** ≥12 characters enforced server-side
- **Token security:** DB-backed, single-use, time-limited
- **Upload validation:** Magic-byte verified, re-encoded server-side
- **Session security:** HttpOnly, SameSite=Lax, Secure in production

---

## Performance Considerations

- **Rate limiting:** Redis-backed (survives restarts)
- **Background jobs:** Bounded thread pool fallback
- **Cover caching:** Images stored locally
- **DB pooling:** SQLAlchemy connection pooling

---

## Suggested Onboarding Path

1. **Start with:** `README.md` → understand scope
2. **Core logic:** `app/services/library.py`
3. **Data layer:** `app/db/models.py` → `app/db/repositories.py`
4. **Routes:** `app/routes/page_routes.py`
5. **Security:** `tests/security/test_web_security.py`
6. **Background jobs:** `app/jobs/tasks.py`

---

*This document was auto-generated from comprehensive codebase analysis.*
