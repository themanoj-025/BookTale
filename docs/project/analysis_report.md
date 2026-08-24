# Analysis Report — Repository Inventory & Classification

Date: 2026-08-10 · Scope: entire Book-Tale repository · Method: file-by-file
read + import-graph scan + content-hash duplicate scan + reference scan.

This report is the written inventory required by Phase 1–2 of the repository
modernization pass (v5.0). It lists every top-level entry, its purpose, its
classification, and its intra-package dependencies. Nothing here changes
behavior — it is the evidence base for the restructuring documented in
[`docs/migration/migration_summary.md`](../migration/migration_summary.md).

---

## 1. Stack overview

| Dimension | Value |
|---|---|
| Language / runtime | Python ≥ 3.10 (black target py310) |
| Package manager | `requirements.txt` (pip) + `pyproject.toml` (tool config) |
| Application | Flask web app (library management) + Socket.IO realtime + RQ worker + CLI |
| Database | PostgreSQL via SQLAlchemy 2 + Alembic migrations (`migrations/`) |
| ML feature | Recommendation engine with ML comparison notebook (`app/services/recommendations/ml/`) |
| Lint / test | flake8 · pytest (tests/ with `--cov` + db-layer coverage gate ≥85) |
| CI | GitHub Actions `ci.yml` + codeql, gitleaks, labeler, stale, welcome, maintenance |
| Deploy | Docker (root `Dockerfile` + `docker/nginx.conf`) + compose |

## 2. Top-level inventory (root)

| Path | Purpose | Classification |
|---|---|---|
| `main.py` | Thin CLI entry point → `app.routes.main` | Entry point |
| `start.py` | Thin launcher entry → `app.routes.start` | Entry point |
| `web_app.py` | Thin Flask/SocketIO entry → `app.routes.web_app` (re-exports public names for back-compat) | Entry point |
| `worker.py` | Thin RQ worker entry → `app.jobs.worker` | Entry point |
| `app/` | Core package (api, config, core, db, jobs, models, realtime, routes, services, static, storage, templates) | Application |
| `migrations/` | Alembic env + 3 version files | Data access |
| `tests/` | pytest suite (7 files incl. `security/`) | Tests |
| `docs/` | Docs suite (community/decisions/design/product/project/reference/technical/assets) | Docs |
| `scripts/` | benchmark, build_frontend.mjs, migrate_json_to_db, seed_users, smoke_checklist, smoke_live, verify_postgres | Infrastructure / Tools |
| `docker/` | nginx.conf (Nginx config for container) | Infrastructure |
| `Dockerfile`, `docker-compose.yml` | Container tooling | Infrastructure |
| `Makefile` | Task runner | Infrastructure |
| `pyproject.toml`, `requirements.txt`, `package.json` | Metadata / deps (incl. frontend build) | Configuration |
| `README.md`, `PROJECT_OVERVIEW.md`, `PROJECT_ANALYSIS.md`, `SMOKE_TEST.md`, `LICENSE` | Metadata / docs | Docs |
| `alembic.ini` | Alembic config | Configuration |
| `apex_lib.bat`, `apex_lib_install.bat`, `start.bat` | Windows helper scripts | Tools |
| `.env.example`, `.gitignore`, `.dockerignore`, `.editorconfig`, `.gitattributes`, `.vscode/`, `.gemini/`, `.github/` | Config / metadata / CI | Configuration |
| `docs/assets/agents/AGENTS_FIX.md` | **Leftover AI-prompt scaffolding (v7.0)** — removed this pass | Unclassified → removed |

## 3. App package (domain & application)

| Module | Purpose | Classification |
|---|---|---|
| `routes/` | `main.py` (CLI), `web_app.py` (Flask app), `start.py` (launcher), `feature_routes.py`, `page_routes.py`, `site_pages.py`, `social_routes.py` | API/interface |
| `config/settings.py` | Typed settings (FLASK_HOST/PORT/DEBUG…) | Configuration |
| `core/` | `exceptions`, `logger`, `utils` | Cross-cutting |
| `db/` | `database`, `models`, `repositories`, `service`, `storage_adapter` | Data access |
| `models/` | `book`, `user` (domain models) | Domain |
| `jobs/` | `jobs`, `tasks` (RQ jobs), `worker` | Infrastructure |
| `realtime/` | Socket.IO event wiring | Realtime |
| `services/auth/` | `auth` — authentication/authorization | Cross-cutting |
| `services/books/` | `backup`, `cover_service`, `library`, `lists`, `reviews`, `series` | Domain / Application |
| `services/email/` | `email_notifier` | Cross-cutting |
| `services/notifications/` | `notifications` | Application |
| `services/reading/` | `diary`, `reading_challenge`, `reading_progress`, `wishlist` | Domain / Application |
| `services/recommendations/` | `recommender`, `seed_data` + `ml/` (Dataset CSV, notebook, comparison script + outputs) | Application / ML |
| `services/social/` | `communities`, `gamification`, `social` | Domain / Application |
| `storage/` | `storage.py` (legacy storage adapter) | Data access |
| `static/` | CSS, JS, fonts, PWA (sw.js, manifest) | Presentation |
| `templates/` | Jinja templates (auth, pages, errors, macros) | Presentation |

Dependency graph is **acyclic** at package level: routes → services/db →
models/config; services → db/repositories; jobs → db.

## 4. Documentation suite

| Path | Purpose |
|---|---|
| `docs/community/` | CHANGELOG, CODE_OF_CONDUCT, CONTRIBUTING, SECURITY, SUPPORT |
| `docs/decisions/` | ADRs (incl. template-migration decision) |
| `docs/design/`, `docs/product/`, `docs/project/`, `docs/reference/`, `docs/technical/` | Standard suite |
| `docs/assets/` | Images, runbooks, archived agent configs (`agents/`) |
| `SMOKE_TEST.md` | Manual smoke checklist |

## 5. Findings summary (evidence for Phase 3)

| Scan | Method | Result |
|---|---|---|
| Duplicate files | SHA-256 over tracked text files (excl. binaries/notebooks) | **0 duplicate-content groups** (the 3 zero-byte `__init__.py` are legitimate package markers, not duplicates) |
| Duplicate dependencies | `requirements.txt` audit | **`pandas/numpy/Pillow` pinned twice** (identical block) — redundant duplicate removed; resolved set unchanged |
| Empty files | size == 0 walk | 3 package-marker `__init__.py` (legit) |
| AI scaffolding | `docs/assets/agents/AGENTS_FIX.md` | **removed** — same v7.0 prompt duplicated across 16 sibling repos; archived copy had no code/CI/Docker consumers (only `.dockerignore` exclusion + CHANGELOG note) |
| Hardcoded secrets | regex scan | none found |
| ML outputs | `recommendation_ml_comparison.py` writes `data/generated/comparison_output/` (PNGs, HTML, txt) | **gitignored, regenerated on demand** — no longer committed (resolved 2026-08-15) |
| Tests | `pytest tests/` | **PASS** — ~150 tests, 0 failures (2 skipped), incl. db coverage gate |

## 6. Needs Human Review

1. **ML `comparison_output/` artifacts** — **RESOLVED (2026-08-15):** the
   generated charts/report/radar HTML now write to the gitignored
   `data/generated/comparison_output/` tree (output dir moved in
   `recommendation_ml_comparison.py`; tracked copies removed from git). The
   script + notebook remain tracked.
2. **Archived agent configs** — `docs/assets/agents/AGENTS.md` (498 lines,
   older copy) and `.cursorrules` remain as archived docs; root `AGENTS.md`
   does not exist. Recommend: promote a single canonical `AGENTS.md` to the
   root (like sibling repos) or remove the archive entirely.
3. **`apex_lib.bat` / `apex_lib_install.bat` / `start.bat`** — Windows helper
   scripts at root; verify they are still used before consolidating into
   `scripts/`.
4. **`node_modules/` present on disk** (gitignored) — frontend build
   (`build_frontend.mjs`, `package.json`) pulls JS deps; ensure CI installs
   them consistently.
5. **Docker entry points** — four root entry modules (`main`, `start`,
   `web_app`, `worker`) are thin wrappers over `app/`; the `web_app.py`
   re-export shim exists for backward-compatible imports (tests/CLI). If that
   compatibility is no longer needed, the shim can be retired.
