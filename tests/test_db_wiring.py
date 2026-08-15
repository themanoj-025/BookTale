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

import json
import os
import tempfile
import threading

import pytest

import app.db.database as dbmod
from app.config.settings import Config
from app.db.database import create_all
from app.db.storage_adapter import DbStorage, create_storage
from app.models.book import Book
from app.models.user import User
from app.services.books.library import Library
from app.storage.storage import Storage


@pytest.fixture()
def db_env(monkeypatch):
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
    for i, uid in enumerate(user_ids):
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


def test_books_roundtrip(store):
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


def test_users_roundtrip(store):
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


def test_transactions_roundtrip_and_update(store):
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


def test_reservations_shape(store):
    _seed_users(store, "MEM-1", "MEM-2", "MEM-3")
    _seed_books(store, "BK-1", "BK-2")
    store.save_reservations({"BK-1": ["MEM-1", "MEM-2"]})
    assert store.load_reservations() == {"BK-1": ["MEM-1", "MEM-2"]}
    # replace semantics
    store.save_reservations({"BK-2": ["MEM-3"]})
    assert store.load_reservations() == {"BK-2": ["MEM-3"]}


def test_fines_and_notifications(store):
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


def test_posts_full_shape_roundtrip(store):
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


def test_post_delete_cascades_comments(store):
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


def test_soft_delete_book_persists_through_adapter(store):
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


def test_comments_follows_reviews_bookshelves_roundtrip(store):
    _seed_users(store, "MEM-1", "MEM-2")
    _seed_books(store, "BK-1")
    store.append_post(
        {
            "post_id": "POST-1",
            "user_id": "MEM-1",
            "content": "x",
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
    store.append_comment(
        {
            "comment_id": "COMM-1",
            "post_id": "POST-1",
            "user_id": "MEM-1",
            "content": "hi",
            "parent_id": None,
            "created_at": "2026-01-01T00:00:00",
            "likes": ["MEM-2"],
        }
    )
    assert store.load_comments()[0]["likes"] == ["MEM-2"]

    store.save_follows(
        [
            {
                "follow_id": "FOL-1",
                "follower_id": "MEM-1",
                "following_id": "MEM-2",
                "created_at": "2026-01-01T00:00:00",
            }
        ]
    )
    assert store.load_follows()[0]["following_id"] == "MEM-2"
    store.save_follows([])  # unfollow -> row deleted
    assert store.load_follows() == []

    review = {
        "review_id": "REV-1",
        "user_id": "MEM-1",
        "book_id": "BK-1",
        "rating": 4,
        "content": "loved it",
        "spoiler": True,
        "helpful_votes": ["MEM-2"],
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-02T00:00:00",
    }
    store.append_review(review)
    r = store.load_reviews()[0]
    assert r["content"] == "loved it" and r["spoiler"] is True
    assert r["helpful_votes"] == ["MEM-2"]

    store.save_bookshelves(
        [
            {
                "user_id": "MEM-1",
                "book_id": "BK-1",
                "shelf": "reading",
                "created_at": "2026-01-01T00:00:00",
            }
        ]
    )
    s = store.load_bookshelves()[0]
    assert s["shelf"] == "reading" and s["book_id"] == "BK-1"


def test_clear_cache_is_noop(store):
    store.clear_cache()  # must not raise


# ─────────────────────────────────────────────────────────────────────
# 2. Library delegates the transactional core to LibraryService on DB
# ─────────────────────────────────────────────────────────────────────


def test_library_delegates_on_db(db_env):
    store = DbStorage()
    lib = Library(store)
    assert lib._service is not None  # transactional service wired in
    # JSON storage keeps the legacy path (no delegation)
    json_lib = Library(Storage())
    assert json_lib._service is None


def test_library_issue_no_oversell_through_app_object(db_env):
    """20 threads racing for the last copy via the app's own Library object:
    exactly one success, losers get a clean reservation message."""
    store = DbStorage()
    lib = Library(store)
    lib.add_book(
        "Only Copy", "Author", "111-222", "Fiction", 1, fetch_cover_async=False
    )
    book_id = list(store.load_books())[0]
    for i in range(20):
        lib.register_user(
            f"MEM-{i}", f"User{i}", f"u{i}@x.io", "", "user", "hash", actor="test"
        )

    results = []  # (user_index, ok, msg) — index captured, NOT list position
    lock = threading.Lock()

    def _try(i: int):
        ok, msg = lib.issue_book(f"MEM-{i}", book_id, actor="Librarian")
        with lock:
            results.append((i, ok, msg))

    threads = [threading.Thread(target=_try, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    winners = [r for r in results if r[1]]
    assert len(winners) == 1, f"expected 1 winner, got {len(winners)}: {results}"
    losers = [r for r in results if not r[1]]
    assert all(
        "reservation" in r[2].lower() or "already" in r[2].lower() for r in losers
    )

    # return path works through the service too (winner's real user index)
    winner_idx = winners[0][0]
    ok, msg, fine = lib.return_book(f"MEM-{winner_idx}", book_id, actor="Librarian")
    assert ok and fine == 0.0
    assert store.load_books()[book_id].available_copies == 1


# ─────────────────────────────────────────────────────────────────────
# 3. create_storage() factory switching
# ─────────────────────────────────────────────────────────────────────


def test_factory_returns_json_backend(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "json")
    assert isinstance(create_storage(), Storage)


def test_factory_returns_db_backend(monkeypatch, db_env):
    monkeypatch.setenv("STORAGE_BACKEND", "db")
    assert isinstance(create_storage(), DbStorage)


def test_factory_defaults_to_db_backend(monkeypatch, db_env):
    """Unset STORAGE_BACKEND resolves to the relational backend (production
    default) — not silently falling back to JSON."""
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    assert isinstance(create_storage(), DbStorage)


# ─────────────────────────────────────────────────────────────────────
# 4. Migration parity through the adapter (schema-drift columns survive)
# ─────────────────────────────────────────────────────────────────────


def test_migrated_post_preserves_social_columns(monkeypatch, tmp_path):
    """A JSON post with upvotes/downvotes/comment_count/is_pinned migrates and
    round-trips through DbStorage with every field intact."""
    from scripts.migrate_json_to_db import migrate as run_migration

    url = "sqlite:///" + str(tmp_path / "mig.db")
    monkeypatch.setattr(Config, "DATABASE_URL", url)
    monkeypatch.setattr(dbmod, "_engine", None)
    monkeypatch.setattr(dbmod, "_session_factory", None)
    create_all()

    data_dir = tmp_path / "json"
    data_dir.mkdir()
    # Seed users.json so the post's FK (user_id) resolves during migration.
    (data_dir / "users.json").write_text(
        json.dumps(
            {
                "MEM-1": {
                    "user_id": "MEM-1",
                    "name": "U1",
                    "email": "u1@x.io",
                    "phone": "",
                    "role": "user",
                    "password_hash": "h",
                    "membership_status": "Active",
                    "membership_expiry": "2099-01-01T00:00:00",
                    "books_issued": [],
                    "unpaid_fine": 0.0,
                    "registered_on": "2026-01-01T00:00:00",
                },
                "MEM-2": {
                    "user_id": "MEM-2",
                    "name": "U2",
                    "email": "u2@x.io",
                    "phone": "",
                    "role": "user",
                    "password_hash": "h",
                    "membership_status": "Active",
                    "membership_expiry": "2099-01-01T00:00:00",
                    "books_issued": [],
                    "unpaid_fine": 0.0,
                    "registered_on": "2026-01-01T00:00:00",
                },
            }
        ),
        encoding="utf-8",
    )
    posts = [
        {
            "post_id": "POST-9",
            "user_id": "MEM-1",
            "content": "migrated",
            "type": "post",
            "book_ids": [],
            "image_urls": [],
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "likes": [],
            "upvotes": ["MEM-2"],
            "downvotes": [],
            "comment_count": 5,
            "is_pinned": True,
        }
    ]
    (data_dir / "posts.json").write_text(json.dumps(posts), encoding="utf-8")
    monkeypatch.setattr(Config, "DATA_DIR", str(data_dir))

    report = run_migration()
    assert report["posts"]["loaded"] == 1 and report["posts"]["skipped"] == 0

    store = DbStorage()
    p = store.load_posts()[0]
    assert p["upvotes"] == ["MEM-2"]
    assert p["comment_count"] == 5
    assert p["is_pinned"] is True


# ─────────────────────────────────────────────────────────────────────
# 5. Admin audit trail (AuditLogRepository)
# ─────────────────────────────────────────────────────────────────────


def test_audit_log_roundtrip_and_search(db_env):
    """Audit entries persist, list newest-first, and filter by query/action."""
    from app.db.repositories import AuditLogRepository

    with dbmod.session_scope() as db:
        repo = AuditLogRepository(db)
        repo.add(
            "ADMIN001",
            "settings.update",
            "FINE_PER_DAY",
            old_value="5.0",
            new_value="7.5",
            ip_address="10.0.0.1",
        )
        repo.add(
            "ADMIN001",
            "settings.update",
            "LIBRARY_NAME",
            old_value="Old",
            new_value="New",
            ip_address="10.0.0.1",
        )
        repo.add(
            "ADMIN002",
            "auth.failed",
            "admin_password",
            new_value="attempt rejected",
            ip_address="10.0.0.2",
        )

    with dbmod.session_scope() as db:
        repo = AuditLogRepository(db)
        # newest first: the auth.failed entry was added last
        all_rows = repo.search()
        assert [r["action"] for r in all_rows] == [
            "auth.failed",
            "settings.update",
            "settings.update",
        ]
        # free-text query matches target and values
        by_q = repo.search(query="FINE_PER_DAY")
        assert len(by_q) == 1 and by_q[0]["new_value"] == "7.5"
        # action filter
        assert repo.count(action="settings.update") == 2
        assert repo.count(action="auth.failed") == 1
        # admin filter
        assert repo.count(admin_id="ADMIN002") == 1
        # IP recorded (from where)
        assert all(r["ip_address"] for r in all_rows)


def test_audit_log_pagination(db_env):
    """Audit search paginates (newest first) and count is total, not page size."""
    from app.db.repositories import AuditLogRepository

    with dbmod.session_scope() as db:
        repo = AuditLogRepository(db)
        for i in range(5):
            repo.add(
                "ADMIN001",
                "settings.update",
                "ISSUE_DAYS",
                old_value=None,
                new_value=str(i),
                ip_address="10.0.0.1",
            )
    with dbmod.session_scope() as db:
        repo = AuditLogRepository(db)
        assert repo.count() == 5
        page1 = repo.search(page=1, per_page=2)
        page2 = repo.search(page=2, per_page=2)
        assert len(page1) == 2 and len(page2) == 2
        # newest first: values 4,3 then 2,1
        assert [r["new_value"] for r in page1] == ["4", "3"]
        assert [r["new_value"] for r in page2] == ["2", "1"]
