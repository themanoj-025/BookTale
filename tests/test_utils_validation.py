"""Tests for app.core.utils validation functions."""

from datetime import datetime

from app.core.utils import (
    colored,
    format_date,
    validate_email,
    validate_isbn,
    validate_phone,
)
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


class TestValidateEmail:
    def test_valid_emails(self) -> None:
        assert validate_email("user@example.com") is True
        assert validate_email("john.doe@uni.edu") is True
        assert validate_email("test+tag@domain.co") is True

    def test_invalid_emails(self) -> None:
        assert validate_email("notanemail") is False
        assert validate_email("@domain.com") is False
        assert validate_email("user@") is False
        assert validate_email("") is False


class TestValidatePhone:
    def test_valid_phones(self) -> None:
        assert validate_phone("1234567890") is True
        assert validate_phone("+91 123 456 7890") is True
        assert validate_phone("+1-555-123-4567") is True

    def test_invalid_phones(self) -> None:
        assert validate_phone("123") is False
        assert validate_phone("abcdefghij") is False
        assert validate_phone("") is False


class TestValidateIsbn:
    def test_valid_isbn10(self) -> None:
        assert validate_isbn("0123456789") is True

    def test_valid_isbn13(self) -> None:
        assert validate_isbn("9780123456789") is True

    def test_valid_isbn_with_dashes(self) -> None:
        assert validate_isbn("0-123-45678-9") is True

    def test_invalid_isbn(self) -> None:
        assert validate_isbn("123") is False
        assert validate_isbn("abc") is False
        assert validate_isbn("") is False


class TestFormatDate:
    def test_valid_iso(self) -> None:
        result = format_date("2024-01-15T10:30:00")
        assert "2024" in result or "Jan" in result

    def test_invalid_iso(self) -> None:
        assert format_date("not-a-date") == "not-a-date"

    def test_none(self) -> None:
        assert format_date(None) is None  # type: ignore[arg-type]


class TestColored:
    def test_color_codes(self) -> None:
        result = colored("hello", "red")
        assert "hello" in result
        assert "\033[" in result

    def test_unknown_color(self) -> None:
        result = colored("hello", "unknown")
        assert "hello" in result


class TestExceptionsHierarchy:
    """Test exception hierarchy."""

    def test_library_error_is_base(self) -> None:
        assert issubclass(BookError, LibraryError)
        assert issubclass(UserError, LibraryError)
        assert issubclass(TransactionError, LibraryError)
        assert issubclass(StorageError, LibraryError)

    def test_book_errors(self) -> None:
        assert issubclass(BookNotFoundError, BookError)
        assert issubclass(BookNotAvailableError, BookError)
        assert issubclass(BookAlreadyDeletedError, BookError)
        assert issubclass(DuplicateISBNError, BookError)

    def test_user_errors(self) -> None:
        assert issubclass(UserNotFoundError, UserError)
        assert issubclass(UserAlreadyExistsError, UserError)
        assert issubclass(UserBlockedError, UserError)
        assert issubclass(BorrowLimitExceededError, UserError)
        assert issubclass(OutstandingFineError, UserError)
        assert issubclass(AuthenticationError, LibraryError)

    def test_transaction_errors(self) -> None:
        assert issubclass(BookNotIssuedError, TransactionError)


class TestExceptionMessages:
    def test_book_not_found(self) -> None:
        e = BookNotFoundError("B001")
        assert "B001" in str(e)
        assert e.book_id == "B001"

    def test_user_not_found(self) -> None:
        e = UserNotFoundError("U001")
        assert "U001" in str(e)
        assert e.user_id == "U001"

    def test_borrow_limit(self) -> None:
        e = BorrowLimitExceededError("U001", 3)
        assert "3" in str(e)
        assert e.limit == 3

    def test_duplicate_isbn(self) -> None:
        e = DuplicateISBNError("1234567890", "B001")
        assert "1234567890" in str(e)
        assert e.existing_id == "B001"

    def test_storage_error(self) -> None:
        e = StorageError("read", "file not found")
        assert "read" in str(e)
        assert "file not found" in str(e)

    def test_outstanding_fine(self) -> None:
        e = OutstandingFineError("U001", 150.50)
        assert "150.50" in str(e)
        assert e.amount == 150.50
