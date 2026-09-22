# Book-Tale — Old Tree → New Tree

## 2026-09-21 restructuring pass (branch `restructure/app-modularization`)

Delta-focused pass on top of the v5.0 layout; full per-file ledger in
`file_move_ledger.md` (§ 2026-09-21). Shape of the change:

```text
Before                                 After
──────                                 ─────
app/routes/*_cli.py (7 files)    →     app/cli/*_cli.py            (new layer)
app/models/                      →     app/domain/                 (legacy structs; app/db/models.py stays canonical)
app/routes/gamification_pkg/     →     app/routes/social_pages/    (routes are social: /feed /search /profile/edit /author)
app/routes/gamification_routes.py→    app/routes/social_pages_routes.py
  └ gamification_core.py         →       └ core.py
PROJECT_{OVERVIEW,ANALYSIS}.md   →     docs/
SMOKE_TEST.md                    →     docs/SMOKE_TEST.md
load-test.js                     →     scripts/loadtest/load-test.js
tests/test_models_{book,user}.py →     tests/test_domain_{book,user}.py
radar_balance.txt                →     (deleted: stray log junk)
```

Unchanged by design (documented in discovery_report.md F1/F3/F4):
root entry-point shims (`web_app.py`, `main.py`, `start.py`, `worker.py`),
`app/db/models.py` (string-based importlib stability), `ml_pkg`
(isolated; relocation deferred).

## This pass (2026-08-11)

```text
Before                                After
──────                                ─────
docs/migration_summary.md      →      docs/migration/migration_summary.md
—                                     docs/migration/old_tree_to_new_tree.md (new)
—                                     docs/migration/file_move_ledger.md     (new)
```

## Prior pass (v5.0 modernization, commit `0cd6fa0`)

Book-Tale was restructured into the current `app/` package layout by the v5.0
modernization pass. Its complete record (deletion log §2, move log §3, import
update summary §4, verification report §5, Needs-Human-Review list §6, DoD
checklist §7) lives at `docs/migration/migration_summary.md`. Tree-level view:

```text
Before (flat)                         After (canonical)
──────                                ─────
*.py flat modules            →        app/ package
                                       ├── api/       OpenAPI spec
                                       ├── config/    settings
                                       ├── core/      exceptions · logger · utils
                                       ├── db/        database · models · repositories · service · storage_adapter
                                       ├── jobs/      jobs · tasks · worker (RQ)
                                       ├── models/    book · user
                                       ├── realtime/  socket.io handlers
                                       ├── routes/    main · web_app · page_routes · site_pages · feature_routes · social_routes
                                       ├── services/  auth · books · email · notifications · reading · recommendations · social
                                       ├── storage/   storage adapter
                                       ├── static/    css · dist · fonts · icons · js · sw
                                       └── templates/ Jinja pages (auth, errors, base, …)
main.py / web_app.py / worker.py / start.py   (thin sys.path bootstrappers → app.*)
scripts/             one-off ops (benchmark, seed_users, smoke, migrate_json_to_db, …)
tests/               unit + security/
migrations/          Alembic-style versions (0001 initial, 0002 audit, 0003 auth)
docs/                full suite (architecture, reference/*, decisions/, runbooks/…)
```

## No-code-move rationale (this pass)

The layout already conforms: `app/` feature-cohesive package, `tests/`,
`migrations/`, `scripts/`, `docs/`, thin root entry launchers, canonical root
metadata only. This pass only consolidates the migration record under
`docs/migration/` — zero code changed.
