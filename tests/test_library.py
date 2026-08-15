"""
test_library.py - Comprehensive test suite for Library Management System
"""

import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.config.settings import Config
from app.core.logger import get_logs, log
from app.models.book import Book
from app.models.user import User
from app.services.auth.auth import AuthManager, hash_password, verify_password
from app.services.books.backup import create_backup, list_backups, restore_backup
from app.services.books.library import Library
from app.services.notifications.notifications import NotificationManager
from app.services.recommendations.recommender import Recommender
from app.storage.storage import Storage

# ─


@pytest.fixture(autouse=True)
def clean_data_dirs():
    """Use temporary directories for each test to ensure isolation."""
    tmpdir = tempfile.mkdtemp()
    old_data = Config.DATA_DIR
    old_logs = Config.LOGS_DIR
    old_backups = Config.BACKUPS_DIR
    old_log_file = Config.LOG_FILE
    old_json_log = Config.JSON_LOG

    Config.DATA_DIR = os.path.join(tmpdir, "data")
    Config.LOGS_DIR = os.path.join(tmpdir, "logs")
    Config.BACKUPS_DIR = os.path.join(tmpdir, "backups")
    Config.BOOKS_FILE = os.path.join(Config.DATA_DIR, "books.json")
    Config.USERS_FILE = os.path.join(Config.DATA_DIR, "users.json")
    Config.TRANSACTIONS_FILE = os.path.join(Config.DATA_DIR, "transactions.json")
    Config.RESERVATIONS_FILE = os.path.join(Config.DATA_DIR, "reservations.json")
    Config.FINES_FILE = os.path.join(Config.DATA_DIR, "fines.json")
    Config.NOTIFICATIONS_FILE = os.path.join(Config.DATA_DIR, "notifications.json")
    Config.LOG_FILE = os.path.join(Config.LOGS_DIR, "activity.log")
    Config.JSON_LOG = os.path.join(Config.LOGS_DIR, "activity.json")

    os.makedirs(Config.DATA_DIR, exist_ok=True)
    os.makedirs(Config.LOGS_DIR, exist_ok=True)
    os.makedirs(Config.BACKUPS_DIR, exist_ok=True)

    yield

    # Restore the exact pre-test Config values first (other test modules may
    # have redirected these at module level; re-deriving from LOGS_DIR would
    # silently leak their temp paths into subsequent tests).
    Config.DATA_DIR = old_data
    Config.LOGS_DIR = old_logs
    Config.BACKUPS_DIR = old_backups
    Config.BOOKS_FILE = os.path.join(old_data, "books.json")
    Config.USERS_FILE = os.path.join(old_data, "users.json")
    Config.TRANSACTIONS_FILE = os.path.join(old_data, "transactions.json")
    Config.RESERVATIONS_FILE = os.path.join(old_data, "reservations.json")
    Config.FINES_FILE = os.path.join(old_data, "fines.json")
    Config.NOTIFICATIONS_FILE = os.path.join(old_data, "notifications.json")
    Config.LOG_FILE = old_log_file
    Config.JSON_LOG = old_json_log

    # Close logger file handles before rmtree (Windows file-lock fix). Run
    # AFTER restoring Config so the module-level _log_file_path cache re-syncs
    # with the restored paths instead of the just-deleted temp dir.
    from app.core.logger import reset_logger

    reset_logger()
    shutil.rmtree(tmpdir)


@pytest.fixture
def storage() -> Storage:
    return Storage()


@pytest.fixture
def lib(storage: Storage) -> Library:
    return Library(storage)


@pytest.fixture
def auth(storage: Storage) -> AuthManager:
    return AuthManager(storage)


@pytest.fixture
def admin_user(lib: Library, auth: AuthManager) -> str:
    """Create and return admin user ID."""
    lib.register_user(
        "ADMIN001",
        "Admin",
        "admin@lib.com",
        "0000000000",
        "admin",
        hash_password("admin123"),
        actor="test",
    )
    return "ADMIN001"


@pytest.fixture
def normal_user(lib: Library) -> str:
    """Create and return a normal user ID."""
    lib.register_user(
        "USER001",
        "Test User",
        "user@test.com",
        "1234567890",
        "user",
        hash_password("pass123"),
        actor="test",
    )
    return "USER001"


@pytest.fixture
def sample_book(lib: Library) -> str:
    """Add a sample book and return its ID."""
    ok, result = lib.add_book(
        "Test Book", "Test Author", "1234567890", "Fiction", 3, actor="test"
    )
    assert ok
    return result


# BOOK TESTS


class TestBook:
    def test_book_creation(self):
        """Test that a Book object is created correctly."""
        book = Book(
            book_id="BK-2026-0001",
            title="Test",
            author="Author",
            isbn="1234567890",
            category="Fiction",
            total_copies=3,
            available_copies=3,
        )
        assert book.book_id == "BK-2026-0001"
        assert book.available_copies == 3
        assert not book.is_deleted

    def test_book_to_dict_from_dict(self):
        """Test serialization/deserialization."""
        book = Book(
            book_id="BK-2026-0001",
            title="Test",
            author="Author",
            isbn="1234567890",
            category="Fiction",
            total_copies=3,
            available_copies=3,
        )
        d = book.to_dict()
        book2 = Book.from_dict(d)
        assert book2.title == "Test"
        assert book2.available_copies == 3

    def test_book_display(self):
        """Test display string."""
        book = Book(
            book_id="BK-2026-0001",
            title="Test",
            author="Author",
            isbn="1234567890",
            category="Fiction",
            total_copies=3,
            available_copies=2,
        )
        display = book.display()
        assert "BK-2026-0001" in display
        assert "Avail: 2/3" in display
        assert "Test" in display


# USER TESTS


class TestUser:
    def test_user_creation(self):
        """Test User creation with defaults."""
        user = User(
            user_id="U001",
            name="John",
            email="john@test.com",
            phone="123",
            role="user",
            password_hash="hash",
        )
        assert user.membership_status == "Active"
        assert len(user.books_issued) == 0
        assert user.unpaid_fine == 0.0

    def test_user_is_active(self):
        """Test active/blocked status."""
        user = User(
            user_id="U001",
            name="John",
            email="john@test.com",
            phone="123",
            role="user",
            password_hash="hash",
        )
        assert user.is_active() is True
        user.membership_status = "Blocked"
        assert user.is_active() is False

    def test_user_can_borrow(self):
        """Test borrow limit logic."""
        user = User(
            user_id="U001",
            name="John",
            email="john@test.com",
            phone="123",
            role="user",
            password_hash="hash",
        )
        assert user.can_borrow() is True
        user.books_issued = ["BK-1", "BK-2", "BK-3"]
        assert user.can_borrow() is False  # Max 3

    def test_user_to_dict_from_dict(self):
        """Test serialization/deserialization."""
        user = User(
            user_id="U001",
            name="John",
            email="john@test.com",
            phone="123",
            role="user",
            password_hash="hash",
        )
        d = user.to_dict()
        user2 = User.from_dict(d)
        assert user2.name == "John"
        assert user2.role == "user"


# AUTH TESTS


class TestAuth:
    def test_hash_password(self):
        """Test password hashing with bcrypt."""
        hashed = hash_password("test123")
        assert hashed.startswith("$2b$"), "bcrypt hash should start with $2b$"
        assert len(hashed) == 60, "bcrypt hash should be 60 characters"
        assert verify_password("test123", hashed) is True
        assert verify_password("wrong", hashed) is False

    def test_login_success(self, storage: Storage, lib: Library, admin_user: str):
        """Test successful login."""
        auth = AuthManager(storage)
        user = auth.login("ADMIN001", "admin123")
        assert user is not None
        assert user.user_id == "ADMIN001"
        assert auth.is_logged_in() is True
        assert auth.require_role("admin") is True

    def test_login_failure(self, storage: Storage, lib: Library, admin_user: str):
        """Test failed login."""
        from app.core.exceptions import AuthenticationError

        auth = AuthManager(storage)
        with pytest.raises(AuthenticationError):
            auth.login("ADMIN001", "wrong_password")

    def test_login_nonexistent(self, storage: Storage):
        """Test login with non-existent user."""
        from app.core.exceptions import AuthenticationError

        auth = AuthManager(storage)
        with pytest.raises(AuthenticationError):
            auth.login("FAKE", "anything")

    def test_logout(self, storage: Storage, lib: Library, admin_user: str):
        """Test logout clears session."""
        auth = AuthManager(storage)
        auth.login("ADMIN001", "admin123")
        assert auth.is_logged_in() is True
        auth.logout()
        assert auth.is_logged_in() is False

    def test_require_role(
        self, storage: Storage, lib: Library, admin_user: str, normal_user: str
    ):
        """Test role checking."""
        auth = AuthManager(storage)
        auth.login("ADMIN001", "admin123")
        assert auth.require_role("admin") is True
        assert auth.require_role("user") is False

        auth.logout()
        auth.login("USER001", "pass123")
        assert auth.require_role("user") is True
        assert auth.require_role("admin") is False


# LIBRARY TESTS (Core Operations)


class TestLibrary:
    def test_add_book(self, lib: Library):
        """Test adding a book."""
        ok, result = lib.add_book(
            "Title", "Author", "1111111111", "Fiction", 2, actor="test"
        )
        assert ok is True
        assert result.startswith("BK-")

    def test_add_book_duplicate_isbn(self, lib: Library):
        """Test adding duplicate ISBN fails."""
        lib.add_book("Book 1", "Author", "1111111111", "Fiction", 1, actor="test")
        ok, result = lib.add_book(
            "Book 2", "Author", "1111111111", "Fiction", 1, actor="test"
        )
        assert ok is False
        assert "already exists" in result

    def test_get_book(self, lib: Library):
        """Test retrieving a book."""
        ok, bid = lib.add_book(
            "Test", "Author", "1111111111", "Fiction", 1, actor="test"
        )
        book = lib.get_book(bid)
        assert book is not None
        assert book.title == "Test"

    def test_get_book_not_found(self, lib: Library):
        """Test getting a non-existent book."""
        assert lib.get_book("FAKE") is None

    def test_search_books(self, lib: Library):
        """Test searching books by various fields."""
        lib.add_book(
            "Harry Potter", "J.K. Rowling", "1111111111", "Fiction", 1, actor="test"
        )
        lib.add_book(
            "The Hobbit", "J.R.R. Tolkien", "2222222222", "Fiction", 1, actor="test"
        )

        results = lib.search_books(query="Harry", search_by="title")
        assert len(results) == 1

        results = lib.search_books(query="potter", search_by="all")
        assert len(results) == 1

        results = lib.search_books(category="Fiction")
        assert len(results) == 2

    def test_update_book(self, lib: Library):
        """Test updating a book."""
        ok, bid = lib.add_book(
            "Original", "Author", "1111111111", "Fiction", 1, actor="test"
        )
        ok, msg = lib.update_book(bid, title="Updated")
        assert ok is True
        book = lib.get_book(bid)
        assert book.title == "Updated"

    def test_delete_book(self, lib: Library):
        """Test soft-deleting a book."""
        ok, bid = lib.add_book(
            "Test", "Author", "1111111111", "Fiction", 1, actor="test"
        )
        ok, msg = lib.delete_book(bid, actor="test")
        assert ok is True
        book = lib.get_book(bid)
        assert book.is_deleted is True

    def test_register_user(self, lib: Library):
        """Test user registration."""
        ok, msg = lib.register_user(
            "U001",
            "User",
            "u@test.com",
            "123",
            "user",
            hash_password("pass"),
            actor="test",
        )
        assert ok is True

    def test_register_duplicate_user(self, lib: Library):
        """Test duplicate user registration fails."""
        lib.register_user(
            "U001",
            "User",
            "u@test.com",
            "123",
            "user",
            hash_password("pass"),
            actor="test",
        )
        ok, msg = lib.register_user(
            "U001",
            "User2",
            "u2@test.com",
            "123",
            "user",
            hash_password("pass"),
            actor="test",
        )
        assert ok is False
        assert "already exists" in msg

    def test_block_unblock_user(self, lib: Library):
        """Test blocking and unblocking users."""
        lib.register_user(
            "U001",
            "User",
            "u@test.com",
            "123",
            "user",
            hash_password("pass"),
            actor="test",
        )

        ok, msg = lib.block_user("U001", actor="admin")
        assert ok is True
        user = lib.get_user("U001")
        assert user.membership_status == "Blocked"

        ok, msg = lib.unblock_user("U001", actor="admin")
        assert ok is True
        user = lib.get_user("U001")
        assert user.membership_status == "Active"

    def test_renew_membership(self, lib: Library):
        """Test membership renewal."""
        lib.register_user(
            "U001",
            "User",
            "u@test.com",
            "123",
            "user",
            hash_password("pass"),
            actor="test",
        )
        ok, msg = lib.renew_membership("U001", days=30, actor="admin")
        assert ok is True
        assert "30" in msg or "renewed" in msg

    def test_issue_book(self, lib: Library):
        """Test issuing a book to a user."""
        lib.register_user(
            "U001",
            "User",
            "u@test.com",
            "123",
            "user",
            hash_password("pass"),
            actor="test",
        )
        ok, bid = lib.add_book(
            "Test", "Author", "1111111111", "Fiction", 2, actor="test"
        )
        ok, msg = lib.issue_book("U001", bid, actor="librarian")
        assert ok is True
        assert "issued" in msg.lower() or "due" in msg.lower()

    def test_issue_book_not_available(self, lib: Library):
        """Test issuing an unavailable book creates reservation."""
        lib.register_user(
            "U001",
            "User",
            "u@test.com",
            "123",
            "user",
            hash_password("pass"),
            actor="test",
        )
        ok, bid = lib.add_book(
            "Test", "Author", "1111111111", "Fiction", 0, actor="test"
        )
        ok, msg = lib.issue_book("U001", bid, actor="librarian")
        assert ok is False
        assert "reservation" in msg.lower() or "unavailable" in msg.lower()

    def test_issue_book_max_limit(self, lib: Library):
        """Test borrow limit enforcement."""
        lib.register_user(
            "U001",
            "User",
            "u@test.com",
            "123",
            "user",
            hash_password("pass"),
            actor="test",
        )
        # Issue 3 books to reach limit
        for i in range(3):
            ok, bid = lib.add_book(
                f"Book {i}", "Author", f"{i}111111111", "Fiction", 1, actor="test"
            )
            lib.issue_book("U001", bid, actor="librarian")
        # Try to issue another
        ok, bid = lib.add_book(
            "Book 4", "Author", "4111111111", "Fiction", 1, actor="test"
        )
        ok, msg = lib.issue_book("U001", bid, actor="librarian")
        assert ok is False
        assert "limit" in msg.lower()

    def test_return_book(self, lib: Library):
        """Test returning a book."""
        lib.register_user(
            "U001",
            "User",
            "u@test.com",
            "123",
            "user",
            hash_password("pass"),
            actor="test",
        )
        ok, bid = lib.add_book(
            "Test", "Author", "1111111111", "Fiction", 2, actor="test"
        )
        lib.issue_book("U001", bid, actor="librarian")
        ok, msg, fine = lib.return_book("U001", bid, actor="librarian")
        assert ok is True
        assert fine >= 0

    def test_return_book_not_issued(self, lib: Library):
        """Test returning a book not issued to user."""
        lib.register_user(
            "U001",
            "User",
            "u@test.com",
            "123",
            "user",
            hash_password("pass"),
            actor="test",
        )
        ok, bid = lib.add_book(
            "Test", "Author", "1111111111", "Fiction", 1, actor="test"
        )
        ok, msg, fine = lib.return_book("U001", bid, actor="librarian")
        assert ok is False
        assert "not issued" in msg.lower()

    def test_pay_fine(self, lib: Library):
        """Test fine payment."""
        lib.register_user(
            "U001",
            "User",
            "u@test.com",
            "123",
            "user",
            hash_password("pass"),
            actor="test",
        )
        # Add a fine directly
        user = lib.get_user("U001")
        user.unpaid_fine = 100.0
        users = {user.user_id: user}
        lib.storage.save_users(users)

        ok, msg = lib.pay_fine("U001", 50.0, actor="admin")
        assert ok is True

        user = lib.get_user("U001")
        assert user.unpaid_fine == 50.0

    def test_get_overdue_list(self, lib: Library):
        """Test overdue list retrieval."""
        lib.register_user(
            "U001",
            "User",
            "u@test.com",
            "123",
            "user",
            hash_password("pass"),
            actor="test",
        )
        ok, bid = lib.add_book(
            "Test", "Author", "1111111111", "Fiction", 1, actor="test"
        )

        # Issue and make it overdue by manipulating the transaction
        lib.issue_book("U001", bid, actor="librarian")
        txns = lib.storage.load_transactions()
        # Set the due date to 10 days ago
        past_date = (datetime.now() - timedelta(days=10)).isoformat()
        for t in txns:
            if t["book_id"] == bid and t["return_date"] is None:
                t["due_date"] = past_date
        lib.storage.save_transactions(txns)

        overdue = lib.get_overdue_list()
        assert len(overdue) > 0
        assert overdue[0]["days_overdue"] >= 10


# RECOMMENDER TESTS


class TestRecommender:
    def test_recommend_similar_books(self, lib: Library, storage: Storage):
        """Test content-based recommendations."""
        ok1, bid1 = lib.add_book(
            "Harry Potter 1", "J.K. Rowling", "1111111111", "Fiction", 2, actor="test"
        )
        ok2, bid2 = lib.add_book(
            "Harry Potter 2", "J.K. Rowling", "2222222222", "Fiction", 2, actor="test"
        )
        lib.add_book(
            "Science Book", "S. Author", "3333333333", "Science", 2, actor="test"
        )

        recommender = Recommender(storage)
        recs = recommender.recommend_similar_books(bid1)
        assert len(recs) > 0
        # Harry Potter 2 should be the top recommendation (same author + category)
        assert recs[0]["book_id"] == bid2

    def test_recommend_trending(self, lib: Library, storage: Storage):
        """Test trending recommendations."""
        ok, bid1 = lib.add_book(
            "Popular Book", "Author", "1111111111", "Fiction", 5, actor="test"
        )
        lib.add_book(
            "Unpopular Book", "Author2", "2222222222", "Science", 5, actor="test"
        )

        # Make first book popular
        book = lib.get_book(bid1)
        book.issue_count = 100
        lib.storage.save_books({bid1: book})

        recommender = Recommender(storage)
        recs = recommender.recommend_trending()
        assert len(recs) > 0
        assert recs[0]["book_id"] == bid1

    def test_recommend_by_category(self, lib: Library, storage: Storage):
        """Test category-based recommendations."""
        # Add many books to avoid seed data cold-start fallback
        lib.add_book("Fiction 1", "Author", "1111111111", "Fiction", 1, actor="test")
        lib.add_book("Fiction 2", "Author", "2222222222", "Fiction", 1, actor="test")
        lib.add_book("Fiction 3", "Author", "3333333333", "Fiction", 1, actor="test")
        lib.add_book("Fiction 4", "Author", "4444444444", "Fiction", 1, actor="test")
        lib.add_book("Fiction 5", "Author", "5555555555", "Fiction", 1, actor="test")
        lib.add_book("Science 1", "Author", "6666666666", "Science", 1, actor="test")
        lib.add_book("Science 2", "Author", "7777777777", "Science", 1, actor="test")
        lib.add_book("Science 3", "Author", "8888888888", "Science", 1, actor="test")
        lib.add_book("History 1", "Author", "9999999999", "History", 1, actor="test")
        lib.add_book("History 2", "Author", "0000000000", "History", 1, actor="test")

        recommender = Recommender(storage)
        recs = recommender.recommend_by_category("Fiction")
        assert len(recs) == 5

    def test_recommend_for_user(self, lib: Library, storage: Storage):
        """Test personalized user recommendations."""
        lib.register_user(
            "U001",
            "User",
            "u@test.com",
            "123",
            "user",
            hash_password("pass"),
            actor="test",
        )
        ok, bid = lib.add_book(
            "Fiction Book", "Fav Author", "1111111111", "Fiction", 5, actor="test"
        )

        # User borrows a fiction book
        lib.issue_book("U001", bid, actor="librarian")

        # Add more fiction books
        lib.add_book(
            "Another Fiction", "Fav Author", "2222222222", "Fiction", 5, actor="test"
        )

        recommender = Recommender(storage)
        recs = recommender.recommend_for_user("U001")
        assert len(recs) > 0

    def test_get_all_categories(self, lib: Library, storage: Storage):
        """Test category listing."""
        # Add many books to avoid seed data cold-start fallback
        lib.add_book("Book 1", "Author", "1111111111", "Fiction", 1, actor="test")
        lib.add_book("Book 2", "Author", "2222222222", "Science", 1, actor="test")
        lib.add_book("Book 3", "Author", "3333333333", "History", 1, actor="test")
        lib.add_book("Book 4", "Author", "4444444444", "Science", 1, actor="test")
        lib.add_book("Book 5", "Author", "5555555555", "Fiction", 1, actor="test")
        lib.add_book("Book 6", "Author", "6666666666", "Other", 1, actor="test")
        lib.add_book("Book 7", "Author", "7777777777", "Education", 1, actor="test")
        lib.add_book("Book 8", "Author", "8888888888", "Science", 1, actor="test")
        lib.add_book("Book 9", "Author", "9999999999", "Fiction", 1, actor="test")
        lib.add_book("Book 10", "Author", "0000000000", "History", 1, actor="test")

        recommender = Recommender(storage)
        cats = recommender.get_all_categories_with_counts()
        assert len(cats) == 5


# NOTIFICATION TESTS


class TestNotifications:
    def test_add_notification(self, storage: Storage):
        """Test adding a notification."""
        notif_mgr = NotificationManager(storage)
        nid = notif_mgr.add_notification("U001", "test", "Hello!")
        assert nid.startswith("NOTIF-")

    def test_get_unread_count(self, storage: Storage):
        """Test unread notification count."""
        notif_mgr = NotificationManager(storage)
        notif_mgr.add_notification("U001", "test", "Msg 1")
        notif_mgr.add_notification("U001", "test", "Msg 2")
        notif_mgr.add_notification("U002", "test", "Msg 3")
        assert notif_mgr.get_unread_count("U001") == 2
        assert notif_mgr.get_unread_count("U002") == 1

    def test_mark_as_read(self, storage: Storage):
        """Test marking notifications as read."""
        notif_mgr = NotificationManager(storage)
        nid = notif_mgr.add_notification("U001", "test", "Hello!")
        notif_mgr.mark_as_read(nid)
        assert notif_mgr.get_unread_count("U001") == 0

    def test_mark_all_read(self, storage: Storage):
        """Test marking all notifications as read."""
        notif_mgr = NotificationManager(storage)
        notif_mgr.add_notification("U001", "test", "Msg 1")
        notif_mgr.add_notification("U001", "test", "Msg 2")
        notif_mgr.mark_all_read("U001")
        assert notif_mgr.get_unread_count("U001") == 0

    def test_overdue_notification(self, storage: Storage):
        """Test overdue notification creation."""
        notif_mgr = NotificationManager(storage)
        notif_mgr.notify_overdue("U001", "The Great Book", 5, 25.0)
        notifs = notif_mgr.get_notifications("U001")
        assert len(notifs) == 1
        assert "overdue" in notifs[0]["message"].lower()

    def test_reservation_notification(self, storage: Storage):
        """Test reservation available notification."""
        notif_mgr = NotificationManager(storage)
        notif_mgr.notify_reservation_available("U001", "The Great Book")
        notifs = notif_mgr.get_notifications("U001")
        assert len(notifs) == 1
        assert "reserved" in notifs[0]["message"].lower()


# STORAGE TESTS


class TestStorage:
    def test_save_load_books(self, storage: Storage):
        """Test saving and loading books."""
        book = Book(
            book_id="BK-1",
            title="Test",
            author="Author",
            isbn="123",
            category="Fiction",
            total_copies=1,
            available_copies=1,
        )
        storage.save_books({"BK-1": book})
        loaded = storage.load_books()
        assert "BK-1" in loaded
        assert loaded["BK-1"].title == "Test"

    def test_save_load_users(self, storage: Storage):
        """Test saving and loading users."""
        user = User(
            user_id="U001",
            name="John",
            email="j@t.com",
            phone="123",
            role="user",
            password_hash="hash",
        )
        storage.save_users({"U001": user})
        loaded = storage.load_users()
        assert "U001" in loaded
        assert loaded["U001"].name == "John"

    def test_append_transaction(self, storage: Storage):
        """Test appending transactions."""
        txn = {
            "txn_id": "TXN-1",
            "type": "issue",
            "user_id": "U001",
            "book_id": "BK-1",
            "issue_date": "2026-01-01",
            "due_date": "2026-01-15",
            "return_date": None,
            "fine": 0,
        }
        storage.append_transaction(txn)
        txns = storage.load_transactions()
        assert len(txns) == 1
        assert txns[0]["txn_id"] == "TXN-1"

    def test_append_fine(self, storage: Storage):
        """Test appending fines."""
        fine = {
            "user_id": "U001",
            "book_id": "BK-1",
            "fine": 10.0,
            "date": "2026-01-01",
            "paid": False,
        }
        storage.append_fine(fine)
        fines = storage.load_fines()
        assert len(fines) == 1

    def test_append_notification(self, storage: Storage):
        """Test appending notifications."""
        notif = {
            "notif_id": "NOTIF-1",
            "user_id": "U001",
            "type": "test",
            "message": "Hello",
            "created_at": "2026-01-01",
            "read": False,
        }
        storage.append_notification(notif)
        notifs = storage.load_notifications()
        assert len(notifs) == 1

    def test_clear_cache(self, storage: Storage):
        """Test cache clearing."""
        storage.load_books()
        storage.clear_cache()
        # No error means success


# BACKUP TESTS


class TestBackup:
    def test_create_backup(self, storage: Storage):
        """Test creating a backup."""
        # Save some data first
        book = Book(
            book_id="BK-1",
            title="Test",
            author="Author",
            isbn="123",
            category="Fiction",
            total_copies=1,
            available_copies=1,
        )
        storage.save_books({"BK-1": book})

        path = create_backup(triggered_by="test")
        assert os.path.exists(path)

    def test_list_backups(self):
        """Test listing backups."""
        create_backup(triggered_by="test")
        backups = list_backups()
        assert len(backups) > 0

    def test_create_and_restore(self, storage: Storage):
        """Test restore operation."""
        book = Book(
            book_id="BK-1",
            title="Test",
            author="Author",
            isbn="123",
            category="Fiction",
            total_copies=1,
            available_copies=1,
        )
        storage.save_books({"BK-1": book})
        path = create_backup(triggered_by="test")
        assert restore_backup(path) is True


# LOGGER TESTS


class TestLogger:
    def test_log(self):
        """Test logging an entry."""
        log("Test action", "test_user", "extra info")
        logs = get_logs(10)
        assert len(logs) >= 1
        assert "Test action" in logs[-1]

    def test_log_empty(self):
        """Test getting logs when none exist."""
        logs = get_logs(10)
        assert isinstance(logs, list)
