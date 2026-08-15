"""
storage.py - JSON-based persistent storage with caching and file locking
"""

import json
import os
import threading
import time
from typing import Any

from app.config.settings import Config
from app.core.exceptions import StorageError
from app.models.book import Book
from app.models.user import User

# ─

_locks: dict[str, threading.Lock] = {}
_cache: dict[str, Any] = {}
_cache_timestamps: dict[str, float] = {}
CACHE_TTL: float = 2.0  # seconds before cache is considered stale


def _get_lock(path: str) -> threading.Lock:
    """Get or create a lock for a given file path."""
    if path not in _locks:
        _locks[path] = threading.Lock()
    return _locks[path]


def _read_json(path: str, force: bool = False) -> Any:
    """Read JSON with caching and file locking."""
    lock = _get_lock(path)
    with lock:
        now = time.time()
        if (
            not force
            and path in _cache
            and (now - _cache_timestamps.get(path, 0)) < CACHE_TTL
        ):
            return _cache[path]

        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            data: Any = {} if path.endswith(".json") else {}
            _cache[path] = data
            _cache_timestamps[path] = now
            return data

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            _cache[path] = data
            _cache_timestamps[path] = now
            return data
        except (json.JSONDecodeError, FileNotFoundError) as e:
            raise StorageError("read", str(e))


def _write_json(path: str, data: Any) -> None:
    """Write JSON with file locking and cache invalidation."""
    lock = _get_lock(path)
    with lock:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            _cache[path] = data
            _cache_timestamps[path] = time.time()
        except (OSError, TypeError) as e:
            raise StorageError("write", str(e))


def _invalidate_cache() -> None:
    """Clear the entire cache."""
    _cache.clear()
    _cache_timestamps.clear()


# ─

BOOK_SCHEMA = {
    "book_id",
    "title",
    "author",
    "isbn",
    "category",
    "total_copies",
    "available_copies",
    "is_deleted",
    "issue_count",
    "added_on",
}

USER_SCHEMA = {
    "user_id",
    "name",
    "email",
    "phone",
    "role",
    "password_hash",
    "membership_status",
    "membership_expiry",
    "books_issued",
    "unpaid_fine",
    "registered_on",
}

TRANSACTION_SCHEMA = {
    "txn_id",
    "type",
    "user_id",
    "book_id",
    "issue_date",
    "due_date",
    "return_date",
    "fine",
}

FINE_SCHEMA = {"user_id", "book_id", "fine", "date", "paid"}

NOTIFICATION_SCHEMA = {"notif_id", "user_id", "type", "message", "created_at", "read"}


def _validate_item(item: dict, schema: set, name: str) -> None:
    """Validate that an item matches the expected schema."""
    missing = schema - set(item.keys())
    if missing:
        raise StorageError("validation", f"{name} missing fields: {missing}")


# STORAGE CLASS


class Storage:
    """Thread-safe JSON storage with caching and schema validation."""

    # ── Books ──────────────────────────────────────────────────

    def load_books(self, force: bool = False) -> dict[str, Book]:
        raw: dict = _read_json(Config.BOOKS_FILE, force=force)
        books: dict[str, Book] = {}
        for k, v in raw.items():
            _validate_item(v, BOOK_SCHEMA, "book")
            books[k] = Book.from_dict(v)
        return books

    def save_books(self, books: dict[str, Book]) -> None:
        _write_json(Config.BOOKS_FILE, {k: v.to_dict() for k, v in books.items()})

    # ── Users ──────────────────────────────────────────────────

    def load_users(self, force: bool = False) -> dict[str, User]:
        raw: dict = _read_json(Config.USERS_FILE, force=force)
        users: dict[str, User] = {}
        for k, v in raw.items():
            _validate_item(v, USER_SCHEMA, "user")
            users[k] = User.from_dict(v)
        return users

    def save_users(self, users: dict[str, User]) -> None:
        _write_json(Config.USERS_FILE, {k: v.to_dict() for k, v in users.items()})

    # ── Transactions ───────────────────────────────────────────

    def load_transactions(self, force: bool = False) -> list:
        raw: dict = _read_json(Config.TRANSACTIONS_FILE, force=force)
        return raw.get("transactions", [])

    def save_transactions(self, txns: list) -> None:
        for t in txns:
            _validate_item(t, TRANSACTION_SCHEMA, "transaction")
        _write_json(Config.TRANSACTIONS_FILE, {"transactions": txns})

    def append_transaction(self, txn: dict) -> None:
        txns = self.load_transactions()
        txns.append(txn)
        self.save_transactions(txns)
        _invalidate_cache()

    # ── Reservations ───────────────────────────────────────────

    def load_reservations(self, force: bool = False) -> dict:
        return _read_json(Config.RESERVATIONS_FILE, force=force)

    def save_reservations(self, res: dict) -> None:
        _write_json(Config.RESERVATIONS_FILE, res)

    # ── Fines ──────────────────────────────────────────────────

    def load_fines(self, force: bool = False) -> list:
        raw: dict = _read_json(Config.FINES_FILE, force=force)
        return raw.get("fines", [])

    def save_fines(self, fines: list) -> None:
        for f in fines:
            _validate_item(f, FINE_SCHEMA, "fine")
        _write_json(Config.FINES_FILE, {"fines": fines})

    def append_fine(self, fine: dict) -> None:
        fines = self.load_fines()
        fines.append(fine)
        self.save_fines(fines)
        _invalidate_cache()

    # ── Notifications ──────────────────────────────────────────

    def load_notifications(self, force: bool = False) -> list:
        raw: dict = _read_json(Config.NOTIFICATIONS_FILE, force=force)
        return raw.get("notifications", [])

    def save_notifications(self, notifs: list) -> None:
        for n in notifs:
            _validate_item(n, NOTIFICATION_SCHEMA, "notification")
        _write_json(Config.NOTIFICATIONS_FILE, {"notifications": notifs})

    def append_notification(self, notif: dict) -> None:
        notifs = self.load_notifications()
        notifs.append(notif)
        self.save_notifications(notifs)
        _invalidate_cache()

    # ── Social: Posts ───────────────────────────────────────────

    def load_posts(self, force: bool = False) -> list:
        path = os.path.join(Config.DATA_DIR, "posts.json")
        return _read_json(path, force=force) or []

    def save_posts(self, posts: list) -> None:
        path = os.path.join(Config.DATA_DIR, "posts.json")
        _write_json(path, posts)

    def append_post(self, post: dict) -> None:
        posts = self.load_posts()
        posts.append(post)
        self.save_posts(posts)
        _invalidate_cache()

    # ── Social: Comments ────────────────────────────────────────

    def load_comments(self, force: bool = False) -> list:
        path = os.path.join(Config.DATA_DIR, "comments.json")
        return _read_json(path, force=force) or []

    def save_comments(self, comments: list) -> None:
        path = os.path.join(Config.DATA_DIR, "comments.json")
        _write_json(path, comments)

    def append_comment(self, comment: dict) -> None:
        comments = self.load_comments()
        comments.append(comment)
        self.save_comments(comments)
        _invalidate_cache()

    # ── Social: Follows ─────────────────────────────────────────

    def load_follows(self, force: bool = False) -> list:
        path = os.path.join(Config.DATA_DIR, "follows.json")
        return _read_json(path, force=force) or []

    def save_follows(self, follows: list) -> None:
        path = os.path.join(Config.DATA_DIR, "follows.json")
        _write_json(path, follows)

    # ── Social: Reviews ─────────────────────────────────────────

    def load_reviews(self, force: bool = False) -> list:
        path = os.path.join(Config.DATA_DIR, "reviews.json")
        return _read_json(path, force=force) or []

    def save_reviews(self, reviews: list) -> None:
        path = os.path.join(Config.DATA_DIR, "reviews.json")
        _write_json(path, reviews)

    def append_review(self, review: dict) -> None:
        reviews = self.load_reviews()
        reviews.append(review)
        self.save_reviews(reviews)
        _invalidate_cache()

    # ── Social: Bookshelves ─────────────────────────────────────

    def load_bookshelves(self, force: bool = False) -> list:
        path = os.path.join(Config.DATA_DIR, "bookshelves.json")
        return _read_json(path, force=force) or []

    def save_bookshelves(self, shelves: list) -> None:
        path = os.path.join(Config.DATA_DIR, "bookshelves.json")
        _write_json(path, shelves)

    # ── Utility ────────────────────────────────────────────────

    def clear_cache(self) -> None:
        """Force clear the data cache (useful after external changes)."""
        _invalidate_cache()
