# BookTale — Startup Flow

## 1. Web app

```
python web_app.py
   └─ web_app.py (root, thin entry)
        ├─ sys.path.insert(0, <project root>)
        ├─ from app.routes import web_app as _web_app
        └─ globals().update(vars(_web_app))        # re-exports app, storage, views...
             └─ app/routes/web_app.py (module body):
                  ├─ from app.config.settings import Config
                  ├─ validate_secure_config()      # fail fast on bad SECRET_KEY
                  ├─ app = Flask(__name__, template_folder=app/templates,
                  │            static_folder=app/static)
                  ├─ CSRFProtect(app)              # on by default
                  ├─ Limiter(app)                  # Redis-backed w/ memory fallback
                  ├─ storage = create_storage()    # DbStorage (default)
                  ├─ lib = Library(storage); auth = AuthManager(storage)
                  ├─ recommender/notif_mgr/social/review_mgr/book_lists/
                  │  communities/gamification/series_mgr/challenge/
                  │  reading_progress/wishlist/diary_mgr = <service>(storage)
                  ├─ socketio = init_socketio(app, storage)
                  ├─ init_social_routes(app, ...)       # app/routes/social_routes.py
                  ├─ init_feature_routes(app, ...)      # series, reading, bookmarks
                  ├─ init_page_routes(app, ...)         # explore, shelves, reports...
                  └─ init_site_pages(app, ...)          # landing, features, welcome
   └─ if __main__: socketio.run(app, host/port/debug from Config)
```

Alternative entry: `gunicorn -w 4 web_app:app` (Dockerfile CMD) — same import path.

## 2. CLI

```
python main.py
   └─ main.py (root, thin) → from app.routes.main import main; main()
        └─ bootstrap(storage, auth)  # creates default admin, initializes services
```

## 3. Launcher (web / CLI / both)

```
python start.py [--web|--cli|--both]
   └─ start.py (root, thin) → app.routes.start.main()
        └─ launches `python web_app.py` and/or `python main.py` as subprocesses
           with cwd = project root; waits for the port, opens the browser
```

## 4. Background worker

```
python worker.py          # (docker-compose worker service)
   └─ worker.py (root, thin) → from app.jobs.worker import main; main()
        └─ requires Redis (exits with a clear error if unreachable)
           ├─ RQ worker consuming Config.RQ_QUEUE
           └─ cron scheduler thread (overdue emails, token purge)
```

## 5. Database & migrations

```
alembic upgrade head      # from project root (alembic.ini prepend_sys_path = .)
   └─ migrations/env.py → from app.db.database import Base, resolve_database_url
                          importlib.import_module("app.db.models")
```

On first web boot with the DB backend, `DbStorage.__init__` calls
`db.database.create_all()` (creates tables if missing).

## 6. Frontend asset pipeline

```
npm run build
   └─ scripts/build_frontend.mjs → reads app/static/js + css, writes hashed
      bundles to app/static/dist/ + manifest.json
web runtime: asset('js/utils.js') reads app/static/dist/manifest.json
   (falls back to /static/<path> if the build hasn't run)
```
