# Book-Tale — File Move Ledger

## This pass (2026-08-11)

| Old path | New path | Category | Reason | Risk | Verified |
|---|---|---|---|---|---|
| `docs/migration_summary.md` | `docs/migration/migration_summary.md` | Meta/docs | Consolidate migration records under `docs/migration/` per enterprise standard | Low (docs only) | ✅ `git mv` preserved history; single inbound tree reference updated (`docs/folder_structure.md` §2) |

## Prior pass (v5.0 modernization, commit `0cd6fa0`)

The v5.0 pass moved application code into the `app/` package layout. Its full
ledger is preserved at `docs/migration/migration_summary.md`:

- §2 **Deletion log** — every removed file with justification
- §3 **Move log** — old path → new path for every moved file (git mv)
- §4 **Import/reference update summary**
- §5 **Verification report** (Phase 8)
- §7 **Definition of Done checklist**

Representative moves from that pass (see §3 for the full list):

| Old path (flat root) | New path | Reason |
|---|---|---|
| `models.py` / `schemas.py` | `app/db/models.py` | DB models into the db layer |
| `services/*` | `app/services/<domain>/` | Feature-owned service verticals (auth, books, reading, social, recommendations, email, notifications) |
| `routes.py` / `api.py` | `app/routes/` | Routing layer |
| `worker.py` logic | `app/jobs/worker.py` | RQ worker + cron scheduler |
| (static/templates) | `app/static/`, `app/templates/` | Presentation assets |

## Non-moves (documented decisions)

| Path | Decision | Reason |
|---|---|---|
| `main.py`, `web_app.py`, `worker.py`, `start.py` (root) | keep | Thin entry launchers — the Docker/CI/`apex_lib.bat` contract (`python web_app.py`); they only bootstrap `sys.path` and delegate to `app.*` |
| `app/services/recommendations/ml/` | keep | Notebook + dataset + images — self-contained ML experiment referenced by recommender |
| `node_modules/`, `.coverage`, `logs/`, `data/booktale.db`, `.hypothesis/` | leave (untracked) | Runtime/build artifacts, correctly gitignored |
