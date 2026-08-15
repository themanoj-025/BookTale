"""
scripts/migrate_json_to_db.py - One-shot JSON -> SQLite/Postgres migration.

Reads every JSON entity currently owned by storage.py / the social modules and
loads it into the relational schema (db.models). Missing JSON files are treated
as empty. Prints a per-entity row-count verification table and exits non-zero
if any loaded count disagrees with the source count.

Usage:
    python scripts/migrate_json_to_db.py            # migrate data/ -> DB
    python scripts/migrate_json_to_db.py --dry-run  # report only, write nothing

Robustness: each row is inserted under its own SAVEPOINT. A row that violates a
foreign key or has a type-mismatched value is skipped, printed, and counted in
a `skipped` column — one dirty row never aborts the whole migration (the real
11k-book/5k-user seed data contains orphaned references by construction).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, select

from app.config.settings import Config
from app.db.database import create_all, get_session_factory
from app.db.models import (
    Book,
    Bookshelf,
    Comment,
    Community,
    DiaryEntry,
    Fine,
    Follow,
    GamificationState,
    Notification,
    Post,
    ReadingChallenge,
    Reservation,
    Review,
    Series,
    Transaction,
    User,
    WishlistSuggestion,
)


def _load(path: str):
    """Load a JSON file; return [] if missing. Never raises on corrupt data
    (the file is logged and skipped, mirroring storage's per-file isolation)."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ! SKIP {os.path.basename(path)}: {e}")
        return []


def _json_path(name: str) -> str:
    return os.path.join(Config.DATA_DIR, name)


def _as_dict(data):
    """Coerce a loaded JSON value to a dict (books/users/reservations are
    object-shaped; a missing file yields [] from _load)."""
    return data if isinstance(data, dict) else {}


def _safe_add_all(db, rows: list, name: str) -> dict:
    """Insert rows under per-row SAVEPOINTs; isolate & count bad rows.

    Returns {"source": total, "loaded": ok, "skipped": bad}. A single FK or
    type violation must not abort the migration of the remaining rows.
    """
    loaded = 0
    skipped = 0
    for row in rows:
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
            loaded += 1
        except Exception as e:
            skipped += 1
            print(f"  ! SKIP {name} row: {e}")
    return {"source": len(rows), "loaded": loaded, "skipped": skipped}


def migrate() -> dict[str, dict]:
    """Run the migration. Returns {entity: {source, loaded, skipped}} counts."""
    report: dict[str, dict] = {}

    # ── Core library ───────────────────────────────────────────────
    books_raw = _as_dict(_load(_json_path("books.json")))
    users_raw = _as_dict(_load(_json_path("users.json")))
    txns_raw = _as_dict(_load(_json_path("transactions.json"))).get("transactions", [])
    fines_raw = _as_dict(_load(_json_path("fines.json"))).get("fines", [])
    notifs_raw = _as_dict(_load(_json_path("notifications.json"))).get("notifications", [])
    res_raw = _as_dict(_load(_json_path("reservations.json")))  # {book_id: [user_ids]}

    # ── Social ─────────────────────────────────────────────────────
    posts_raw = _load(_json_path("posts.json"))
    comments_raw = _load(_json_path("comments.json"))
    follows_raw = _load(_json_path("follows.json"))
    reviews_raw = _load(_json_path("reviews.json"))
    shelves_raw = _load(_json_path("bookshelves.json"))
    diary_raw = _load(_json_path("diary_entries.json"))
    wishlist_raw = _load(_json_path("wishlist_suggestions.json"))
    series_raw = _load(_json_path("series.json"))
    communities_raw = _load(_json_path("communities.json"))
    challenges_raw = _load(_json_path("reading_challenges.json"))
    gamification_raw = _load(_json_path("gamification.json"))

    session_factory = get_session_factory()
    with session_factory() as db:
        # Books / Users carry their PK as the dict key AND inside the dict.
        books = []
        for book_id, data in books_raw.items():
            books.append(
                Book(
                    book_id=book_id,
                    **{
                        k: v
                        for k, v in data.items()
                        if k in Book.__table__.columns and k != "book_id"
                    },
                )
            )
        report["books"] = _safe_add_all(db, books, "books")

        users = []
        for uid, data in users_raw.items():
            users.append(
                User(
                    user_id=uid,
                    **{
                        k: v
                        for k, v in data.items()
                        if k in User.__table__.columns and k != "user_id"
                    },
                )
            )
        report["users"] = _safe_add_all(db, users, "users")

        txns = [
            Transaction(**{k: v for k, v in t.items() if k in Transaction.__table__.columns})
            for t in txns_raw
        ]
        report["transactions"] = _safe_add_all(db, txns, "transactions")

        fines = [
            Fine(**{k: v for k, v in f.items() if k in Fine.__table__.columns}) for f in fines_raw
        ]
        report["fines"] = _safe_add_all(db, fines, "fines")

        notifs = [
            Notification(**{k: v for k, v in n.items() if k in Notification.__table__.columns})
            for n in notifs_raw
        ]
        report["notifications"] = _safe_add_all(db, notifs, "notifications")

        # Reservations: {book_id: [user_id, ...]} -> normalized rows
        res_rows = []
        for book_id, user_ids in res_raw.items():
            for position, uid in enumerate(user_ids, start=1):
                res_rows.append(Reservation(book_id=book_id, user_id=uid, position=position))
        report["reservations"] = _safe_add_all(db, res_rows, "reservations")

        posts = [
            Post(**{k: v for k, v in p.items() if k in Post.__table__.columns}) for p in posts_raw
        ]
        report["posts"] = _safe_add_all(db, posts, "posts")

        comments = [
            Comment(**{k: v for k, v in c.items() if k in Comment.__table__.columns})
            for c in comments_raw
        ]
        report["comments"] = _safe_add_all(db, comments, "comments")

        follows = [
            Follow(**{k: v for k, v in f.items() if k in Follow.__table__.columns})
            for f in follows_raw
        ]
        report["follows"] = _safe_add_all(db, follows, "follows")

        reviews = [
            Review(**{k: v for k, v in r.items() if k in Review.__table__.columns})
            for r in reviews_raw
        ]
        report["reviews"] = _safe_add_all(db, reviews, "reviews")

        shelves = [
            Bookshelf(**{k: v for k, v in s.items() if k in Bookshelf.__table__.columns})
            for s in shelves_raw
        ]
        report["bookshelves"] = _safe_add_all(db, shelves, "bookshelves")

        diary = [
            DiaryEntry(**{k: v for k, v in d.items() if k in DiaryEntry.__table__.columns})
            for d in diary_raw
        ]
        report["diary_entries"] = _safe_add_all(db, diary, "diary_entries")

        wish = [
            WishlistSuggestion(
                **{k: v for k, v in w.items() if k in WishlistSuggestion.__table__.columns}
            )
            for w in wishlist_raw
        ]
        report["wishlist_suggestions"] = _safe_add_all(db, wish, "wishlist_suggestions")

        series = [
            Series(**{k: v for k, v in s.items() if k in Series.__table__.columns})
            for s in series_raw
        ]
        report["series"] = _safe_add_all(db, series, "series")

        communities = [
            Community(**{k: v for k, v in c.items() if k in Community.__table__.columns})
            for c in communities_raw
        ]
        report["communities"] = _safe_add_all(db, communities, "communities")

        challenges = [
            ReadingChallenge(
                **{k: v for k, v in c.items() if k in ReadingChallenge.__table__.columns}
            )
            for c in challenges_raw
        ]
        report["reading_challenges"] = _safe_add_all(db, challenges, "reading_challenges")

        gamification = [
            GamificationState(
                **{k: v for k, v in g.items() if k in GamificationState.__table__.columns}
            )
            for g in gamification_raw
        ]
        report["gamification"] = _safe_add_all(db, gamification, "gamification")

        # ── CRITICAL: `with session_factory() as db:` does NOT auto-commit on
        #    clean exit — the session rolls back. Without this commit every
        #    migrated row silently vanished (report said "loaded" while the DB
        #    stayed empty). This was a real data-loss bug exposed by
        #    tests/test_db_wiring.py::test_migrated_post_preserves_social_columns.
        db.commit()

    return report


def verify() -> dict[str, dict]:
    """Count rows in the DB per entity (used by --dry-run / post-check)."""
    counts: dict[str, dict] = {}
    session_factory = get_session_factory()
    with session_factory() as db:
        for name, model in [
            ("books", Book),
            ("users", User),
            ("transactions", Transaction),
            ("fines", Fine),
            ("notifications", Notification),
            ("reservations", Reservation),
            ("posts", Post),
            ("comments", Comment),
            ("follows", Follow),
            ("reviews", Review),
            ("bookshelves", Bookshelf),
            ("diary_entries", DiaryEntry),
            ("wishlist_suggestions", WishlistSuggestion),
            ("series", Series),
            ("communities", Community),
            ("reading_challenges", ReadingChallenge),
            ("gamification", GamificationState),
        ]:
            counts[name] = {"loaded": int(db.scalar(select(func.count()).select_from(model)) or 0)}
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate JSON data files into the DB")
    parser.add_argument("--dry-run", action="store_true", help="report counts only; do not write")
    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN: current DB counts ===")
        for name, c in verify().items():
            print(f"  {name:<24} {c['loaded']}")
        return 0

    print("=== Migrating JSON -> DB ===")
    create_all()
    report = migrate()

    print(f"\n{'Entity':<24} {'Source':>8} {'Loaded':>8} {'Skipped':>8}   OK")
    ok = True
    for name, c in sorted(report.items()):
        match = c["source"] == c["loaded"]
        ok = ok and match
        status = "✓" if match else "✗ MISMATCH"
        print(f"  {name:<24} {c['source']:>8} {c['loaded']:>8} " f"{c['skipped']:>8}   {status}")

    if not ok:
        print("\nMIGRATION FAILED: row counts disagree (see MISMATCH rows).")
        return 1
    print("\nMigration complete: every entity verified 1:1.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
