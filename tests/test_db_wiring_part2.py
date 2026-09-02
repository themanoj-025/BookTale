"""tests/test_db_wiring.py - Phase 2 wiring verification.

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
   sandboxed DATA_DIR — the DB lands in that temp dir). — Part 2."""

from __future__ import annotations
import json
import threading
import app.db.database as dbmod
from app.config.settings import Config
from app.db.database import create_all
from app.db.storage_adapter import DbStorage, create_storage
from app.services.books.library import Library
from app.storage.storage import Storage


def _seed_users(store, *user_ids: str) -> None:
    """Seed users so FK-referencing rows can be inserted."""
    from app.models.user import User
    users = {}
    for uid in user_ids:
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
    from app.models.book import Book
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


def test_comments_follows_reviews_bookshelves_roundtrip(store) -> None:
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


def test_clear_cache_is_noop(store) -> None:
    store.clear_cache()  # must not raise


# ─────────────────────────────────────────────────────────────────────
# 2. Library delegates the transactional core to LibraryService on DB
# ─────────────────────────────────────────────────────────────────────


def test_library_delegates_on_db(db_env) -> None:
    store = DbStorage()
    lib = Library(store)
    assert lib._service is not None  # transactional service wired in
    # JSON storage keeps the legacy path (no delegation)
    json_lib = Library(Storage())
    assert json_lib._service is None


def test_library_issue_no_oversell_through_app_object(db_env) -> None:
    """20 threads racing for the last copy via the app's own Library object:
    exactly one success, losers get a clean reservation message."""
    store = DbStorage()
    lib = Library(store)
    lib.add_book("Only Copy", "Author", "111-222", "Fiction", 1, fetch_cover_async=False)
    book_id = next(iter(store.load_books()))
    for i in range(20):
        lib.register_user(f"MEM-{i}", f"User{i}", f"u{i}@x.io", "", "user", "hash", actor="test")

    results = []  # (user_index, ok, msg) — index captured, NOT list position
    lock = threading.Lock()

    def _try(i: int) -> None:
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
    assert all("reservation" in r[2].lower() or "already" in r[2].lower() for r in losers)

    # return path works through the service too (winner's real user index)
    winner_idx = winners[0][0]
    ok, _msg, fine = lib.return_book(f"MEM-{winner_idx}", book_id, actor="Librarian")
    assert ok and fine == 0.0
    assert store.load_books()[book_id].available_copies == 1


# ─────────────────────────────────────────────────────────────────────
# 3. create_storage() factory switching
# ─────────────────────────────────────────────────────────────────────


def test_factory_returns_json_backend(monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "json")
    assert isinstance(create_storage(), Storage)


def test_factory_returns_db_backend(monkeypatch, db_env) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "db")
    assert isinstance(create_storage(), DbStorage)


def test_factory_defaults_to_db_backend(monkeypatch, db_env) -> None:
    """Unset STORAGE_BACKEND resolves to the relational backend (production
    default) — not silently falling back to JSON."""
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    assert isinstance(create_storage(), DbStorage)


# ─────────────────────────────────────────────────────────────────────
# 4. Migration parity through the adapter (schema-drift columns survive)
# ─────────────────────────────────────────────────────────────────────


def test_migrated_post_preserves_social_columns(monkeypatch, tmp_path) -> None:
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


def test_audit_log_roundtrip_and_search(db_env) -> None:
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


def test_audit_log_pagination(db_env) -> None:
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
