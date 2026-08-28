"""Tests for Book-Tale custom exception hierarchy.

Tests all exception classes for correct message formatting, attribute access,
and inheritance chain.
"""

import pytest

from app.core.exceptions import (
    AuthenticationError,
    BookAlreadyDeletedError,
    BookError,
    BookNotAvailableError,
    BookNotFoundError,
    BookNotIssuedError,
    BorrowLimitExceededError,
    DuplicateISBNError,
    LibraryError,
    OutstandingFineError,
    StorageError,
    TransactionError,
    UserAlreadyExistsError,
    UserBlockedError,
    UserError,
    UserNotFoundError,
)


class TestLibraryError:
    """Test base exception class."""

    def test_message(self) -> None:
        exc = LibraryError("test message")
        assert str(exc) == "test message"
        assert exc.message == "test message"

    def test_inheritance(self) -> None:
        assert issubclass(LibraryError, Exception)


class TestBookErrors:
    """Test book-related exceptions."""

    def test_book_not_found(self) -> None:
        exc = BookNotFoundError("BK001")
        assert exc.book_id == "BK001"
        assert "BK001" in str(exc)
        assert issubclass(exc, BookError)

    def test_book_not_available(self) -> None:
        exc = BookNotAvailableError("BK002")
        assert exc.book_id == "BK002"
        assert issubclass(exc, BookError)

    def test_book_already_deleted(self) -> None:
        exc = BookAlreadyDeletedError("BK003")
        assert exc.book_id == "BK003"
        assert issubclass(exc, BookError)

    def test_duplicate_isbn(self) -> None:
        exc = DuplicateISBNError("978-0-13-468599-1", "BK004")
        assert exc.isbn == "978-0-13-468599-1"
        assert exc.existing_id == "BK004"
        assert issubclass(exc, BookError)


class TestUserErrors:
    """Test user-related exceptions."""

    def test_user_not_found(self) -> None:
        exc = UserNotFoundError("USER001")
        assert exc.user_id == "USER001"
        assert issubclass(exc, UserError)

    def test_user_already_exists(self) -> None:
        exc = UserAlreadyExistsError("USER002")
        assert exc.user_id == "USER002"
        assert issubclass(exc, UserError)

    def test_user_blocked(self) -> None:
        exc = UserBlockedError("USER003", "blocked")
        assert exc.user_id == "USER003"
        assert exc.status == "blocked"
        assert issubclass(exc, UserError)

    def test_borrow_limit_exceeded(self) -> None:
        exc = BorrowLimitExceededError("USER004", 3)
        assert exc.user_id == "USER004"
        assert exc.limit == 3
        assert issubclass(exc, UserError)

    def test_outstanding_fine(self) -> None:
        exc = OutstandingFineError("USER005", 150.50)
        assert exc.user_id == "USER005"
        assert exc.amount == 150.50
        assert issubclass(exc, UserError)


class TestAuthError:
    """Test authentication exception."""

    def test_message(self) -> None:
        exc = AuthenticationError()
        assert "Invalid credentials" in str(exc)
        assert issubclass(exc, LibraryError)


class TestTransactionErrors:
    """Test transaction-related exceptions."""

    def test_book_not_issued(self) -> None:
        exc = BookNotIssuedError("USER006", "BK005")
        assert exc.user_id == "USER006"
        assert exc.book_id == "BK005"
        assert issubclass(exc, TransactionError)


class TestStorageError:
    """Test storage exception."""

    def test_with_detail(self) -> None:
        exc = StorageError("save", "disk full")
        assert exc.operation == "save"
        assert "save" in str(exc)
        assert "disk full" in str(exc)

    def test_without_detail(self) -> None:
        exc = StorageError("load")
        assert exc.operation == "load"
        assert "load" in str(exc)


class TestInheritanceChain:
    """Test full inheritance chain."""

    def test_book_errors_inherit_from_library(self) -> None:
        assert issubclass(BookError, LibraryError)
        assert issubclass(BookNotFoundError, LibraryError)

    def test_user_errors_inherit_from_library(self) -> None:
        assert issubclass(UserError, LibraryError)
        assert issubclass(UserNotFoundError, LibraryError)

    def test_transaction_errors_inherit_from_library(self) -> None:
        assert issubclass(TransactionError, LibraryError)
        assert issubclass(BookNotIssuedError, LibraryError)
