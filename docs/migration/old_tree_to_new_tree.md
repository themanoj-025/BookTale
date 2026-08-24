# Book-Tale — Old Tree → New Tree

## This pass (2026-08-11)

```
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

```
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
