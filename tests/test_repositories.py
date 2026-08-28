"""Tests for Book-Tale repository layer.

Tests CRUD operations and query helpers.
"""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import Book, User, Transaction
from app.db.repositories import (
    BookRepository,
    TransactionRepository,
    UserRepository,
    _parse_dt,
)


@pytest.fixture
def engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session


class TestParseDt:
    """Test the tolerant date parser."""

    def test_parse_iso_date(self) -> None:
        result = _parse_dt("2024-01-15T10:30:00")
        assert result is not None
        assert result.year == 2024

    def test_parse_none(self) -> None:
        assert _parse_dt(None) is None

    def test_parse_empty_string(self) -> None:
        assert _parse_dt("") is None

    def test_parse_legacy_format(self) -> None:
        result = _parse_dt("15 Jan 2024")
        assert result is not None
        assert result.year == 2024

    def test_parse_invalid(self) -> None:
        assert _parse_dt("not-a-date") is None


class TestBookRepository:
    """Test book CRUD operations."""

    def test_add_and_get_book(self, session: Session) -> None:
        repo = BookRepository(session)
        repo.add(book_id="BK001", title="Test Book", author="Author", genre="Fiction")
        book = repo.get("BK001")
        assert book is not None
        assert book.title == "Test Book"

    def test_list_books(self, session: Session) -> None:
        repo = BookRepository(session)
        repo.add(book_id="BK001", title="Book 1", author="A", genre="Fiction")
        repo.add(book_id="BK002", title="Book 2", author="B", genre="Sci-Fi")
        books = repo.list_all()
        assert len(books) == 2

    def test_search_books(self, session: Session) -> None:
        repo = BookRepository(session)
        repo.add(book_id="BK001", title="Python Programming", author="Guido", genre="Tech")
        repo.add(book_id="BK002", title="Java Basics", author="James", genre="Tech")
        results = repo.search("Python")
        assert len(results) == 1

    def test_count(self, session: Session) -> None:
        repo = BookRepository(session)
        assert repo.count() == 0
        repo.add(book_id="BK001", title="Book", author="A", genre="Fiction")
        assert repo.count() == 1


class TestUserRepository:
    """Test user CRUD operations."""

    def test_add_and_get_user(self, session: Session) -> None:
        repo = UserRepository(session)
        repo.add(user_id="U001", name="Test User", email="test@test.com", password_hash="h")
        user = repo.get("U001")
        assert user is not None
        assert user.name == "Test User"

    def test_get_by_email(self, session: Session) -> None:
        repo = UserRepository(session)
        repo.add(user_id="U001", name="Test", email="test@test.com", password_hash="h")
        user = repo.get_by_email("test@test.com")
        assert user is not None

    def test_list_users(self, session: Session) -> None:
        repo = UserRepository(session)
        repo.add(user_id="U001", name="User 1", email="u1@test.com", password_hash="h")
        repo.add(user_id="U002", name="User 2", email="u2@test.com", password_hash="h")
        users = repo.list_all()
        assert len(users) == 2


class TestTransactionRepository:
    """Test transaction CRUD operations."""

    def test_add_transaction(self, session: Session) -> None:
        # Create required FK references
        session.add(Book(book_id="BK100", title="Tx Book"))
        session.add(User(user_id="U100", name="Tx User", email="tx@test.com", password_hash="h"))
        session.commit()

        repo = TransactionRepository(session)
        repo.add(
            tx_id="TX001",
            book_id="BK100",
            user_id="U100",
            tx_type="issue",
            issue_date=datetime.now().isoformat(),
        )
        txs = repo.list_for_user("U100")
        assert len(txs) == 1
