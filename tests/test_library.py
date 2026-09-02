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
from app.models.book import Book
from app.models.user import User
from app.services.auth.auth import AuthManager, hash_password, verify_password
from app.services.books.library import Library
from app.storage.storage import Storage

# ─


@pytest.fixture(autouse=True)
def clean_data_dirs() -> None:
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
    ok, result = lib.add_book("Test Book", "Test Author", "1234567890", "Fiction", 3, actor="test")
    assert ok
    return result


# BOOK TESTS


class TestBook:
    def test_book_creation(self) -> None:
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

    def test_book_to_dict_from_dict(self) -> None:
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

    def test_book_display(self) -> None:
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
    def test_user_creation(self) -> None:
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

    def test_user_is_active(self) -> None:
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

    def test_user_can_borrow(self) -> None:
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

    def test_user_to_dict_from_dict(self) -> None:
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
    def test_hash_password(self) -> None:
        """Test password hashing with bcrypt."""
        hashed = hash_password("test123")
        assert hashed.startswith("$2b$"), "bcrypt hash should start with $2b$"
        assert len(hashed) == 60, "bcrypt hash should be 60 characters"
        assert verify_password("test123", hashed) is True
        assert verify_password("wrong", hashed) is False

    def test_login_success(self, storage: Storage, lib: Library, admin_user: str) -> None:
        """Test successful login."""
        auth = AuthManager(storage)
        user = auth.login("ADMIN001", "admin123")
        assert user is not None
        assert user.user_id == "ADMIN001"
        assert auth.is_logged_in() is True
        assert auth.require_role("admin") is True

    def test_login_failure(self, storage: Storage, lib: Library, admin_user: str) -> None:
        """Test failed login."""
        from app.core.exceptions import AuthenticationError

        auth = AuthManager(storage)
        with pytest.raises(AuthenticationError):
            auth.login("ADMIN001", "wrong_password")

    def test_login_nonexistent(self, storage: Storage) -> None:
        """Test login with non-existent user."""
        from app.core.exceptions import AuthenticationError

        auth = AuthManager(storage)
        with pytest.raises(AuthenticationError):
            auth.login("FAKE", "anything")

    def test_logout(self, storage: Storage, lib: Library, admin_user: str) -> None:
        """Test logout clears session."""
        auth = AuthManager(storage)
        auth.login("ADMIN001", "admin123")
        assert auth.is_logged_in() is True
        auth.logout()
        assert auth.is_logged_in() is False

    def test_require_role(self, storage: Storage, lib: Library, admin_user: str, normal_user: str) -> None:
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
    def test_add_book(self, lib: Library) -> None:
        """Test adding a book."""
        ok, result = lib.add_book("Title", "Author", "1111111111", "Fiction", 2, actor="test")
        assert ok is True
        assert result.startswith("BK-")

    def test_add_book_duplicate_isbn(self, lib: Library) -> None:
        """Test adding duplicate ISBN fails."""
        lib.add_book("Book 1", "Author", "1111111111", "Fiction", 1, actor="test")
        ok, result = lib.add_book("Book 2", "Author", "1111111111", "Fiction", 1, actor="test")
        assert ok is False
        assert "already exists" in result

    def test_get_book(self, lib: Library) -> None:
        """Test retrieving a book."""
        _ok, bid = lib.add_book("Test", "Author", "1111111111", "Fiction", 1, actor="test")
        book = lib.get_book(bid)
        assert book is not None
        assert book.title == "Test"

    def test_get_book_not_found(self, lib: Library) -> None:
        """Test getting a non-existent book."""
        assert lib.get_book("FAKE") is None

    def test_search_books(self, lib: Library) -> None:
        """Test searching books by various fields."""
        lib.add_book("Harry Potter", "J.K. Rowling", "1111111111", "Fiction", 1, actor="test")
        lib.add_book("The Hobbit", "J.R.R. Tolkien", "2222222222", "Fiction", 1, actor="test")

        results = lib.search_books(query="Harry", search_by="title")
        assert len(results) == 1

        results = lib.search_books(query="potter", search_by="all")
        assert len(results) == 1

        results = lib.search_books(category="Fiction")
        assert len(results) == 2

    def test_update_book(self, lib: Library) -> None:
        """Test updating a book."""
        ok, bid = lib.add_book("Original", "Author", "1111111111", "Fiction", 1, actor="test")
        ok, _msg = lib.update_book(bid, title="Updated")
        assert ok is True
        book = lib.get_book(bid)
        assert book.title == "Updated"

    def test_delete_book(self, lib: Library) -> None:
        """Test soft-deleting a book."""
        ok, bid = lib.add_book("Test", "Author", "1111111111", "Fiction", 1, actor="test")
        ok, _msg = lib.delete_book(bid, actor="test")
        assert ok is True
        book = lib.get_book(bid)
        assert book.is_deleted is True

    def test_register_user(self, lib: Library) -> None:
        """Test user registration."""
        ok, _msg = lib.register_user(
            "U001",
            "User",
            "u@test.com",
            "123",
            "user",
            hash_password("pass"),
            actor="test",
        )
        assert ok is True

    def test_register_duplicate_user(self, lib: Library) -> None:
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

    def test_block_unblock_user(self, lib: Library) -> None:
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

        ok, _msg = lib.block_user("U001", actor="admin")
        assert ok is True
        user = lib.get_user("U001")
        assert user.membership_status == "Blocked"

        ok, _msg = lib.unblock_user("U001", actor="admin")
        assert ok is True
        user = lib.get_user("U001")
        assert user.membership_status == "Active"

    def test_renew_membership(self, lib: Library) -> None:
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

    def test_issue_book(self, lib: Library) -> None:
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
        ok, bid = lib.add_book("Test", "Author", "1111111111", "Fiction", 2, actor="test")
        ok, msg = lib.issue_book("U001", bid, actor="librarian")
        assert ok is True
        assert "issued" in msg.lower() or "due" in msg.lower()

    def test_issue_book_not_available(self, lib: Library) -> None:
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
        ok, bid = lib.add_book("Test", "Author", "1111111111", "Fiction", 0, actor="test")
        ok, msg = lib.issue_book("U001", bid, actor="librarian")
        assert ok is False
        assert "reservation" in msg.lower() or "unavailable" in msg.lower()

    def test_issue_book_max_limit(self, lib: Library) -> None:
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
        ok, bid = lib.add_book("Book 4", "Author", "4111111111", "Fiction", 1, actor="test")
        ok, msg = lib.issue_book("U001", bid, actor="librarian")
        assert ok is False
        assert "limit" in msg.lower()

    def test_return_book(self, lib: Library) -> None:
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
        ok, bid = lib.add_book("Test", "Author", "1111111111", "Fiction", 2, actor="test")
        lib.issue_book("U001", bid, actor="librarian")
        ok, _msg, fine = lib.return_book("U001", bid, actor="librarian")
        assert ok is True
        assert fine >= 0

    def test_return_book_not_issued(self, lib: Library) -> None:
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
        ok, bid = lib.add_book("Test", "Author", "1111111111", "Fiction", 1, actor="test")
        ok, msg, _fine = lib.return_book("U001", bid, actor="librarian")
        assert ok is False
        assert "not issued" in msg.lower()

    def test_pay_fine(self, lib: Library) -> None:
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

        ok, _msg = lib.pay_fine("U001", 50.0, actor="admin")
        assert ok is True

        user = lib.get_user("U001")
        assert user.unpaid_fine == 50.0

    def test_get_overdue_list(self, lib: Library) -> None:
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
        _ok, bid = lib.add_book("Test", "Author", "1111111111", "Fiction", 1, actor="test")

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

