"""
tests/test_db_layer.py - Phase 2 DB layer verification.

Covers the four Phase 2 acceptance criteria:
  1. Concurrency: 20 threads racing for the last copy -> exactly 1 success,
     no oversell, losers get a clean "unavailable" error.
  2. Transactional integrity: a crash mid-operation rolls back atomically
     (no half-applied state).
  3. Migration parity: JSON files -> DB row counts match 1:1.
  4. Indexed queries: search / overdue / stats return correct results via
     the repository layer (no full-file scans).
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timedelta

import pytest

import app.db.database as dbmod
from app.config.settings import Config
from app.db.database import create_all, get_session_factory
from app.db.models import Book, Transaction, User
from app.db.repositories import BookRepository, TransactionRepository, library_stats
from app.db.service import LibraryService


@pytest.fixture()
def db_env(monkeypatch):
    """Point the engine at a throwaway SQLite file; rebuild on teardown.

    The engine is cached by URL, so we patch Config.DATABASE_URL to a unique
    temp file per test and reset the module-level engine/session globals.
    """
    tmpdir = tempfile.mkdtemp(prefix="booktale_db_")
    url = "sqlite:///" + os.path.join(tmpdir, "test.db")

    monkeypatch.setattr(Config, "DATABASE_URL", url)
    monkeypatch.setattr(dbmod, "_engine", None)
    monkeypatch.setattr(dbmod, "_session_factory", None)

    create_all()
    yield url
    dbmod._engine = None
    dbmod._session_factory = None


def _seed(users: int = 1, copies: int = 1, book_id: str = "BK-1"):
    """Seed N users + one book; returns (session_factory, user_ids, book_id)."""
    factory = get_session_factory()
    with factory() as db:
        db.add(
            Book(
                book_id=book_id,
                title="Test Book",
                author="Author",
                isbn="9780000000001",
                category="Fiction",
                total_copies=copies,
                available_copies=copies,
            )
        )
        ids = []
        for i in range(users):
            uid = f"U{i:03d}"
            ids.append(uid)
            db.add(
                User(
                    user_id=uid,
                    name=f"User {i}",
                    email=f"u{i}@x.com",
                    phone="",
                    role="user",
                    password_hash="h",
                    membership_status="Active",
                    membership_expiry=(datetime.now() + timedelta(days=365)).isoformat(),
                    books_issued=[],
                    unpaid_fine=0.0,
                )
            )
        db.commit()
    return factory, ids, book_id


# ════════════════════════════════════════════════════════════════════
# 1. CONCURRENCY — last-copy race
# ════════════════════════════════════════════════════════════════════


def test_last_copy_race_no_oversell(db_env):
    """20 threads racing for the last copy: exactly 1 wins, 19 get a clean
    'No copies available' error, and available_copies never goes negative."""
    factory, user_ids, book_id = _seed(users=20, copies=1)

    service = LibraryService(factory)
    results: list = []
    barrier = threading.Barrier(20)

    def attempt(uid: str):
        barrier.wait()
        ok, msg = service.issue_book(uid, book_id)
        results.append((uid, ok, msg))

    threads = [threading.Thread(target=attempt, args=(u,)) for u in user_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    successes = [r for r in results if r[1]]
    failures = [r for r in results if not r[1]]
    assert len(successes) == 1, f"expected 1 winner, got {len(successes)}"
    assert len(failures) == 19
    # Losers must get the reservation-queue message, never a crash or oversell.
    for _, ok, msg in failures:
        assert "No copies available" in msg

    with factory() as db:
        book = db.get(Book, book_id)
        assert book.available_copies == 0
        assert book.issue_count == 1
        txn_count = db.query(Transaction).filter(Transaction.book_id == book_id).count()
        assert txn_count == 1  # exactly one open txn, not 20


def test_double_issue_same_user_rejected(db_env):
    """A user cannot issue the same book twice, even under contention."""
    factory, user_ids, book_id = _seed(users=1, copies=5)
    service = LibraryService(factory)
    ok1, _ = service.issue_book("U000", book_id)
    ok2, msg2 = service.issue_book("U000", book_id)
    assert ok1 is True
    assert ok2 is False
    assert "already has this book issued" in msg2


def test_borrow_limit_enforced(db_env):
    """MAX_BORROW_LIMIT caps concurrent books per user."""
    factory, user_ids, _ = _seed(users=1, copies=10)
    service = LibraryService(factory)
    # Create MAX_BORROW_LIMIT + 1 more single-copy books so the final attempt
    # hits the borrow limit (not a 'book not found').
    with factory() as db:
        for i in range(Config.MAX_BORROW_LIMIT + 1):
            db.add(
                Book(
                    book_id=f"BK-{i + 2}",
                    title=f"B{i}",
                    author="A",
                    isbn=f"9780000000{i:03d}",
                    category="Fiction",
                    total_copies=1,
                    available_copies=1,
                )
            )
        db.commit()
    ok = []
    for i in range(1, Config.MAX_BORROW_LIMIT + 2):
        o, m = service.issue_book("U000", f"BK-{i + 1}")
        ok.append((o, m))
    assert sum(1 for o, _ in ok if o) == Config.MAX_BORROW_LIMIT
    assert ok[-1][0] is False
    assert "max borrow limit" in ok[-1][1]


# ════════════════════════════════════════════════════════════════════
# 2. TRANSACTIONAL INTEGRITY — crash mid-operation
# ════════════════════════════════════════════════════════════════════


def test_crash_mid_issue_rolls_back(db_env):
    """If something raises after the copy is decremented, the whole txn
    rolls back: no copy lost, no dangling txn, user's list untouched."""
    factory, user_ids, book_id = _seed(users=1, copies=1)
    service = LibraryService(factory)

    # Simulate a crash: monkeypatch the txn insert to raise after mutation.
    import app.db.service as svc_mod

    orig = svc_mod.Transaction

    class Boom(Exception):
        pass

    def raiser(*args, **kwargs):
        raise Boom("simulated crash mid-issue")

    svc_mod.Transaction = raiser
    try:
        with pytest.raises(Boom):
            service.issue_book("U000", book_id)
    finally:
        svc_mod.Transaction = orig

    with factory() as db:
        book = db.get(Book, book_id)
        user = db.get(User, "U000")
        assert book.available_copies == 1  # copy restored by rollback
        assert book.issue_count == 0
        assert user.books_issued == []  # no phantom loan
        assert db.query(Transaction).count() == 0  # no dangling txn


def test_return_book_atomic(db_env):
    """Return closes the txn, restores the copy, and applies fine atomically."""
    factory, user_ids, book_id = _seed(users=1, copies=1)
    service = LibraryService(factory)
    service.issue_book("U000", book_id)

    # Force the issue into the past to accrue a fine.
    with factory() as db:
        txn = db.query(Transaction).first()
        old_due = (datetime.now() - timedelta(days=10)).isoformat()
        txn.due_date = old_due
        db.commit()

    ok, msg, fine = service.return_book("U000", book_id)
    assert ok is True
    assert fine > 0
    with factory() as db:
        book = db.get(Book, book_id)
        user = db.get(User, "U000")
        assert book.available_copies == 1
        assert book_id not in (user.books_issued or [])
        assert user.unpaid_fine == fine


def test_return_notifies_next_reservation(db_env):
    """Returning a book serves the next user in the reservation queue and
    creates a notification for them (the _pop_reservation_queue path)."""
    factory, user_ids, book_id = _seed(users=2, copies=1)
    service = LibraryService(factory)
    # U000 holds the only copy; U001 reserves it (gets the queue message).
    ok1, _ = service.issue_book("U000", book_id)
    assert ok1 is True
    ok2, msg2 = service.issue_book("U001", book_id)
    assert ok2 is False
    assert "reservation queue" in msg2

    # U000 returns -> U001 should be notified (message names the user).
    ok, msg, _ = service.return_book("U000", book_id)
    assert ok is True
    assert "User 1" in msg  # _seed names users 'User {i}', U001 == User 1

    with factory() as db:
        from app.db.models import Notification

        notif = db.query(Notification).filter(Notification.user_id == "U001").first()
        assert notif is not None
        assert notif.type == "reservation_available"
        assert notif.read is False
        # Queue is now empty for this book.
        from app.db.models import Reservation

        assert db.query(Reservation).filter(Reservation.book_id == book_id).count() == 0


def test_reserve_book_idempotent(db_env):
    """reserve_book adds a user once; a second call reports already queued."""
    factory, user_ids, book_id = _seed(users=1, copies=1)
    service = LibraryService(factory)
    ok1, msg1 = service.reserve_book("U000", book_id)
    assert ok1 is False
    assert "position 1" in msg1
    ok2, msg2 = service.reserve_book("U000", book_id)
    assert ok2 is False
    assert "already in reservation queue" in msg2


def test_pay_fine_partial(db_env):
    """pay_fine accepts partial payments and tracks the remainder."""
    factory, user_ids, book_id = _seed(users=1, copies=1)
    service = LibraryService(factory)
    service.issue_book("U000", book_id)
    with factory() as db:
        txn = db.query(Transaction).first()
        txn.due_date = (datetime.now() - timedelta(days=10)).isoformat()
        db.commit()
    _, _, fine = service.return_book("U000", book_id)
    # 10 days x FINE_PER_DAY (env-overridable — never hardcode the value)
    assert fine == 10 * Config.FINE_PER_DAY

    ok, msg = service.pay_fine("U000", 20.0)
    assert ok is True
    assert "₹20.00 collected" in msg
    with factory() as db:
        user = db.get(User, "U000")
        assert user.unpaid_fine == 30.0

    ok2, _ = service.pay_fine("U000", 100.0)  # overpay clamps to remainder
    assert ok2 is True
    with factory() as db:
        assert db.get(User, "U000").unpaid_fine == 0.0


def test_overdue_list_tolerates_legacy_dates(db_env):
    """Legacy '%d %b %Y' due dates must not crash get_overdue_list."""
    factory, user_ids, book_id = _seed(users=1, copies=1)
    service = LibraryService(factory)
    service.issue_book("U000", book_id)
    with factory() as db:
        txn = db.query(Transaction).first()
        txn.due_date = (datetime.now() - timedelta(days=2)).strftime("%d %b %Y")
        db.commit()
        overdue = TransactionRepository(db).get_overdue_list()
        assert len(overdue) == 1
        assert overdue[0]["days_overdue"] == 2


# ════════════════════════════════════════════════════════════════════
# 3. MIGRATION PARITY — JSON -> DB
# ════════════════════════════════════════════════════════════════════


def test_migration_parity(db_env, monkeypatch):
    """Seed JSON files, run the one-shot migration, assert row counts match."""
    tmpdir = tempfile.mkdtemp(prefix="booktale_json_")

    books = {
        "BK-1": {
            "book_id": "BK-1",
            "title": "A",
            "author": "B",
            "isbn": "1",
            "category": "Fiction",
            "total_copies": 2,
            "available_copies": 2,
            "is_deleted": False,
            "issue_count": 0,
            "added_on": datetime.now().isoformat(),
        },
        "BK-2": {
            "book_id": "BK-2",
            "title": "C",
            "author": "D",
            "isbn": "2",
            "category": "Sci-Fi",
            "total_copies": 1,
            "available_copies": 1,
            "is_deleted": False,
            "issue_count": 3,
            "added_on": datetime.now().isoformat(),
        },
    }
    users = {
        "U001": {
            "user_id": "U001",
            "name": "Ann",
            "email": "a@x.com",
            "phone": "",
            "role": "user",
            "password_hash": "h",
            "membership_status": "Active",
            "membership_expiry": datetime.now().isoformat(),
            "books_issued": [],
            "unpaid_fine": 0.0,
            "registered_on": datetime.now().isoformat(),
        },
    }
    txns = {
        "transactions": [
            {
                "txn_id": "TXN-1",
                "type": "issue",
                "user_id": "U001",
                "book_id": "BK-1",
                "issue_date": datetime.now().isoformat(),
                "due_date": (datetime.now() + timedelta(days=14)).isoformat(),
                "return_date": None,
                "fine": 0.0,
            }
        ]
    }
    fines = {
        "fines": [
            {
                "user_id": "U001",
                "book_id": "BK-1",
                "fine": 5.0,
                "date": datetime.now().isoformat(),
                "paid": False,
            }
        ]
    }
    notifs = {
        "notifications": [
            {
                "notif_id": "N1",
                "user_id": "U001",
                "type": "info",
                "message": "hi",
                "created_at": datetime.now().isoformat(),
                "read": False,
            }
        ]
    }

    for name, data in [
        ("books.json", books),
        ("users.json", users),
        ("transactions.json", txns),
        ("fines.json", fines),
        ("notifications.json", notifs),
    ]:
        with open(os.path.join(tmpdir, name), "w", encoding="utf-8") as f:
            json.dump(data, f)

    # Point the migrator at the temp JSON dir (it reads Config.DATA_DIR).
    monkeypatch.setattr(Config, "DATA_DIR", tmpdir)

    from scripts.migrate_json_to_db import migrate

    report = migrate()

    assert report["books"]["loaded"] == 2
    assert report["users"]["loaded"] == 1
    assert report["transactions"]["loaded"] == 1
    assert report["fines"]["loaded"] == 1
    assert report["notifications"]["loaded"] == 1
    for name, counts in report.items():
        assert counts["source"] == counts["loaded"], f"{name} parity broken"


def test_migration_missing_files_are_empty(db_env, monkeypatch):
    """No JSON files at all -> migration succeeds with zero counts."""
    tmpdir = tempfile.mkdtemp(prefix="booktale_empty_")
    monkeypatch.setattr(Config, "DATA_DIR", tmpdir)
    from scripts.migrate_json_to_db import migrate

    report = migrate()
    for counts in report.values():
        assert counts["source"] == 0 == counts["loaded"]


# ════════════════════════════════════════════════════════════════════
# 4. INDEXED QUERIES — repositories
# ════════════════════════════════════════════════════════════════════


def test_search_pagination_and_filters(db_env):
    factory, user_ids, _ = _seed(users=1, copies=1)
    with factory() as db:
        db.add_all(
            [
                Book(
                    book_id="BK-10",
                    title="Python Programming",
                    author="Guido",
                    isbn="9780000000010",
                    category="CS",
                    total_copies=1,
                    available_copies=1,
                ),
                Book(
                    book_id="BK-11",
                    title="Deep Python",
                    author="Van Rossum",
                    isbn="9780000000011",
                    category="CS",
                    total_copies=1,
                    available_copies=1,
                    is_deleted=True,
                ),
                Book(
                    book_id="BK-12",
                    title="A Novel",
                    author="Someone",
                    isbn="9780000000012",
                    category="Fiction",
                    total_copies=1,
                    available_copies=1,
                    issue_count=7,
                ),
            ]
        )
        db.commit()

        repo = BookRepository(db)
        # Deleted books excluded
        assert len(repo.search()) == 3
        # Text search (deleted BK-11 excluded)
        hits = repo.search(query="python")
        assert {b.book_id for b in hits} == {"BK-10"}
        # Category filter
        assert {b.book_id for b in repo.search(category="CS")} == {"BK-10"}
        # Pagination
        p1 = repo.search(page=1, per_page=2)
        p2 = repo.search(page=2, per_page=2)
        assert len(p1) == 2 and len(p2) == 1
        assert not set(b.book_id for b in p1) & set(b.book_id for b in p2)
        # Popular sort
        popular = repo.search(sort_by="popular")
        assert popular[0].book_id == "BK-12"


def test_overdue_list_indexed(db_env):
    factory, user_ids, book_id = _seed(users=1, copies=1)
    service = LibraryService(factory)
    service.issue_book("U000", book_id)
    with factory() as db:
        txn = db.query(Transaction).first()
        txn.due_date = (datetime.now() - timedelta(days=3)).isoformat()
        db.commit()

        overdue = TransactionRepository(db).get_overdue_list()
        assert len(overdue) == 1
        assert overdue[0]["user_id"] == "U000"
        assert overdue[0]["days_overdue"] == 3


def test_library_stats_aggregates(db_env):
    factory, user_ids, book_id = _seed(users=1, copies=2)
    service = LibraryService(factory)
    service.issue_book("U000", book_id)
    with factory() as db:
        stats = library_stats(db)
        assert stats["total_books"] == 1
        assert stats["total_copies"] == 2
        assert stats["avail_copies"] == 1
        assert stats["issued_copies"] == 1
        assert stats["total_users"] == 1
        assert stats["active_users"] == 1
        assert stats["total_txns"] == 1
        assert stats["active_issues"] == 1
