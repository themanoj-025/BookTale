"""
scripts/benchmark.py - Phase 2 DoD latency benchmark.

Measures p50/p95/p99 latency of the DB-backed service layer
(db.service.LibraryService) at 10k books / 5k users / 50k transactions on
SQLite (WAL + BEGIN IMMEDIATE), per the Phase 2 Definition of Done:

    "a benchmark script shows checkout p95 latency at 10k books / 5k users
     / 50k transactions is under, say, 50ms (document the actual number)"

Run with:
    python scripts/benchmark.py                  # default 10000 5000 50000
    python scripts/benchmark.py 2000 1000 10000  # custom books/users/txns

Results are printed and (with --write-doc) appended to docs/perf-report.md.

The script intentionally imports only config + db.* modules (not web_app) so
the isolated database is built from scratch without the app bootstrap or the
Goodreads seed, and nothing outside the benchmark is touched.
"""

import argparse
import os
import random
import statistics
import sys
import tempfile
import time
from datetime import datetime, timedelta

# ── Isolate the bench DB BEFORE importing anything that reads Config ──────
_BENCH_DIR = tempfile.mkdtemp(prefix="booktale_bench_")
os.environ["STORAGE_BACKEND"] = "db"

# `python scripts/benchmark.py` puts scripts/ on sys.path, not the project
# root — add the root explicitly so `config`, `db.*` resolve (same pattern
# as scripts/smoke_checklist.py).
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from app.config.settings import Config

Config.DATA_DIR = os.path.join(_BENCH_DIR, "data")
Config.LOGS_DIR = os.path.join(_BENCH_DIR, "logs")
Config.BACKUPS_DIR = os.path.join(_BENCH_DIR, "backups")
for _d in (Config.DATA_DIR, Config.LOGS_DIR, Config.BACKUPS_DIR):
    os.makedirs(_d, exist_ok=True)

from sqlalchemy import insert

from app.db.database import create_all, get_engine
from app.db.models import Book, Transaction, User
from app.db.service import LibraryService

# ══════════════════════════════════════════════════════════════════════
# SEED DATA GENERATORS
# ══════════════════════════════════════════════════════════════════════

_CATEGORIES = [
    "Fiction",
    "Science",
    "Fantasy",
    "Mystery",
    "Romance",
    "History",
    "Biography",
    "Poetry",
    "Horror",
    "Thriller",
    "Adventure",
    "Young Adult",
    "Children",
    "Reference",
    "Science Fiction",
    "Classics",
    "Self-Help",
    "Travel",
    "Non-Fiction",
]

_ADJ = [
    "Dark",
    "Silent",
    "Broken",
    "Golden",
    "Hidden",
    "Ancient",
    "Restless",
    "Quiet",
    "Burning",
    "Distant",
    "Forgotten",
    "Wild",
]
_NOUN = [
    "Kingdom",
    "River",
    "Winter",
    "Garden",
    "Empire",
    "Horizon",
    "Library",
    "Shadow",
    "Morning",
    "Island",
    "City",
    "Forest",
]
_SURNAMES = [
    "Sharma",
    "Patel",
    "Khan",
    "Silva",
    "Costa",
    "Mendes",
    "Novak",
    "Petrov",
    "Hansen",
    "Müller",
    "Rossi",
    "Tanaka",
    "Nguyen",
    "Okafor",
    "Cohen",
    "Bauer",
    "Sato",
    "Kim",
]

_T0 = datetime.now() - timedelta(days=400)


def _book_row(i: int) -> dict:
    total = random.randint(1, 8)
    return {
        "book_id": f"BK-{i:05d}",
        "title": f"{random.choice(_ADJ)} {random.choice(_NOUN)} of the {random.choice(_NOUN)}",
        "author": f"{random.choice(_SURNAMES)}, {random.choice(['A.', 'B.', 'C.', 'D.', 'E.'])}",
        "isbn": f"978{i:09d}",
        "category": random.choice(_CATEGORIES),
        "total_copies": total,
        "available_copies": random.randint(1, total),
        "is_deleted": False,
        "issue_count": random.randint(0, 500),
        "added_on": (_T0 + timedelta(days=random.randint(0, 390))).isoformat(),
        "publisher": "Bench Press",
        "pages": random.randint(120, 900),
        "language": "English",
        "release_date": f"{random.randint(1950, 2024)}-01-01",
        "cover_image": "",
        "description": "Benchmark seed book.",
        "series_name": "",
        "series_order": 0,
        "cover_url": "",
        "cover_fetched": False,
        "cover_source": "",
        "dominant_color": "",
        "genres": [],
    }


def _user_row(i: int) -> dict:
    return {
        "user_id": f"U{i:05d}",
        "name": f"Reader {i}",
        "email": f"reader{i}@bench.io",
        "phone": "",
        "role": "user",
        "password_hash": "benchmark-placeholder",
        "membership_status": "Active",
        "membership_expiry": (datetime.now() + timedelta(days=365)).isoformat(),
        "books_issued": [],
        "unpaid_fine": 0.0,
        "registered_on": (_T0 + timedelta(days=random.randint(0, 390))).isoformat(),
        "bio": "",
        "profile_picture": "",
        "website": "",
        "location": "",
        "email_verified": False,
        "favorite_genres": [],
        "favorite_books": [],
        "failed_login_attempts": 0,
        "lock_until": None,
        "theme": "light",
        "font_size": "medium",
        "email_notifications": True,
        "push_notifications": True,
        "notify_on_comment": True,
        "notify_on_like": True,
        "notify_on_follow": True,
        "notify_on_issue_return": True,
        "notify_on_overdue": True,
        "notify_on_due_reminder": True,
        "privacy_show_activity": True,
        "privacy_show_wishlist": True,
        "privacy_show_bookmarks": True,
        "privacy_profile_visibility": "public",
        "privacy_show_email": False,
        "reading_default_rating": "worth_it",
        "reading_goal_type": "books",
        "reading_default_goal": 12,
    }


def _txn_rows(n: int, users: list, books: list) -> list:
    """50k mixed transactions: ~90% closed returns, ~10% open issues, and a
    share of the open ones overdue (past due_date) so the overdue scan has
    realistic work. user/books are the ID lists to sample from."""
    rows = []
    now = datetime.now()
    for i in range(n):
        uid = random.choice(users)
        bid = random.choice(books)
        issued = _T0 + timedelta(days=random.randint(0, 390))
        due = issued + timedelta(days=Config.ISSUE_DAYS)
        closed = i % 10 != 0  # 90% returned
        if closed:
            returned = issued + timedelta(days=random.randint(1, 25))
            fine = 0.0
            if returned > due:
                fine = (returned - due).days * Config.FINE_PER_DAY
            return_date = returned.isoformat()
        else:
            return_date = None
            fine = 0.0
        rows.append(
            {
                "txn_id": f"TXN-{i:06d}",
                "type": "issue",
                "user_id": uid,
                "book_id": bid,
                "issue_date": issued.isoformat(),
                "due_date": due.isoformat(),
                "return_date": return_date,
                "fine": fine,
            }
        )
    # Force ~2,000 open issues to be overdue (past due_date) so the overdue
    # scan returns a realistic list instead of an empty one.
    open_rows = [r for r in rows if r["return_date"] is None]
    for r in random.sample(open_rows, min(2000, len(open_rows))):
        past = now - timedelta(days=random.randint(1, 30))
        r["due_date"] = (past - timedelta(days=random.randint(1, 15))).isoformat()
    return rows


def _bulk_insert(table, rows: list) -> None:
    """Executemany insert in chunks; column defaults provided explicitly."""
    engine = get_engine()
    CHUNK = 1000
    with engine.begin() as conn:
        for i in range(0, len(rows), CHUNK):
            conn.execute(insert(table), rows[i : i + CHUNK])


def _seed(books_n: int, users_n: int, txns_n: int) -> tuple:
    random.seed(42)
    t0 = time.perf_counter()
    create_all()

    book_rows = [_book_row(i) for i in range(books_n)]
    user_rows = [_user_row(i) for i in range(users_n)]
    user_ids = [r["user_id"] for r in user_rows]
    book_ids = [r["book_id"] for r in book_rows]
    txn_rows = _txn_rows(txns_n, user_ids, book_ids)

    _bulk_insert(Book, book_rows)
    _bulk_insert(User, user_rows)
    _bulk_insert(Transaction, txn_rows)

    dt = time.perf_counter() - t0
    print(f"  seeded {books_n} books / {users_n} users / {txns_n} txns in {dt:.1f}s")
    return user_ids, book_ids


# ══════════════════════════════════════════════════════════════════════
# BENCHMARK LOOP
# ══════════════════════════════════════════════════════════════════════


def _measure(fn, n: int, warmup: int = 20) -> list:
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t) * 1000.0)  # ms
    return samples


def _percentiles(samples: list) -> dict:
    s = sorted(samples)

    def pct(p):
        idx = min(len(s) - 1, round((p / 100.0) * (len(s) - 1)))
        return s[idx]

    return {
        "mean": statistics.fmean(s),
        "p50": pct(50),
        "p95": pct(95),
        "p99": pct(99),
        "n": len(s),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 2 DoD latency benchmark")
    parser.add_argument("books", nargs="?", type=int, default=10000)
    parser.add_argument("users", nargs="?", type=int, default=5000)
    parser.add_argument("txns", nargs="?", type=int, default=50000)
    parser.add_argument(
        "--write-doc", action="store_true", help="append results to docs/perf-report.md"
    )
    args = parser.parse_args()

    print("== Book-Tale Phase 2 DoD benchmark ==")
    print(f"  DB: {Config.DATA_DIR}/booktale.db (SQLite WAL + BEGIN IMMEDIATE)")

    user_ids, book_ids = _seed(args.books, args.users, args.txns)
    svc = LibraryService()

    print("\n  warming up each operation (20 iterations, discarded)...\n")

    # ── Checkout: one fresh (user, book) pair per iteration ───────────
    # Warmup (20) + samples must fit in the user/book pool for any custom
    # run size the CLI accepts (e.g. `benchmark.py 50 30 10`), so subtract
    # the warmup from the cap.
    n_checkout = max(0, min(200, len(user_ids) - 20, len(book_ids) - 20))
    if n_checkout == 0:
        print(
            "  pool too small for the checkout benchmark " "(need at least 21 users and 21 books)"
        )
        return 1
    checkout_i = 0

    def checkout():
        nonlocal checkout_i
        # Distinct (user, book) pairs only: warmup (20) + samples (200) must
        # stay under the pool size (5k users / 10k books), so no modulo wrap
        # can ever re-issue an already-issued pair (which would 500 the op
        # with "User already has this book issued").
        assert checkout_i < min(
            len(user_ids), len(book_ids)
        ), "checkout pool exhausted: warmup + samples exceed users/books"
        i = checkout_i
        checkout_i += 1
        ok, _ = svc.issue_book(user_ids[i], book_ids[i], actor="Librarian")
        if not ok:
            raise RuntimeError(f"checkout failed for {user_ids[i]}/{book_ids[i]}")

    # ── Search: broad substring LIKE across title/author/isbn/category ─
    def search():
        svc.search_books(query="the", page=1, per_page=20)

    # ── Overdue list: indexed open-issue scan + tolerant date filter ───
    def overdue():
        svc.get_overdue_list()

    # ── Stats: one-shot aggregate (reports dashboard) ──────────────────
    def stats():
        svc.library_stats()

    results = {}
    for name, fn, n in (
        ("checkout (issue_book)", checkout, n_checkout),
        ("search_books 'the'", search, 500),
        ("get_overdue_list", overdue, 100),
        ("library_stats", stats, 100),
    ):
        samples = _measure(fn, n)
        results[name] = _percentiles(samples)

    print(f"{'operation':<26} {'n':>5} {'mean':>9} {'p50':>9} {'p95':>9} {'p99':>9}")
    print("-" * 67)
    for name, r in results.items():
        print(
            f"{name:<26} {r['n']:>5} {r['mean']:>8.2f}ms {r['p50']:>8.2f}ms "
            f"{r['p95']:>8.2f}ms {r['p99']:>8.2f}ms"
        )

    # DoD gate: checkout p95 < 50ms
    checkout_p95 = results["checkout (issue_book)"]["p95"]
    gate = checkout_p95 < 50.0
    # ASCII markers only: the Windows cp1252 console cannot encode the
    # check/cross emoji and would raise UnicodeEncodeError on the gate line.
    print(
        f"\n  Phase 2 DoD gate: checkout p95 < 50ms -> "
        f"{checkout_p95:.2f}ms {'PASS' if gate else 'FAIL'}"
    )

    if args.write_doc:
        _append_doc(args, results)
    return 0 if gate else 1


def _append_doc(args, results: dict) -> None:
    lines = [
        "",
        "## Benchmark run",
        "",
        f"- Dataset: {args.books} books / {args.users} users / {args.txns} txns",
        "- Database: SQLite (WAL + BEGIN IMMEDIATE), file under temp dir",
        "- LibraryService methods measured after 20-iteration warmup",
        f"- Run at: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "| operation | n | mean (ms) | p50 (ms) | p95 (ms) | p99 (ms) |",
        "|---|---|---|---|---|---|",
    ]
    for name, r in results.items():
        lines.append(
            f"| {name} | {r['n']} | {r['mean']:.2f} | {r['p50']:.2f} "
            f"| {r['p95']:.2f} | {r['p99']:.2f} |"
        )
    lines.append("")
    doc = os.path.join("docs", "perf-report.md")
    with open(doc, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"\n  appended results to {doc}")


if __name__ == "__main__":
    sys.exit(main())
