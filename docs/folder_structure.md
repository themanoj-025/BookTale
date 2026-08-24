# Folder Structure — Book-Tale

Canonical layout after the v5.0 modernization pass. The structure follows the
target architecture ("adapt, don't force-fit"): a feature-cohesive `app/`
package, thin root entry points, Alembic migrations, a test suite, and a
docs suite.

## 1. Current tree (canonical)

```
Book-Tale/
├── main.py                       # ENTRY: CLI (thin wrapper → app/routes/main)
├── start.py                      # ENTRY: launcher (→ app/routes/start)
├── web_app.py                    # ENTRY: Flask + SocketIO (→ app/routes/web_app)
├── worker.py                     # ENTRY: RQ worker (→ app/jobs/worker)
├── app/                          # Core package
│   ├── api/  api_spec.py         # OpenAPI spec
│   ├── config/  settings.py      # typed settings
│   ├── core/   exceptions, logger, utils
│   ├── db/     database, models, repositories, service, storage_adapter
│   ├── jobs/   jobs, tasks, worker
│   ├── models/ book, user
│   ├── realtime/  realtime.py
│   ├── routes/  main, web_app, start, feature_routes, page_routes,
│   │            site_pages, social_routes
│   ├── services/
│   │   ├── auth/         auth
│   │   ├── books/        library, reviews, series, lists, cover_service, backup
│   │   ├── email/        email_notifier
│   │   ├── notifications/ notifications
│   │   ├── reading/      diary, reading_progress, reading_challenge, wishlist
│   │   ├── recommendations/  recommender, seed_data, ml/ (Dataset, Model, notebook)
│   │   └── social/       communities, gamification, social
│   ├── storage/  storage.py     # legacy storage adapter
│   ├── static/  css, js, fonts, dist, sw.js, manifest, offline.html
│   ├── templates/  base, landing, books, auth/*, errors/*, macros, …
│   └── __init__.py
├── migrations/                   # Alembic (env, script.py.mako, versions/×3)
├── tests/                        # pytest suite (+ security/)
├── scripts/                      # benchmark, build_frontend.mjs, seed_users,
│                                 # migrate_json_to_db, smoke_*, verify_postgres
├── docker/                       # nginx.conf
├── docs/                         # documentation suite (see §2)
├── Dockerfile  docker-compose.yml
├── Makefile  pyproject.toml  requirements.txt  package.json  alembic.ini
├── README.md  PROJECT_OVERVIEW.md  PROJECT_ANALYSIS.md  SMOKE_TEST.md  LICENSE
├── apex_lib.bat  apex_lib_install.bat  start.bat     # Windows helpers
└── .env.example  .gitignore  .dockerignore  .editorconfig  .gitattributes
    .vscode/  .gemini/  .github/
```

## 2. Docs tree

```
docs/
├── architecture.md               # ← this pass
├── folder_structure.md           # ← this pass
├── migration_summary.md          # ← modernization record (moved to migration/ 2026-08-11)
├── migration/                    # migration records (old_tree_to_new_tree, file_move_ledger)
├── community/  decisions/  design/  product/  project/  reference/  technical/
├── project/
│   └── analysis_report.md        # ← this pass
└── assets/
    └── runbooks/                 # deploy, rollback, restore-from-backup, …
```

## 3. Change log (this pass)

| Old path | New path | Reason | Mechanism |
|---|---|---|---|
| `docs/assets/agents/AGENTS_FIX.md` | *removed* | Leftover v7.0 prompt scaffolding (same file duplicated in 16 sibling repos); archived copy had zero consumers | `git rm` |
| `docs/assets/agents/AGENTS.md` + `.cursorrules` | *removed* | Archived universal master-prompt template (generic, zero project content, zero consumers); the repo's real agent instructions live in `.github/copilot-instructions.md` | `git rm` (2026-08-15 docs audit) |
| `requirements.txt` (dup block) | deduped | `pandas/numpy/Pillow` pinned twice identically; removed redundant block (resolved set unchanged) | edit |

Reference updates: `.dockerignore` (dropped `AGENTS_FIX.md` exclusion).
The CHANGELOG's historical note about the earlier `docs/agents/` move is a
factual record and was left intact.

## 4. Root allowlist compliance

| Root entry | Status |
|---|---|
| `main.py`, `start.py`, `web_app.py`, `worker.py` | ✔ entry points (thin wrappers) |
| `Dockerfile`, `docker-compose.yml`, `docker/` | ✔ container tooling |
| `Makefile`, `pyproject.toml`, `requirements.txt`, `package.json`, `alembic.ini` | ✔ standard metadata |
| `README.md`, `PROJECT_OVERVIEW.md`, `PROJECT_ANALYSIS.md`, `SMOKE_TEST.md`, `LICENSE` | ✔ metadata / docs |
| `app/`, `migrations/`, `tests/`, `docs/`, `scripts/`, `docker/`, `.github/` | ✔ top-level folders |
| `apex_lib.bat`, `apex_lib_install.bat`, `start.bat` | ✔ platform helpers (flagged §6.3) |
| `.env.example`, `.gitignore`, `.dockerignore`, `.editorconfig`, `.gitattributes`, `.vscode/`, `.gemini/` | ✔ config / metadata |

Result: **no stray files remain at root**.

## 5. Why not more restructuring?

The repository is already cleanly feature-structured; the four root entry
wrappers are deliberate (thin forwarding for CLI/launcher/web/worker
surfaces). The ML directory is intentionally nested under
`services/recommendations/ml/` as a feature-owned bundle. Two deferred
improvements are flagged (not performed): relocating committed ML benchmark
outputs, and consolidating the archived agent configs — both are
owner-decisions documented in the analysis report §6.
