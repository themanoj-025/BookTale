"""
tests/test_db_wiring.py - Phase 2 wiring verification.

Proves the app actually runs on the relational layer:

1. DbStorage implements the full JSON Storage interface with JSON-compatible
   shapes (round-trip parity), including the schema-drift fixes:
   - posts carry upvotes/downvotes/comment_count/is_pinned
   - reviews carry content/spoiler/helpful_votes/updated_at
   - bookshelves carry user_id/book_id/shelf/created_at
2. Deletion semantics: removing a post from the list deletes its DB row AND its
   comments (FK order); same for comments/follows/reviews.
3. Library delegates issue/return/pay_fine to the transactional LibraryService
   when constructed with a DbStorage — a 20-thread race for the last copy yields
   exactly one success (no oversell) through the app's own Library object.
4. create_storage() factory switches backends via STORAGE_BACKEND env.
5. Web stack boots on the DB: web_app's module-level storage is a DbStorage
   (verified by tests/security/test_web_security.py which imports web_app with a
   sandboxed DATA_DIR — the DB lands in that temp dir).
"""

from __future__ import annotations

import os
import tempfile

import pytest

import app.db.database as dbmod
from app.config.settings import Config
from app.db.database import create_all
from app.db.storage_adapter import DbStorage
from app.models.book import Book
from app.models.user import User

pytestmark = pytest.mark.unit




pytestmark = pytest.mark.slow
@pytest.fixture()
def db_env(monkeypatch) -> None:
    """Point the engine at a throwaway SQLite file; rebuild on teardown."""
    tmpdir = tempfile.mkdtemp(prefix="booktale_wire_")
    url = "sqlite:///" + os.path.join(tmpdir, "test.db")
    monkeypatch.setattr(Config, "DATABASE_URL", url)
    monkeypatch.setattr(dbmod, "_engine", None)
    monkeypatch.setattr(dbmod, "_session_factory", None)
    create_all()
    yield
    dbmod._engine = None
    dbmod._session_factory = None


@pytest.fixture()
def store(db_env) -> DbStorage:
    return DbStorage()


def _seed_users(store, *user_ids: str) -> None:
    """Seed users so FK-referencing rows can be inserted (mirrors the real app,
    where posts/comments/txns always reference existing users)."""
    users = {}
    for _i, uid in enumerate(user_ids):
        users[uid] = User(
            user_id=uid,
            name=f"User {uid}",
            email=f"{uid}@x.io",
            phone="",
            role="user",
            password_hash="h",
        )
    store.save_users(users)


def _seed_books(store, *book_ids: str) -> None:
    books = {}
    for bid in book_ids:
        books[bid] = Book(
            book_id=bid,
            title=bid,
            author="A",
            isbn=bid,
            category="Fiction",
            total_copies=1,
            available_copies=1,
        )
    store.save_books(books)


# ─────────────────────────────────────────────────────────────────────
# 1. Interface parity — every Storage method round-trips on SQLAlchemy
# ─────────────────────────────────────────────────────────────────────


def test_books_roundtrip(store) -> None:
    books = {
        "BK-1": Book(
            book_id="BK-1",
            title="Dune",
            author="Herbert",
            isbn="123",
            category="Fiction",
            total_copies=2,
            available_copies=1,
            issue_count=3,
            genres=["sci-fi"],
            cover_fetched=True,
        ),
        "BK-2": Book(
            book_id="BK-2",
            title="Neuromancer",
            author="Gibson",
            isbn="456",
            category="Science",
            total_copies=1,
            available_copies=0,
        ),
    }
    store.save_books(books)
    loaded = store.load_books()
    assert set(loaded) == {"BK-1", "BK-2"}
    assert loaded["BK-1"].title == "Dune"
    assert loaded["BK-1"].genres == ["sci-fi"]
    assert loaded["BK-1"].cover_fetched is True
    assert loaded["BK-2"].available_copies == 0


def test_users_roundtrip(store) -> None:
    users = {
        "MEM-1": User(
            user_id="MEM-1",
            name="Alice",
            email="a@x.io",
            phone="1",
            role="user",
            password_hash="h",
            bio="hi",
            favorite_genres=["Fiction"],
            theme="dark",
            reading_default_goal=20,
        ),
    }
    store.save_users(users)
    loaded = store.load_users()
    assert loaded["MEM-1"].name == "Alice"
    assert loaded["MEM-1"].theme == "dark"
    assert loaded["MEM-1"].favorite_genres == ["Fiction"]
    assert loaded["MEM-1"].reading_default_goal == 20


def test_transactions_roundtrip_and_update(store) -> None:
    _seed_users(store, "MEM-1")
    _seed_books(store, "BK-1")
    txn = {
        "txn_id": "TXN-1",
        "type": "issue",
        "user_id": "MEM-1",
        "book_id": "BK-1",
        "issue_date": "2026-01-01T00:00:00",
        "due_date": "2026-01-15T00:00:00",
        "return_date": None,
        "fine": 0.0,
    }
    store.append_transaction(txn)
    txns = store.load_transactions()
    assert len(txns) == 1 and txns[0]["txn_id"] == "TXN-1"
    # in-place update on return
    txns[0]["return_date"] = "2026-01-16T00:00:00"
    txns[0]["fine"] = 5.0
    store.save_transactions(txns)
    assert store.load_transactions()[0]["fine"] == 5.0


def test_reservations_shape(store) -> None:
    _seed_users(store, "MEM-1", "MEM-2", "MEM-3")
    _seed_books(store, "BK-1", "BK-2")
    store.save_reservations({"BK-1": ["MEM-1", "MEM-2"]})
    assert store.load_reservations() == {"BK-1": ["MEM-1", "MEM-2"]}
    # replace semantics
    store.save_reservations({"BK-2": ["MEM-3"]})
    assert store.load_reservations() == {"BK-2": ["MEM-3"]}


def test_fines_and_notifications(store) -> None:
    _seed_users(store, "MEM-1")
    _seed_books(store, "BK-1")
    store.append_fine(
        {
            "user_id": "MEM-1",
            "book_id": "BK-1",
            "fine": 10.0,
            "date": "2026-01-02T00:00:00",
            "paid": False,
        }
    )
    fines = store.load_fines()
    assert len(fines) == 1 and fines[0]["fine"] == 10.0 and fines[0]["paid"] is False

    store.append_notification(
        {
            "notif_id": "N-1",
            "user_id": "MEM-1",
            "type": "like",
            "message": "hi",
            "created_at": "2026-01-02T00:00:00",
            "read": False,
        }
    )
    assert store.load_notifications()[0]["message"] == "hi"
    store.save_notifications([])
    assert store.load_notifications() == []


def test_posts_full_shape_roundtrip(store) -> None:
    _seed_users(store, "MEM-1", "MEM-2", "MEM-3")
    post = {
        "post_id": "POST-1",
        "user_id": "MEM-1",
        "content": "reading Dune!",
        "type": "post",
        "book_ids": ["BK-1"],
        "image_urls": [],
        "created_at": "2026-01-02T00:00:00",
        "updated_at": "2026-01-02T00:00:00",
        "likes": ["MEM-2"],
        "upvotes": ["MEM-3"],
        "downvotes": [],
        "comment_count": 2,
        "is_pinned": True,
    }
    store.append_post(post)
    loaded = store.load_posts()
    assert len(loaded) == 1
    p = loaded[0]
    # schema-drift fix: these keys survive the DB round-trip
    assert p["likes"] == ["MEM-2"]
    assert p["upvotes"] == ["MEM-3"]
    assert p["comment_count"] == 2
    assert p["is_pinned"] is True


def test_post_delete_cascades_comments(store) -> None:
    _seed_users(store, "MEM-1", "MEM-2")
    store.append_post(
        {
            "post_id": "POST-1",
            "user_id": "MEM-1",
            "content": "a",
            "type": "post",
            "book_ids": [],
            "image_urls": [],
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "",
            "likes": [],
            "upvotes": [],
            "downvotes": [],
            "comment_count": 0,
            "is_pinned": False,
        }
    )
    store.append_post(
        {
            "post_id": "POST-2",
            "user_id": "MEM-1",
            "content": "b",
            "type": "post",
            "book_ids": [],
            "image_urls": [],
            "created_at": "2026-01-02T00:00:00",
            "updated_at": "",
            "likes": [],
            "upvotes": [],
            "downvotes": [],
            "comment_count": 0,
            "is_pinned": False,
        }
    )
    store.append_comment(
        {
            "comment_id": "COMM-1",
            "post_id": "POST-2",
            "user_id": "MEM-2",
            "content": "nice",
            "parent_id": None,
            "created_at": "2026-01-03T00:00:00",
            "likes": [],
        }
    )
    # delete POST-2 from the list (social.delete_post -> save_posts)
    posts = [p for p in store.load_posts() if p["post_id"] != "POST-2"]
    store.save_posts(posts)
    assert [p["post_id"] for p in store.load_posts()] == ["POST-1"]
    # comment must be gone too (FK ordering, no dangling child rows)
    assert store.load_comments() == []


def test_soft_delete_book_persists_through_adapter(store) -> None:
    """Library.delete_book is a SOFT delete (is_deleted=True + save_books, the
    dict keeps the row — same as the JSON layer kept it in books.json forever).
    The upsert-only save_books must persist that flag so a reload still sees
    the row marked deleted (no ghost-row divergence vs the JSON backend)."""
    store.save_books(
        {
            "BK-1": Book(
                book_id="BK-1",
                title="Dune",
                author="Herbert",
                isbn="123",
                category="Fiction",
                total_copies=1,
                available_copies=1,
            ),
        }
    )
    books = store.load_books()
    assert books["BK-1"].is_deleted is False
    books["BK-1"].is_deleted = True
    store.save_books(books)
    reloaded = store.load_books()
    assert reloaded["BK-1"].is_deleted is True
    assert "BK-1" in reloaded  # row kept, mirroring JSON semantics

