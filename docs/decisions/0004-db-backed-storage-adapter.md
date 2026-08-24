# ADR-0004: DB-Backed Storage Adapter (DbStorage) over the JSON Storage Interface

- **Status:** Accepted (2026-08-01)
- **Deciders:** Project owner, acting senior staff engineer
- **Related ADRs:** ADR-0003 (template migration — this decision is data-layer, not
  presentation), ADR-0002 (registration role whitelist — unchanged by backend swap)

---

## Context

Book-Tale persisted every entity as a full-file JSON document (`books.json`,
`users.json`, `transactions.json`, …) through a single `Storage` class in
`storage.py`. Phase 2's goal is a real relational layer (SQLAlchemy over SQLite in
dev, PostgreSQL in prod), but the application is a 125-route monolith whose modules
(`library.py`, `auth.py`, `social.py`, `recommender.py`, `notifications.py`, all
route modules, the CLI, and seeders) all talk to persistence exclusively through
`Storage`'s ~25-method interface.

Rewriting every call site to a new repository API in one phase would be a
high-risk, low-reviewability change touching every file in the repo.

## Decision

Introduce `db/storage_adapter.py` with:

1. **`DbStorage`** — a class implementing the *exact* `Storage` public interface
   (load/save/append for every entity) on top of the SQLAlchemy models in
   `db/models.py`. Callers are unchanged: `library.py`'s `issue_book` still calls
   `self.storage.load_users()`, only the object behind it changed.
2. **`create_storage()`** — a factory reading `STORAGE_BACKEND` (default `db`):
   - `STORAGE_BACKEND=db` (default) → `DbStorage`
   - `STORAGE_BACKEND=json` → legacy `Storage` (fallback / parity testing)
3. **Wiring swaps** — the four `Storage()` instantiations (`web_app.py`,
   `main.py`, `email_notifier.py`, `seed_users.py`) now call `create_storage()`.
4. **Transactional core delegation** — `Library.__init__` detects a `DbStorage`
   and delegates `issue_book`/`return_book`/`pay_fine` to `db.service.LibraryService`,
   which performs each operation as a single DB transaction (SQLite `BEGIN
   IMMEDIATE` via engine event) so concurrent checkouts cannot oversell the last
   copy. Reservations (`reserve_book`, enqueue/pop queue) are inside the service too.

### Semantics deliberately preserved from the JSON layer

- **Books/users: upsert-only.** The app never hard-deletes them (`delete_book` is a
  soft delete setting `is_deleted=True`); hard deletes would violate FK integrity
  with transactions. The JSON layer kept soft-deleted rows in the file forever, so
  upsert-only matches.
- **Posts/comments/follows/reviews: delete-absent.** The JSON layer supported item
  removal, so the adapter deletes rows whose PK is absent from the incoming list
  (posts cascade-delete their comments first, FK order).
- **Reservations/fines/notifications/bookshelves: delete-all + re-insert** to mirror
  the JSON full-file replace.
- **Per-row FK tolerance:** every write uses a SAVEPOINT; a single orphaned row
  (e.g., a txn for a user absent from `users`) is logged and skipped rather than
  crashing the request — matching the old JSON layer's lack of referential
  enforcement while adding resilience.

## Consequences

### Positive

- The entire app — all routes, services, CLI, seeders — runs on the relational
  layer with zero changes to callers, verifiable by the 37-journey smoke script
  (`scripts/smoke_checklist.py`) running green against the DB backend.
- Indexed queries replace O(n) full-file scans on hot paths (search, overdue list,
  stats, reports); real pagination can now be pushed into repositories later.
- Oversell-proof checkout is a tested property (20-thread race test, exactly one
  winner) instead of a lost-update race in `issue_book`.
- `STORAGE_BACKEND=json` gives a one-line rollback path and a parity test harness.
- JSON files remain the seed source: `scripts/migrate_json_to_db.py` (one-shot,
  verified against seed data) and ADR records make the relational layer a strict
  superset of the old data.

### Negative / Trade-offs

- The adapter mirrors JSON dict shapes, so the DB layer doesn't yet expose the
  relational model's full power (joins, FKs used for integrity rather than just
  indexing). That's intentional: repositories/services refactor is a later phase.
- `save_notifications`/fines/bookshelves delete-all + re-insert is still racy under
  concurrent writers (a known JSON-semantics echo); the transactional core
  (issue/return/pay_fine + reservations) is the oversell-safe path and is the only
  one the race test covers.
- SQLite file backend (dev) serializes writes via `BEGIN IMMEDIATE`; multi-process
  scaling requires the planned PostgreSQL move.

## Alternatives considered

- **Full repository-layer rewrite in one phase** — rejected: 100+ call-site churn,
  unverifiable in one reviewable increment, and no `STORAGE_BACKEND=json` rollback.
- **Keep JSON, add SQLite mirror** — rejected: doubles write cost and divergence
  surface without removing the O(n) scans.
- **Directly replace `Storage` with SQL and rewrite `library.py` only** — rejected:
  social modules, auth, recommender, and seeders all need persistence; the adapter
  covers the whole surface uniformly.

## Tests

`tests/test_db_wiring.py` (15 tests): interface round-trip parity for every entity
(including schema-drift columns: post upvotes/downvotes/comment_count/is_pinned,
review content/spoiler/helpful_votes/updated_at, bookshelf user_id/book_id/shelf),
post-delete cascades comments, soft-delete persists through the adapter,
`Library` delegates to the service on DB and keeps the legacy path on JSON,
20-thread no-oversell race, factory switching (both backends + unset env), and a
migration-parity test that a JSON post with the drift columns survives
`migrate_json_to_db.py` → `DbStorage` round-trip with every field intact.
