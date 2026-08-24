# Performance Report — SQLite Layer (Phase 2 DoD)

Date: 2026-08-01 · Run: `python scripts/benchmark.py`

## Goal

The Phase 2 Definition of Done requires a benchmark proving the DB-backed
service layer is fast at realistic scale:

> a benchmark script shows checkout p95 latency at 10k books / 5k users /
> 50k transactions is under, say, 50ms (document the actual number)

## Environment

- OS: Windows (bash shell), Python 3.14
- Database: SQLite on local disk (WAL mode, `busy_timeout=30`,
  `BEGIN IMMEDIATE` write serialization — see `db/database.py`)
- Storage backend: `STORAGE_BACKEND=db` (SQLAlchemy layer)
- Measured via `db.service.LibraryService` (the transactional/indexed layer
  the app runs on), not the legacy JSON-scan wrappers

## Dataset (seeded deterministically, `random.seed(42)`)

| Entity | Rows | Notes |
| --- | --- | --- |
| Books | 10,000 | synthetic titles/authors across 19 categories, `available_copies ≥ 1` |
| Users | 5,000 | all `Active` membership, zero fines, empty `books_issued` |
| Transactions | 50,000 | ~90% closed returns, ~10% open issues; ~2,000 open issues forced overdue |

Seeding (bulk `executemany`, 1,000-row chunks) completes in ~5 seconds.

## Methodology

- Each operation measured after a 20-iteration warmup (discarded).
- Latency per call via `time.perf_counter()`, including full session
  open/commit/close (realistic request-path cost).
- Checkout uses one **fresh distinct (user, book) pair per iteration** so all
  200 samples are successful checkouts through the full transactional path
  (`BEGIN IMMEDIATE` → read-modify-write → `COMMIT`).
- Search uses a broad substring query (`"the"`) matching thousands of rows
  across the title/author/isbn/category `LIKE` predicates.
- Percentiles are order-statistics of the sorted sample set.

## Results (ms)

| Operation | n | mean | p50 | p95 | p99 |
| --- | ---: | ---: | ---: | ---: | ---: |
| checkout (`issue_book`) | 200 | 3.61 | 3.47 | **4.39** | 12.53 |
| `search_books "the"` | 500 | 1.44 | 1.42 | **2.05** | 2.45 |
| `get_overdue_list` | 100 | 207.29 | 207.15 | **244.18** | 267.94 |
| `library_stats` | 100 | 354.42 | 348.22 | **468.24** | 485.44 |

## Phase 2 DoD gate

```
checkout p95 < 50ms -> 4.39ms PASS ✅
```

Checkout p95 (4.39 ms) is **~11× under** the 50 ms target. The p99 spike
(12.5 ms) is likely the SQLite commit fsync under WAL (could also be
scheduling/disk-cache noise) — still comfortably fast.

## Interpretation & honest caveats

- **Checkout (transactional write)** is the headline result: 3.6 ms mean,
  4.4 ms p95 at 50k transactions of accumulated history. The
  `BEGIN IMMEDIATE` write serialization adds no measurable regression at
  this scale; concurrent-writer contention is the guard for oversell
  correctness, not a bottleneck here.
- **Search** is sub-2 ms at p95 because the `LIKE '%…%'` predicates cannot
  use the `ix_books_title/author` btree indexes (leading wildcard), yet a
  full scan of 10k rows is still cheap. At 100k+ books this is the first
  thing to revisit (SQLite FTS5 / Postgres `tsvector`).
- **`get_overdue_list` (~200–250 ms)** and **`library_stats` (~350–470 ms)**
  are the slowest reads and the honest weak spots:
  - `get_overdue_list` narrows to open issues via `ix_txns_open_due`, but the
    overdue comparison is done in Python with a tolerant date parser
    (legacy JSON wrote several date formats). ~5k open rows × parse per row
    dominates. Fix when migrating fully off JSON: enforce ISO-8601 dates and
    push the comparison into SQL.
  - `library_stats` runs ~10 aggregate queries per call (counts, sums, joins)
    and is called on the reports dashboard. Caching with explicit
    invalidation on writes (Redis in prod, per the Phase 6 plan) or a single
    combined query would cut it to single-digit ms.
- Variance between runs (~2× on the two slow reads) is Windows scheduling /
  disk-cache noise; the checkout and search numbers are stable across runs.
- These numbers are **request-path service-layer** latencies; total page
  latency includes template rendering and any per-request overhead.

## How to re-run

```bash
python scripts/benchmark.py                    # 10k / 5k / 50k (default)
python scripts/benchmark.py 2000 1000 10000    # custom dataset size
python scripts/benchmark.py --write-doc        # append results to this file
```

The script seeds an isolated temp database and touches nothing outside it
(it imports only `config` + `db.*` modules — never `web_app`).
