"""
exceptions.py - Custom exception hierarchy for the Library Management System
"""


class LibraryError(Exception):
    """Base exception for all library-related errors."""

    def __init__(self, message: str, *args: object) -> None:
        self.message = message
        super().__init__(message, *args)


class BookError(LibraryError):
    """Base exception for book-related errors."""


class BookNotFoundError(BookError):
    """Raised when a book is not found."""

    def __init__(self, book_id: str) -> None:
        super().__init__(f"Book not found: {book_id}")
        self.book_id = book_id


class BookNotAvailableError(BookError):
    """Raised when a book has no available copies."""

    def __init__(self, book_id: str) -> None:
        super().__init__(f"No available copies for book: {book_id}")
        self.book_id = book_id


class BookAlreadyDeletedError(BookError):
    """Raised when trying to modify a deleted book."""

    def __init__(self, book_id: str) -> None:
        super().__init__(f"Book is already deleted: {book_id}")
        self.book_id = book_id


class DuplicateISBNError(BookError):
    """Raised when a book with the same ISBN already exists."""

    def __init__(self, isbn: str, existing_id: str) -> None:
        super().__init__(f"Book with ISBN {isbn} already exists (ID: {existing_id})")
        self.isbn = isbn
        self.existing_id = existing_id


class UserError(LibraryError):
    """Base exception for user-related errors."""


class UserNotFoundError(UserError):
    """Raised when a user is not found."""

    def __init__(self, user_id: str) -> None:
        super().__init__(f"User not found: {user_id}")
        self.user_id = user_id


class UserAlreadyExistsError(UserError):
    """Raised when trying to register a duplicate user ID."""

    def __init__(self, user_id: str) -> None:
        super().__init__(f"User ID already exists: {user_id}")
        self.user_id = user_id


class UserBlockedError(UserError):
    """Raised when a blocked user tries to borrow."""

    def __init__(self, user_id: str, status: str) -> None:
        super().__init__(f"User {user_id} is {status}")
        self.user_id = user_id
        self.status = status


class BorrowLimitExceededError(UserError):
    """Raised when a user has reached their borrow limit."""

    def __init__(self, user_id: str, limit: int) -> None:
        super().__init__(f"User {user_id} has reached max borrow limit ({limit})")
        self.user_id = user_id
        self.limit = limit


class OutstandingFineError(UserError):
    """Raised when a user has unpaid fines."""

    def __init__(self, user_id: str, amount: float) -> None:
        super().__init__(f"User {user_id} has unpaid fine of ₹{amount:.2f}")
        self.user_id = user_id
        self.amount = amount


class AuthenticationError(LibraryError):
    """Raised when login fails."""

    def __init__(self) -> None:
        super().__init__("Invalid credentials")


class TransactionError(LibraryError):
    """Base exception for transaction-related errors."""


class BookNotIssuedError(TransactionError):
    """Raised when returning a book not issued to the user."""

    def __init__(self, user_id: str, book_id: str) -> None:
        super().__init__(f"Book {book_id} is not issued to user {user_id}")
        self.user_id = user_id
        self.book_id = book_id


class StorageError(LibraryError):
    """Raised on storage I/O failures."""

    def __init__(self, operation: str, detail: str = "") -> None:
        msg = f"Storage error during {operation}"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)
        self.operation = operation
