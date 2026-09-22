# Book-Tale Restructuring — Phase 1 Discovery Report

Date: 2026-09-21 · Branch: `restructure/app-modularization` · Baseline: 451 tests passed, 0 failed (127 deselected `-m slow`), `app/db` coverage 71.38% ≥ 70 gate. Analyzer: AST-based scan (`_discovery.py`, removed post-run; data below is from its JSON output).

## 1. Inventory (verified, not assumed)

| Metric            | Value                                                                                                         |
| ----------------- | ------------------------------------------------------------------------------------------------------------- |
| Python files      | 172 (app 107 · tests 47 · scripts 8 · migrations 5)                                                           |
| App source lines  | ~24,946                                                                                                       |
| Flask routes      | 148 across 21 route modules                                                                                   |
| Circular imports  | **0** (Tarjan SCC over full internal import graph)                                                            |
| Missing templates | 0 (every `render_template` target exists)                                                                     |
| Entry points      | 5 root shims (`main/start/web_app/worker.py` + `app/routes/{main,start}.py`), `app/jobs/worker.py`, 5 scripts |

## 2. Key findings

### F1 — Root shims are intentional, documented, load-bearing (KEEP)

`web_app.py`, `main.py`, `start.py`, `worker.py` at root are thin re-export entry points ("Thin entry point that re-exports... from the app package"). 12 test files import `from web_app import ...`; Dockerfile CMD runs `gunicorn ... web_app:app`; docker-compose runs `python worker.py`. **These are canonical entry points, not clutter.** Do not move; keep their app-package implementations as the real homes.

### F2 — Zero circular imports

The full import graph (172 files, resolved via AST) has no SCC > 1. The earlier `feature_shared` None-capture bug was an init-ordering issue, not a cycle. Consequence: **moves are low-risk from a cycle standpoint**; standard dependency-ordered sequencing suffices.

### F3 — `ml_pkg` is fully isolated (severable)

`app/services/recommendations/ml/Model/ml_pkg/` (12+ files, numpy/pandas) has **zero importers** in app, tests, or scripts. It ships its own `requirements.txt`, datasets, images, notebooks. Any failure there cannot affect the web app. High-confidence candidate to relocate to a top-level `ml/` (or remove — flagged, not decided).

### F4 — Two ORM model homes (ambiguity, needs a ruling)

- `app/db/models.py` (425 lines) — SQLAlchemy ORM, used by `app/db/*`, `migrations/env.py` (string-based `importlib.import_module("app.db.models")`), tests. **Canonical.**
- `app/models/{book,user}.py` — legacy dataclass-style domain models imported by 10 app files + 8 test files + 1 script.
  Both are named "models" — the protocol's naming standard resolves this: SQLAlchemy → stays `app/db/models.py`; legacy domain structs → `app/domain/` or merged into db models (merge is a behavior-risk; **recommend rename+relocate only**).

### F5 — CLI files live in `app/routes/` (misplaced layer)

`book_management_cli.py`, `user_management_cli.py`, `recommendations_cli.py`, `backup_cli.py`, `notifications_cli.py`, `operations_cli.py`, `reports_cli.py` are CLI command surfaces inside the web routes package (imported by `app/routes/main.py` — the TUI menu). Per Phase 5 taxonomy → `app/cli/`.

### F6 — Duplication/shim debt (rename+flag class)

- `gamification.py` (page route) vs `gamification_routes.py` (re-export shim) vs `gamification_pkg/` (real modules) — three names for one feature.
- `web_app.py` (real) vs root `web_app.py` (shim) — fine; but `feature_routes.py` + `feature_shared.py` + five extracted `*_routes.py` with late-binding imports is a known-tangled area (fixed this session).
- Banned-name scan: `backup_cli.py`, `services/books/backup.py` (legit domain term "backup", not temp junk — document exemption rather than rename).

### F7 — Root hygiene

Stray root artifacts: `radar_balance.txt` (log junk — delete), `apex_lib*.bat` + `start.bat` (Windows launchers — move to `scripts/windows/` or keep as canonical launchers; judgment call), `load-test.js` (k6 script → `scripts/loadtest/`), `.coverage` (gitignored artifact), `PROJECT_ANALYSIS.md`/`SMOKE_TEST.md` (docs → `docs/`), `PROJECT_OVERVIEW.md` (786 lines → merge into `docs/architecture.md`).

### F8 — God modules (flag, split only where behavior-safe)

31 files > 350 lines, top: `web_app.py` 638, `services/recommendations/seed_data.py` 603, `services/books/reviews.py` 592, `recommender.py` 591, `books/library.py` 589, `gamification_pkg/profile_page.py` 574, `social/social.py` 562, `social_api.py` 548. HTML-string page builders dominate. Splitting is **out of scope for this pass** where behavior risk is high; the route extraction pattern (already in flight) is the sanctioned mechanism.

## 3. Risk register (Phase 8 seed)

| Risk                                                                       | Level        | Mitigation                                                                            |
| -------------------------------------------------------------------------- | ------------ | ------------------------------------------------------------------------------------- |
| String-based dynamic imports (`app.db.models` ×3)                          | High         | Keep `app/db/models.py` path stable or update all three call sites in the same commit |
| Root shim re-export surface (`from web_app import *`-style usage in tests) | High         | Shims stay; their targets move with re-export preservation                            |
| `feature_shared`/init-ordering closure capture                             | High (known) | Already fixed; new modules must follow the register-function late-binding pattern     |
| 12 test files importing root shims                                         | Medium       | Moves must keep shim re-exports byte-compatible; URL-map diff in Phase 7              |
| Alembic migration path references                                          | Medium       | `alembic.ini` + `migrations/env.py` reference `app.db.*` — verify after moves         |
| Dockerfile COPY paths (`app/static/...`)                                   | Medium       | Static moves must update Dockerfile layers                                            |
| 451-test baseline drift                                                    | Medium       | Re-run full suite after every phase commit                                            |

## 4. Judgment calls presented (protocol §2.3 — decision needed before Phase 4 moves)

1. **`app/models/` legacy structs**: relocate to `app/domain/` (rename-only, mechanical) vs merge into `app/db/models.py` (invasive). _Recommendation: relocate._
2. **`ml_pkg`**: relocate to top-level `ml/` vs leave in place (zero coupling = zero urgency). _Recommendation: relocate later; not part of this pass's critical path._
3. **Windows launchers**: canonical root files vs `scripts/windows/`. _Recommendation: keep at root (user-facing entry points), document in folder_structure.md._
4. **CLI module moves** (`app/routes/*_cli.py` → `app/cli/`): changes 2-3 import sites (`app/routes/main.py` menu) — mechanical, medium blast radius. _Recommendation: do it in Phase 4 step 6._

## 5. Phase 2/3 target structure (delta design — adapt, don't force-fit)

The existing tree already matches the enterprise skeleton to a large degree (`app/{api,config,core,db,jobs,routes,services,storage,realtime,templates,static}`). The restructuring is therefore a **targeted delta**, not a rebuild:

```
app/
├── cli/                    # NEW: F5 moves (7 *_cli.py + TUI menu support)
├── domain/                 # NEW: F4 legacy domain structs (renamed from app/models/)
├── db/                     # stays (SQLAlchemy models canonical here)
├── routes/                 # stays; gamification triple-name collapses to
│   └── gamification_pkg/   #      gamification_routes.py → thin re-export (F6)
├── services/               # stays (books/reading/social/... already domain-shaped)
└── ml/                     # DEFERRED (F3): ml_pkg relocation, separate pass
scripts/windows/            # F7: *.bat launchers (if accepted)
docs/                       # F7: PROJECT_*.md, SMOKE_TEST.md absorbed
```

Move ledger template and per-file mapping will be generated in `docs/migration/file_move_ledger.md` during Phase 4 execution; each phase = one commit = one verified green suite run.
