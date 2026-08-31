"""Comprehensive tests for Book-Tale ORM models.

Tests model creation, relationships, and default values.
"""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import Book, User, Transaction, Fine, Notification, Reservation




pytestmark = pytest.mark.slow
@pytest.fixture
def engine() -> None:
    """Create an in-memory SQLite engine."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine) -> None:
    """Create a database session."""
    with Session(engine) as session:
        yield session


class TestBookModel:
    """Test Book ORM model."""

    def test_create_book(self, session: Session) -> None:
        book = Book(
            book_id="BOOK001",
            title="Test Book",
            author="Test Author",
            genre="Fiction",
            available_copies=3,
            total_copies=3,
        )
        session.add(book)
        session.commit()
        assert book.book_id == "BOOK001"

    def test_book_defaults(self, session: Session) -> None:
        book = Book(book_id="BOOK002", title="Default Test")
        session.add(book)
        session.commit()
        assert book.available_copies == 0
        assert book.total_copies == 0


class TestUserModel:
    """Test User ORM model."""

    def test_create_user(self, session: Session) -> None:
        user = User(
            user_id="USER001",
            name="Test User",
            email="test@example.com",
            password_hash="hashed_pw",
            role="user",
        )
        session.add(user)
        session.commit()
        assert user.user_id == "USER001"

    def test_user_role_default(self, session: Session) -> None:
        user = User(
            user_id="USER002",
            name="No Role",
            email="norole@example.com",
            password_hash="hashed",
        )
        session.add(user)
        session.commit()
        assert user.role == "user"


class TestTransactionModel:
    """Test Transaction ORM model."""

    def test_create_transaction(self, session: Session) -> None:
        book = Book(book_id="BOOK100", title="Transaction Test")
        user = User(user_id="USER100", name="Tx User", email="tx@test.com", password_hash="h")
        session.add_all([book, user])
        session.commit()

        tx = Transaction(
            tx_id="TX001",
            book_id="BOOK100",
            user_id="USER100",
            tx_type="issue",
            issue_date=datetime.now().isoformat(),
        )
        session.add(tx)
        session.commit()
        assert tx.tx_id == "TX001"


class TestFineModel:
    """Test Fine ORM model."""

    def test_create_fine(self, session: Session) -> None:
        user = User(user_id="USER200", name="Fine User", email="fine@test.com", password_hash="h")
        session.add(user)
        session.commit()

        fine = Fine(
            fine_id="FINE001",
            user_id="USER200",
            amount=50.0,
            reason="Late return",
            paid=False,
        )
        session.add(fine)
        session.commit()
        assert fine.paid is False


class TestNotificationModel:
    """Test Notification ORM model."""

    def test_create_notification(self, session: Session) -> None:
        user = User(user_id="USER300", name="Notif User", email="notif@test.com", password_hash="h")
        session.add(user)
        session.commit()

        notif = Notification(
            notif_id="NOTIF001",
            user_id="USER300",
            message="Test notification",
            read=False,
        )
        session.add(notif)
        session.commit()
        assert notif.read is False


class TestReservationModel:
    """Test Reservation ORM model."""

    def test_create_reservation(self, session: Session) -> None:
        book = Book(book_id="BOOK300", title="Reservation Test")
        user = User(user_id="USER400", name="Res User", email="res@test.com", password_hash="h")
        session.add_all([book, user])
        session.commit()

        res = Reservation(
            res_id="RES001",
            book_id="BOOK300",
            user_id="USER400",
            status="pending",
        )
        session.add(res)
        session.commit()
        assert res.status == "pending"
