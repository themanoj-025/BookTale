"""
db/storage_adapter.py - DB-backed implementation of the JSON Storage interface.

Implements the exact same public API as storage.Storage (load_books/save_books,
load_users/save_users, load_transactions/.../append_*, load_posts/..., and
clear_cache) on top of the SQLAlchemy models in db.models. Swapping
`storage = Storage()` for `storage = create_storage()` makes the entire existing
stack — web routes, Library, AuthManager, Recommender, NotificationManager, and
the social modules — run on the relational layer with zero changes to callers.

Semantics preserved from the JSON layer:

- books/users: upsert-only. The app never hard-deletes them (soft delete via
  `is_deleted`), and hard-deleting rows that transactions reference would
  violate FK integrity. The JSON layer kept them in the file forever too.
- transactions: upsert by txn_id (append + in-place update on return).
- reservations/fines/notifications/bookshelves: full-file replace in JSON, so
  the adapter deletes + re-inserts the set.
- posts/comments/follows/reviews: the JSON layer supports item removal, so the
  adapter deletes rows whose PK is absent from the incoming list. When a post is
  removed its comments go first (FK ordering, matching how the JSON world left
  them dangling with no integrity to break).

Integrity strategy: every write is per-row FK-tolerant (SAVEPOINT isolation),
mirroring scripts/migrate_json_to_db.py — a single orphaned row (e.g. a txn for
a user_id absent from users) is logged and skipped, never crashes the request.
The JSON storage never validated referential integrity either, so this keeps
parity while remaining resilient.

The transactional guarantee lives in db/service.py (LibraryService); Library
delegates issue/return/pay_fine to it when constructed with a DbStorage (see
library.py), so oversell-proof checkout is wired into the running app.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy import delete, select

from app.db.database import create_all, session_scope
from app.db.models import Book as BookRow
from app.db.models import Bookshelf as ShelfRow
from app.db.models import Comment as CommentRow
from app.db.models import Fine as FineRow
from app.db.models import Follow as FollowRow
from app.db.models import Notification as NotificationRow
from app.db.models import Post as PostRow
from app.db.models import Reservation as ReservationRow
from app.db.models import Review as ReviewRow
from app.db.models import Transaction as TransactionRow
from app.db.models import User as UserRow

log = logging.getLogger("db.storage_adapter")


# ─────────────────────────────────────────────────────────────────────
# Row <-> plain-dict helpers (column-filtered, JSON-compatible shapes)
# ─────────────────────────────────────────────────────────────────────


def _columns(model) -> set:
    return {c.name for c in model.__table__.columns}


def _plain(row, drop=()) -> dict:
    """ORM row -> plain dict of its columns (minus autoincrement `id` etc.)."""
    return {c.name: getattr(row, c.name) for c in row.__table__.columns if c.name not in drop}


def _row(model, data: dict) -> None:
    """Plain dict -> ORM row, keeping only known model columns."""
    cols = _columns(model)
    return model(**{k: v for k, v in data.items() if k in cols})


def _upsert_tolerant(db, model, data: dict, name: str) -> None:
    """Insert-or-update a row; skip (log) on FK/type violations via SAVEPOINT."""
    try:
        with db.begin_nested():
            db.merge(_row(model, data))
            db.flush()
    except Exception as e:
        log.warning(
            "DbStorage skip %s row (id=%s): %s",
            name,
            data.get("post_id")
            or data.get("comment_id")
            or data.get("follow_id")
            or data.get("review_id")
            or data.get("txn_id")
            or data.get("notif_id")
            or data.get("user_id")
            or data.get("book_id")
            or data.get("suggestion_id"),
            e,
        )


def _insert_tolerant(db, model, data: dict, name: str) -> None:
    """Insert a row; skip (log) on FK/type violations via SAVEPOINT."""
    try:
        with db.begin_nested():
            db.add(_row(model, data))
            db.flush()
    except Exception as e:
        log.warning("DbStorage skip %s insert: %s", name, e)


def _delete_absent(db, model, pk_col, ids: list) -> None:
    """Delete DB rows whose PK is not in `ids` (list-replace semantics)."""
    if not ids:
        db.execute(delete(model))
        return
    db.execute(delete(model).where(pk_col.not_in(ids)))


# ─────────────────────────────────────────────────────────────────────
# DbStorage — drop-in replacement for storage.Storage
# ─────────────────────────────────────────────────────────────────────


class DbStorage:
    """SQLAlchemy-backed Storage implementing the JSON Storage interface."""

    def __init__(self) -> None:
        # Dev convenience: tables exist before the first read (web_app calls
        # bootstrap() at import time, which reads users). Production uses
        # Alembic; create_all() is a no-op when tables already exist.
        create_all()

    # ── Books ──────────────────────────────────────────────────────

    def load_books(self, force: bool = False) -> dict[str, Any]:
        from app.models.book import Book

        with session_scope() as db:
            rows = db.scalars(select(BookRow)).all()
        return {r.book_id: Book.from_dict(_plain(r)) for r in rows}

    def save_books(self, books: dict[str, Any]) -> None:
        with session_scope() as db:
            for b in books.values():
                _upsert_tolerant(db, BookRow, b.to_dict(), "book")

    # ── Users ──────────────────────────────────────────────────────

    def load_users(self, force: bool = False) -> dict[str, Any]:
        from app.models.user import User

        with session_scope() as db:
            rows = db.scalars(select(UserRow)).all()
        return {r.user_id: User.from_dict(_plain(r)) for r in rows}

    def save_users(self, users: dict[str, Any]) -> None:
        with session_scope() as db:
            for u in users.values():
                _upsert_tolerant(db, UserRow, u.to_dict(), "user")

    # ── Transactions ───────────────────────────────────────────────

    def load_transactions(self, force: bool = False) -> list:
        with session_scope() as db:
            rows = db.scalars(select(TransactionRow).order_by(TransactionRow.issue_date)).all()
        return [_plain(r) for r in rows]

    def save_transactions(self, txns: list) -> None:
        with session_scope() as db:
            for t in txns:
                _upsert_tolerant(db, TransactionRow, t, "transaction")

    def append_transaction(self, txn: dict) -> None:
        with session_scope() as db:
            _insert_tolerant(db, TransactionRow, txn, "transaction")

    # ── Reservations ({book_id: [user_ids]}) ───────────────────────

    def load_reservations(self, force: bool = False) -> dict:
        with session_scope() as db:
            rows = db.scalars(select(ReservationRow).order_by(ReservationRow.position)).all()
        res: dict = {}
        for r in rows:
            res.setdefault(r.book_id, []).append(r.user_id)
        return res

    def save_reservations(self, res: dict) -> None:
        with session_scope() as db:
            db.execute(delete(ReservationRow))
            for book_id, user_ids in res.items():
                for pos, uid in enumerate(user_ids, start=1):
                    _insert_tolerant(
                        db,
                        ReservationRow,
                        {"book_id": book_id, "user_id": uid, "position": pos},
                        "reservation",
                    )

    # ── Fines ──────────────────────────────────────────────────────

    def load_fines(self, force: bool = False) -> list:
        with session_scope() as db:
            rows = db.scalars(select(FineRow)).all()
        return [_plain(r, drop={"id"}) for r in rows]

    def save_fines(self, fines: list) -> None:
        with session_scope() as db:
            db.execute(delete(FineRow))
            for f in fines:
                _insert_tolerant(db, FineRow, f, "fine")

    def append_fine(self, fine: dict) -> None:
        with session_scope() as db:
            _insert_tolerant(db, FineRow, fine, "fine")

    # ── Notifications ──────────────────────────────────────────────

    def load_notifications(self, force: bool = False) -> list:
        with session_scope() as db:
            rows = db.scalars(select(NotificationRow).order_by(NotificationRow.created_at)).all()
        return [_plain(r) for r in rows]

    def save_notifications(self, notifs: list) -> None:
        with session_scope() as db:
            db.execute(delete(NotificationRow))
            for n in notifs:
                _insert_tolerant(db, NotificationRow, n, "notification")

    def append_notification(self, notif: dict) -> None:
        with session_scope() as db:
            _insert_tolerant(db, NotificationRow, notif, "notification")

    # ── Social: Posts ──────────────────────────────────────────────

    def load_posts(self, force: bool = False) -> list:
        with session_scope() as db:
            rows = db.scalars(select(PostRow).order_by(PostRow.created_at)).all()
        return [_plain(r) for r in rows]

    def save_posts(self, posts: list) -> None:
        with session_scope() as db:
            ids = [p["post_id"] for p in posts if p.get("post_id")]
            current = set(db.scalars(select(PostRow.post_id)).all())
            removed = current - set(ids)
            if removed:
                # FK order: comments reference posts, delete children first.
                db.execute(delete(CommentRow).where(CommentRow.post_id.in_(removed)))
                db.execute(delete(PostRow).where(PostRow.post_id.in_(removed)))
            for p in posts:
                _upsert_tolerant(db, PostRow, p, "post")

    def append_post(self, post: dict) -> None:
        with session_scope() as db:
            _insert_tolerant(db, PostRow, post, "post")

    # ── Social: Comments ───────────────────────────────────────────

    def load_comments(self, force: bool = False) -> list:
        with session_scope() as db:
            rows = db.scalars(select(CommentRow).order_by(CommentRow.created_at)).all()
        return [_plain(r) for r in rows]

    def save_comments(self, comments: list) -> None:
        with session_scope() as db:
            ids = [c["comment_id"] for c in comments if c.get("comment_id")]
            _delete_absent(db, CommentRow, CommentRow.comment_id, ids)
            for c in comments:
                _upsert_tolerant(db, CommentRow, c, "comment")

    def append_comment(self, comment: dict) -> None:
        with session_scope() as db:
            _insert_tolerant(db, CommentRow, comment, "comment")

    # ── Social: Follows ────────────────────────────────────────────

    def load_follows(self, force: bool = False) -> list:
        with session_scope() as db:
            rows = db.scalars(select(FollowRow).order_by(FollowRow.created_at)).all()
        return [_plain(r) for r in rows]

    def save_follows(self, follows: list) -> None:
        with session_scope() as db:
            ids = [f["follow_id"] for f in follows if f.get("follow_id")]
            _delete_absent(db, FollowRow, FollowRow.follow_id, ids)
            for f in follows:
                _upsert_tolerant(db, FollowRow, f, "follow")

    # ── Social: Reviews ────────────────────────────────────────────

    def load_reviews(self, force: bool = False) -> list:
        with session_scope() as db:
            rows = db.scalars(select(ReviewRow).order_by(ReviewRow.created_at)).all()
        return [_plain(r) for r in rows]

    def save_reviews(self, reviews: list) -> None:
        with session_scope() as db:
            ids = [r["review_id"] for r in reviews if r.get("review_id")]
            _delete_absent(db, ReviewRow, ReviewRow.review_id, ids)
            for r in reviews:
                _upsert_tolerant(db, ReviewRow, r, "review")

    def append_review(self, review: dict) -> None:
        with session_scope() as db:
            _insert_tolerant(db, ReviewRow, review, "review")

    # ── Social: Bookshelves ────────────────────────────────────────

    def load_bookshelves(self, force: bool = False) -> list:
        with session_scope() as db:
            rows = db.scalars(select(ShelfRow).order_by(ShelfRow.created_at)).all()
        return [_plain(r, drop={"id"}) for r in rows]

    def save_bookshelves(self, shelves: list) -> None:
        with session_scope() as db:
            db.execute(delete(ShelfRow))
            for s in shelves:
                _insert_tolerant(db, ShelfRow, s, "bookshelf")

    # ── Utility ────────────────────────────────────────────────────

    def clear_cache(self) -> None:
        """No-op: sessions read the DB directly (JSON layer had a 2s TTL)."""


# ─────────────────────────────────────────────────────────────────────
# Factory — select backend via STORAGE_BACKEND env (default: relational)
# ─────────────────────────────────────────────────────────────────────


def create_storage() -> None:
    """Return the active persistence backend.

    STORAGE_BACKEND=db (default)  -> DbStorage (SQLAlchemy / SQLite|Postgres)
    STORAGE_BACKEND=json          -> legacy JSON Storage (fallback/testing)
    """
    backend = os.getenv("STORAGE_BACKEND", "db").strip().lower()
    if backend == "json":
        from app.storage.storage import Storage  # deferred: legacy import

        return Storage()
    return DbStorage()
