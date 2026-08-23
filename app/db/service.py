"""
db/service.py - Transactional library service layer.

Mirrors the public API of library.Library (issue_book / return_book / reserve /
pay_fine / stats / overdue) but executes every read-modify-write inside a single
DB transaction with row-level locking, so concurrent checkouts cannot oversell
the last copy.

Concurrency strategy:
  - SQLite: every transaction begins with BEGIN IMMEDIATE (engine-level
    event in db/database.py) so writers serialize; the loser's snapshot
    re-reads available_copies=0 after the winner commits and fails cleanly.
  - PostgreSQL: BEGIN IMMEDIATE is not needed; SELECT ... FOR UPDATE row
    locks serialize issuers of the same book inside one transaction.

Note: `with session_factory() as db:` does NOT auto-commit on clean exit
(close() rolls back). Every state-changing method therefore calls db.commit()
explicitly at the point the change must become durable; on exception the
session close() rolls the whole transaction back atomically.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.config.settings import Config
from app.db.database import get_session_factory
from app.db.models import Book, Fine, Notification, Reservation, Transaction, User
from app.db.repositories import (
    BookRepository,
    TransactionRepository,
    UserRepository,
    library_stats,
)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


class LibraryService:
    """DB-backed business logic. Same method signatures as library.Library."""

    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory or get_session_factory()

    # ═══════════════════════════════════════════════════════════
    # ISSUE / RETURN / RESERVE  (transactional core)
    # ═══════════════════════════════════════════════════════════

    def issue_book(self, user_id: str, book_id: str, actor: str = "Librarian") -> tuple[bool, str]:
        """Check out a book atomically. Returns (ok, message).

        Exactly one concurrent caller can take the last available copy; the
        losers get a clean 'No copies available' error instead of overselling.
        """
        with self._session_factory() as db:
            user = db.get(User, user_id)
            book = db.execute(
                select(Book)
                .where(Book.book_id == book_id, Book.is_deleted.is_(False))
                .with_for_update()
            ).scalar_one_or_none()

            if user is None:
                return False, "User not found"
            if book is None:
                return False, "Book not found"
            if user.membership_status.lower() != "active":
                return False, f"User membership is {user.membership_status}"
            if len(user.books_issued or []) >= Config.MAX_BORROW_LIMIT:
                return False, (
                    f"User has reached max borrow limit " f"({Config.MAX_BORROW_LIMIT} books)"
                )
            if book_id in (user.books_issued or []):
                return False, "User already has this book issued"
            if user.unpaid_fine > 0:
                return False, (
                    f"User has unpaid fine of ₹{user.unpaid_fine:.2f}. "
                    f"Please clear before issuing."
                )
            if book.available_copies <= 0:
                return self._enqueue_reservation(db, user_id, book_id, book)

            # Issue: decrement copy + record txn + update user, then COMMIT.
            issue_date = datetime.now()
            due_date = issue_date + timedelta(days=Config.ISSUE_DAYS)
            book.available_copies -= 1
            book.issue_count += 1
            user.books_issued = [*list(user.books_issued or []), book_id]
            db.add(
                Transaction(
                    txn_id=_new_id("TXN"),
                    type="issue",
                    user_id=user_id,
                    book_id=book_id,
                    issue_date=issue_date.isoformat(),
                    due_date=due_date.isoformat(),
                    return_date=None,
                    fine=0.0,
                )
            )
            db.commit()  # durable now; any earlier exception rolls back instead
            return True, f"Book issued! Due date: {due_date.strftime('%d %b %Y')}"

    def return_book(
        self, user_id: str, book_id: str, actor: str = "Librarian"
    ) -> tuple[bool, str, float]:
        """Return a book atomically: close txn, restore copy, apply fine,
        notify the next reservation in queue — all or nothing."""
        with self._session_factory() as db:
            user = db.get(User, user_id)
            book = db.execute(
                select(Book).where(Book.book_id == book_id).with_for_update()
            ).scalar_one_or_none()

            if user is None:
                return False, "User not found", 0.0
            if book is None:
                return False, "Book not found", 0.0
            if book_id not in (user.books_issued or []):
                return False, "This book is not issued to this user", 0.0

            txn = db.scalar(
                select(Transaction)
                .where(
                    Transaction.user_id == user_id,
                    Transaction.book_id == book_id,
                    Transaction.return_date.is_(None),
                    Transaction.type == "issue",
                )
                .order_by(Transaction.issue_date.desc())
                .with_for_update()
                .limit(1)
            )

            return_date = datetime.now()
            fine = 0.0
            if txn is not None:
                due = datetime.fromisoformat(txn.due_date)
                if return_date > due:
                    fine = (return_date - due).days * Config.FINE_PER_DAY
                txn.return_date = return_date.isoformat()
                txn.fine = fine

            user.books_issued = [b for b in (user.books_issued or []) if b != book_id]
            if fine > 0:
                user.unpaid_fine = float(user.unpaid_fine or 0.0) + fine
                db.add(
                    Fine(
                        user_id=user_id,
                        book_id=book_id,
                        fine=fine,
                        date=return_date.isoformat(),
                        paid=False,
                    )
                )

            book.available_copies = min(book.total_copies, book.available_copies + 1)

            # Notify next reserved user (atomically with the return).
            notify_msg = self._pop_reservation_queue(db, book_id, book, return_date, user)
            db.commit()
            return True, f"Book returned. Fine: ₹{fine:.2f}" + notify_msg, fine

    def reserve_book(
        self, user_id: str, book_id: str, actor: str = "Librarian"
    ) -> tuple[bool, str]:
        """Add a user to a book's reservation queue (idempotent)."""
        with self._session_factory() as db:
            book = db.execute(
                select(Book).where(Book.book_id == book_id).with_for_update()
            ).scalar_one_or_none()
            if book is None:
                return False, "Book not found"
            return self._enqueue_reservation(db, user_id, book_id, book)

    # ═══════════════════════════════════════════════════════════
    # FINE PAYMENT
    # ═══════════════════════════════════════════════════════════

    def pay_fine(self, user_id: str, amount: float, actor: str = "Admin") -> tuple[bool, str]:
        with self._session_factory() as db:
            user = db.get(User, user_id)
            if user is None:
                return False, "User not found"
            if user.unpaid_fine <= 0:
                return False, "No outstanding fine"
            paid = min(amount, user.unpaid_fine)
            user.unpaid_fine = round(float(user.unpaid_fine) - paid, 2)
            fines = db.scalars(
                select(Fine).where(Fine.user_id == user_id, Fine.paid.is_(False)).with_for_update()
            ).all()
            remaining = paid
            for f in fines:
                if remaining <= 0:
                    break
                if remaining >= f.fine:
                    remaining -= f.fine
                    f.paid = True
                else:
                    f.fine -= remaining
                    remaining = 0
            db.commit()
            return True, (f"₹{paid:.2f} collected. Remaining fine: ₹{user.unpaid_fine:.2f}")

    # ═══════════════════════════════════════════════════════════
    # READS (delegated to indexed repositories)
    # ═══════════════════════════════════════════════════════════

    def get_overdue_list(self) -> list[dict]:
        with self._session_factory() as db:
            return TransactionRepository(db).get_overdue_list()

    def library_stats(self) -> dict:
        with self._session_factory() as db:
            return library_stats(db)

    def search_books(self, **kwargs) -> list[Book]:
        with self._session_factory() as db:
            return BookRepository(db).search(**kwargs)

    def search_users(self, **kwargs) -> list[User]:
        with self._session_factory() as db:
            return UserRepository(db).search(**kwargs)

    def book_count(self) -> int:
        with self._session_factory() as db:
            return BookRepository(db).count()

    # ═══════════════════════════════════════════════════════════
    # INTERNAL HELPERS
    # ═══════════════════════════════════════════════════════════

    def _enqueue_reservation(self, db, user_id: str, book_id: str, book: Book) -> tuple[bool, str]:
        """Add user to the reservation queue; commits its own write so the
        queue entry survives even though the issue itself is declined."""
        existing = db.scalar(
            select(Reservation).where(
                Reservation.book_id == book_id, Reservation.user_id == user_id
            )
        )
        if existing is not None:
            return False, "No copies available and user already in reservation queue"
        max_pos = (
            db.scalar(select(func.max(Reservation.position)).where(Reservation.book_id == book_id))
            or 0
        )
        db.add(
            Reservation(
                book_id=book_id,
                user_id=user_id,
                position=int(max_pos) + 1,
                created_at=datetime.now().isoformat(),
            )
        )
        db.commit()
        return False, (
            f"No copies available. User added to reservation queue "
            f"(position {int(max_pos) + 1})"
        )

    def _pop_reservation_queue(
        self, db, book_id: str, book: Book, when: datetime, returning_user: User
    ) -> str:
        """Serve the next reservation, notifying that user. Returns message."""
        next_res = db.scalar(
            select(Reservation)
            .where(Reservation.book_id == book_id)
            .order_by(Reservation.position.asc())
            .with_for_update()
            .limit(1)
        )
        if next_res is None:
            return ""
        next_user = db.get(User, next_res.user_id)
        db.delete(next_res)
        if next_user is None:
            return ""
        db.add(
            Notification(
                notif_id=_new_id("NOTIF"),
                user_id=next_user.user_id,
                type="reservation_available",
                message=f"The book '{book.title}' you reserved is now available!",
                created_at=when.isoformat(),
                read=False,
            )
        )
        return (
            f"\n  📢 NOTIFICATION: '{book.title}' is now available for "
            f"reserved user: {next_user.name}"
        )
