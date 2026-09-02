"""test_library.py - Comprehensive test suite for Library Management System — Part 2."""

import os
from app.core.logger import get_logs, log
from app.models.book import Book
from app.models.user import User
from app.services.auth.auth import hash_password
from app.services.books.backup import create_backup, list_backups, restore_backup
from app.services.books.library import Library
from app.services.notifications.notifications import NotificationManager
from app.services.recommendations.recommender import Recommender
from app.storage.storage import Storage

class TestRecommender:
    def test_recommend_similar_books(self, lib: Library, storage: Storage) -> None:
        """Test content-based recommendations."""
        _ok1, bid1 = lib.add_book(
            "Harry Potter 1", "J.K. Rowling", "1111111111", "Fiction", 2, actor="test"
        )
        _ok2, bid2 = lib.add_book(
            "Harry Potter 2", "J.K. Rowling", "2222222222", "Fiction", 2, actor="test"
        )
        lib.add_book("Science Book", "S. Author", "3333333333", "Science", 2, actor="test")

        recommender = Recommender(storage)
        recs = recommender.recommend_similar_books(bid1)
        assert len(recs) > 0
        # Harry Potter 2 should be the top recommendation (same author + category)
        assert recs[0]["book_id"] == bid2

    def test_recommend_trending(self, lib: Library, storage: Storage) -> None:
        """Test trending recommendations."""
        _ok, bid1 = lib.add_book("Popular Book", "Author", "1111111111", "Fiction", 5, actor="test")
        lib.add_book("Unpopular Book", "Author2", "2222222222", "Science", 5, actor="test")

        # Make first book popular
        book = lib.get_book(bid1)
        book.issue_count = 100
        lib.storage.save_books({bid1: book})

        recommender = Recommender(storage)
        recs = recommender.recommend_trending()
        assert len(recs) > 0
        assert recs[0]["book_id"] == bid1

    def test_recommend_by_category(self, lib: Library, storage: Storage) -> None:
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

    def test_recommend_for_user(self, lib: Library, storage: Storage) -> None:
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
        _ok, bid = lib.add_book(
            "Fiction Book", "Fav Author", "1111111111", "Fiction", 5, actor="test"
        )

        # User borrows a fiction book
        lib.issue_book("U001", bid, actor="librarian")

        # Add more fiction books
        lib.add_book("Another Fiction", "Fav Author", "2222222222", "Fiction", 5, actor="test")

        recommender = Recommender(storage)
        recs = recommender.recommend_for_user("U001")
        assert len(recs) > 0

    def test_get_all_categories(self, lib: Library, storage: Storage) -> None:
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
    def test_add_notification(self, storage: Storage) -> None:
        """Test adding a notification."""
        notif_mgr = NotificationManager(storage)
        nid = notif_mgr.add_notification("U001", "test", "Hello!")
        assert nid.startswith("NOTIF-")

    def test_get_unread_count(self, storage: Storage) -> None:
        """Test unread notification count."""
        notif_mgr = NotificationManager(storage)
        notif_mgr.add_notification("U001", "test", "Msg 1")
        notif_mgr.add_notification("U001", "test", "Msg 2")
        notif_mgr.add_notification("U002", "test", "Msg 3")
        assert notif_mgr.get_unread_count("U001") == 2
        assert notif_mgr.get_unread_count("U002") == 1

    def test_mark_as_read(self, storage: Storage) -> None:
        """Test marking notifications as read."""
        notif_mgr = NotificationManager(storage)
        nid = notif_mgr.add_notification("U001", "test", "Hello!")
        notif_mgr.mark_as_read(nid)
        assert notif_mgr.get_unread_count("U001") == 0

    def test_mark_all_read(self, storage: Storage) -> None:
        """Test marking all notifications as read."""
        notif_mgr = NotificationManager(storage)
        notif_mgr.add_notification("U001", "test", "Msg 1")
        notif_mgr.add_notification("U001", "test", "Msg 2")
        notif_mgr.mark_all_read("U001")
        assert notif_mgr.get_unread_count("U001") == 0

    def test_overdue_notification(self, storage: Storage) -> None:
        """Test overdue notification creation."""
        notif_mgr = NotificationManager(storage)
        notif_mgr.notify_overdue("U001", "The Great Book", 5, 25.0)
        notifs = notif_mgr.get_notifications("U001")
        assert len(notifs) == 1
        assert "overdue" in notifs[0]["message"].lower()

    def test_reservation_notification(self, storage: Storage) -> None:
        """Test reservation available notification."""
        notif_mgr = NotificationManager(storage)
        notif_mgr.notify_reservation_available("U001", "The Great Book")
        notifs = notif_mgr.get_notifications("U001")
        assert len(notifs) == 1
        assert "reserved" in notifs[0]["message"].lower()


# STORAGE TESTS


class TestStorage:
    def test_save_load_books(self, storage: Storage) -> None:
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

    def test_save_load_users(self, storage: Storage) -> None:
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

    def test_append_transaction(self, storage: Storage) -> None:
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

    def test_append_fine(self, storage: Storage) -> None:
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

    def test_append_notification(self, storage: Storage) -> None:
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

    def test_clear_cache(self, storage: Storage) -> None:
        """Test cache clearing."""
        storage.load_books()
        storage.clear_cache()
        # No error means success


# BACKUP TESTS


class TestBackup:
    def test_create_backup(self, storage: Storage) -> None:
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

    def test_list_backups(self) -> None:
        """Test listing backups."""
        create_backup(triggered_by="test")
        backups = list_backups()
        assert len(backups) > 0

    def test_create_and_restore(self, storage: Storage) -> None:
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
    def test_log(self) -> None:
        """Test logging an entry."""
        log("Test action", "test_user", "extra info")
        logs = get_logs(10)
        assert len(logs) >= 1
        assert "Test action" in logs[-1]

    def test_log_empty(self) -> None:
        """Test getting logs when none exist."""
        logs = get_logs(10)
        assert isinstance(logs, list)
