# BookTale — Module Dependency Map

Dependency direction: **routes → services → storage/db → core/config/models**.
Domain services depend on storage/db, models, core (logger/exceptions), and
config — never on routes. Routes depend on services, realtime, and api.

```
                            ┌──────────────────────────┐
                            │   Entry points (root)    │
                            │  web_app.py main.py      │
                            │  start.py worker.py      │
                            └───────────┬──────────────┘
                                        │ thin re-exports / imports
              ┌─────────────────────────┼──────────────────────────┐
              ▼                         ▼                          ▼
┌───────────────────────┐  ┌──────────────────────┐  ┌───────────────────────┐
│   app/routes/         │  │   app/jobs/          │  │   app/realtime/       │
│ web_app, main, start, │  │ tasks.py jobs.py     │  │ realtime.py           │
│ page_routes, social_  │  │ worker.py            │  └──────────┬────────────┘
│ routes, feature_      │  └──────────┬───────────┘             │
│ routes, site_pages    │             │ tasks → cover_service   │
└───────────┬───────────┘             │        + db.storage     │
            │ init_*_routes(app, ...) │                          │
            ▼                         ▼                          ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        app/services/  (domain layer)                   │
│  auth/   books/ (library, lists, reviews, series, backup, cover)       │
│  email/  notifications/  reading/ (diary, progress, challenge, wishlist)│
│  recommendations/ (recommender, seed_data)   social/ (feed, clubs, gam)│
└───────────────┬────────────────────────────────────────────────────────┘
                │ uses Storage / DbStorage
                ▼
┌───────────────────────────┐      ┌───────────────────────────────┐
│   app/storage/storage.py  │      │   app/db/                     │
│   (legacy JSON Storage)   │      │ storage_adapter (DbStorage)   │
└───────────┬───────────────┘      │ database models repositories  │
            │                      │ service                       │
            ▼                      └───────────────┬───────────────┘
┌───────────────────────┐                          │ SQLAlchemy engine
│   app/config/         │                          ▼
│ settings.py (Config)  │            SQLite (dev) / PostgreSQL (prod)
└───────────┬───────────┘
            ▼
┌───────────────────────────────────────────┐
│   app/core/  (logger, exceptions, utils)  │  ← depended on by nearly all layers
│   app/models/ (Book, User dataclasses)    │
└───────────────────────────────────────────┘
```

## Key cross-cutting dependencies

| Consumer | Depends on |
| ---------- | ------------ |
| `routes/web_app.py` | all services, `db.storage_adapter`, `realtime`, `routes.main` (bootstrap) |
| `routes/page_routes.py` | services, `models.book` (CATEGORIES), `db.database` |
| `services/books/library.py` | `models.book`, `models.user`, `storage`, `jobs.jobs` (enqueue cover fetch) |
| `services/recommendations/recommender.py` | `models.book`, `storage`, `recommendations.seed_data` |
| `jobs/tasks.py` | `core.logger`, `services.books.cover_service`, `db.storage_adapter` |
| `jobs/jobs.py` | `config`, `core.logger` |
| `db/database.py` | `config`, imports `db.models` for metadata |
| `scripts/seed_users.py` | `services.auth.auth`, `models.user`, `config`, `db.storage_adapter` |

## Import conventions

- All intra-app imports use the `app.` package prefix (`from app.config.settings
  import Config`), never bare top-level modules and never `sys.path` games
  inside `app/`.
- Route modules receive their dependencies as parameters from the app factory
  (`init_*_routes(app, storage, lib, ...)`) instead of importing `web_app`
  (avoids circular imports); the rate limiter instance is exposed on
  `app.extensions["booktale_limiter"]`.
- `tasks.py` builds its own storage via `create_storage()` so jobs run
  identically through Redis or the bounded fallback pool.
