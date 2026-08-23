"""
library.py - Core library business logic
"""

import uuid
from datetime import datetime, timedelta

from app.config.settings import Config
from app.core.logger import log
from app.jobs.jobs import enqueue_cover_fetch
from app.models.book import Book
from app.models.user import MAX_BORROW_LIMIT, User
from app.storage.storage import Storage

# Email notifications (optional — gracefully skipped if SMTP not configured)
try:
    from app.services.email.email_notifier import notify_overdue as _email_overdue
    from app.services.email.email_notifier import (
        notify_reservation_available as _email_reserve,
    )

    _EMAIL_AVAILABLE = True
except ImportError:
    _EMAIL_AVAILABLE = False

# Reference Config directly for test compatibility
# Use Config.ISSUE_DAYS and Config.FINE_PER_DAY inside methods


def _gen_book_id(books: dict[str, Book]) -> str:
    """Generate a unique book ID in format BK-YYYY-NNNN."""
    year = datetime.now().year
    prefix = f"BK-{year}-"
    existing = [k for k in books if k.startswith(prefix)]
    seq = len(existing) + 1
    while f"{prefix}{seq:04d}" in books:
        seq += 1
    return f"{prefix}{seq:04d}"


class Library:
    """Core library business logic layer."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        # ── Phase 2 wiring: when running on the relational layer, the
        #    transactional core (issue/return/pay_fine) delegates to
        #    db.service.LibraryService — a single DB transaction per operation
        #    (BEGIN IMMEDIATE on SQLite) so concurrent checkouts can never
        #    oversell the last copy. JSON storage keeps the legacy path.
        self._service = None
        try:
            from app.db.storage_adapter import DbStorage

            if isinstance(storage, DbStorage):
                from app.db.service import LibraryService

                self._service = LibraryService()
        except ImportError:
            # db/ package unavailable — fall back to the storage-backed path.
            self._service = None

    # ═══════════════════════════════════════════════════════════
    # BOOK MANAGEMENT
    # ═══════════════════════════════════════════════════════════

    def add_book(
        self,
        title: str,
        author: str,
        isbn: str,
        category: str,
        total_copies: int,
        actor: str = "System",
        fetch_cover_async: bool = True,
    ) -> tuple[bool, str]:
        books = self.storage.load_books()
        # Check duplicate ISBN
        for b in books.values():
            if b.isbn == isbn and not b.is_deleted:
                return False, f"Book with ISBN {isbn} already exists (ID: {b.book_id})"
        book_id = _gen_book_id(books)
        book = Book(
            book_id=book_id,
            title=title,
            author=author,
            isbn=isbn,
            category=category,
            total_copies=total_copies,
            available_copies=total_copies,
        )
        books[book_id] = book
        self.storage.save_books(books)
        log(f"Added book '{title}' by {author}", actor, f"ID:{book_id}")

        # Fetch cover asynchronously (Phase 6): enqueue to RQ when Redis is
        # reachable; otherwise the jobs facade falls back to a BOUNDED thread
        # pool (max COVER_FETCH_WORKERS) — never an unbounded raw thread.
        # self.storage is passed through so the in-process pool path writes
        # to the caller's data store (the RQ path builds its own).
        if fetch_cover_async:
            enqueue_cover_fetch(book_id, title, author, isbn, self.storage)

        return True, book_id

    def update_book(self, book_id: str, **kwargs) -> tuple[bool, str]:
        books = self.storage.load_books()
        book = books.get(book_id)
        if not book or book.is_deleted:
            return False, "Book not found"
        allowed = {"title", "author", "isbn", "category", "total_copies"}
        for k, v in kwargs.items():
            if k in allowed:
                setattr(book, k, v)
        if "total_copies" in kwargs:
            issued = book.total_copies - book.available_copies
            book.available_copies = max(0, kwargs["total_copies"] - issued)
            book.total_copies = kwargs["total_copies"]
        self.storage.save_books(books)
        log(f"Updated book {book_id}", "Admin")
        return True, "Book updated"

    def delete_book(self, book_id: str, actor: str = "Admin") -> tuple[bool, str]:
        books = self.storage.load_books()
        book = books.get(book_id)
        if not book:
            return False, "Book not found"
        if book.total_copies != book.available_copies:
            return False, "Cannot delete: copies are currently issued"
        book.is_deleted = True
        self.storage.save_books(books)
        log(f"Soft-deleted book '{book.title}'", actor, f"ID:{book_id}")
        return True, "Book soft-deleted (marked unavailable)"

    def search_books(
        self,
        query: str = "",
        category: str = "",
        search_by: str = "all",
        available_only: bool = False,
        min_issues: int = 0,
        date_added_after: str = "",
        date_added_before: str = "",
        author_exact: str = "",
        publisher: str = "",
        isbn_exact: str = "",
        sort_by: str = "relevance",
    ) -> list[Book]:
        """
        Search books with advanced filters.

        Args:
            query: Search query string
            category: Filter by category (exact match)
            search_by: Field to search ('all', 'title', 'author', 'isbn')
            available_only: Only show books with available copies
            min_issues: Minimum issue count filter
            date_added_after: ISO date string — only books added after this date
            date_added_before: ISO date string — only books added before this date
            author_exact: Exact author name match
            publisher: Filter by publisher (if available in book data)
            min_rating: Minimum average rating
            isbn_exact: Exact ISBN search
            sort_by: Sort order ('relevance', 'title', 'author', 'newest', 'oldest', 'popular', 'available')
        """
        books = self.storage.load_books()
        results: list[Book] = []
        q = query.lower()
        for b in books.values():
            if b.is_deleted:
                continue

            # Category filter
            if category and b.category.lower() != category.lower():
                continue

            # Availability filter
            if available_only and b.available_copies <= 0:
                continue

            # Min issues filter
            if min_issues > 0 and b.issue_count < min_issues:
                continue

            # Date added filters
            if date_added_after:
                try:
                    if datetime.fromisoformat(b.added_on) < datetime.fromisoformat(
                        date_added_after
                    ):
                        continue
                except:
                    pass
            if date_added_before:
                try:
                    if datetime.fromisoformat(b.added_on) > datetime.fromisoformat(
                        date_added_before
                    ):
                        continue
                except:
                    pass

            # Author exact filter
            if author_exact and b.author.lower() != author_exact.lower():
                continue

            # Publisher filter (use 'publisher' from extended book data if available)
            if publisher:
                pub = getattr(b, "publisher", "")
                if publisher.lower() not in pub.lower():
                    continue

            # ISBN exact filter
            if isbn_exact:
                clean = isbn_exact.replace("-", "").lower()
                if clean not in b.isbn.replace("-", "").lower():
                    continue

            # Query text search
            if q:
                by_title = q in b.title.lower()
                by_author = q in b.author.lower()
                by_isbn = q.replace("-", "") in b.isbn.replace("-", "")
                by_category = q in b.category.lower()
                by_id = q.upper() in b.book_id.upper()
                if (
                    (search_by == "title"
                    and not by_title)
                    or (search_by == "author"
                    and not by_author)
                    or (search_by == "isbn"
                    and not by_isbn)
                    or (search_by == "all"
                    and not any([by_title, by_author, by_isbn, by_category, by_id]))
                ):
                    continue

            results.append(b)

        # Sort results
        if sort_by == "title":
            results.sort(key=lambda b: b.title.lower())
        elif sort_by == "author":
            results.sort(key=lambda b: b.author.lower())
        elif sort_by == "newest":
            results.sort(key=lambda b: b.added_on, reverse=True)
        elif sort_by == "oldest":
            results.sort(key=lambda b: b.added_on)
        elif sort_by == "popular":
            results.sort(key=lambda b: b.issue_count, reverse=True)
        elif sort_by == "available":
            results.sort(key=lambda b: b.available_copies, reverse=True)
        # default: relevance — keep original order (best matches first)

        return results

    def search_users(
        self,
        query: str = "",
        role: str = "",
        status: str = "",
        location: str = "",
        sort_by: str = "name",
    ) -> list[User]:
        """Search users with filters."""
        users = self.storage.load_users()
        q = query.lower().strip()
        results = []
        for u in users.values():
            if q and not (q in u.name.lower() or q in u.user_id.lower() or q in u.email.lower()):
                continue
            if role and u.role.lower() != role.lower():
                continue
            if status and u.membership_status.lower() != status.lower():
                continue
            if location:
                uloc = getattr(u, "location", "").lower()
                if location.lower() not in uloc:
                    continue
            results.append(u)

        if sort_by == "name":
            results.sort(key=lambda u: u.name.lower())
        elif sort_by == "newest":
            results.sort(key=lambda u: u.registered_on, reverse=True)
        elif sort_by == "issues":
            results.sort(key=lambda u: len(u.books_issued), reverse=True)
        elif sort_by == "fine":
            results.sort(key=lambda u: u.unpaid_fine, reverse=True)

        return results

    def get_book(self, book_id: str) -> Book | None:
        return self.storage.load_books().get(book_id)

    # ═══════════════════════════════════════════════════════════
    # USER MANAGEMENT
    # ═══════════════════════════════════════════════════════════

    def register_user(
        self,
        user_id: str,
        name: str,
        email: str,
        phone: str,
        role: str,
        password_hash: str,
        actor: str = "Admin",
    ) -> tuple[bool, str]:
        users = self.storage.load_users()
        if user_id in users:
            return False, "User ID already exists"
        user = User(
            user_id=user_id,
            name=name,
            email=email,
            phone=phone,
            role=role,
            password_hash=password_hash,
        )
        users[user_id] = user
        self.storage.save_users(users)
        log(f"Registered user '{name}' ({role})", actor, f"ID:{user_id}")
        return True, "User registered successfully"

    def get_user(self, user_id: str) -> User | None:
        return self.storage.load_users().get(user_id)

    def block_user(self, user_id: str, actor: str) -> tuple[bool, str]:
        users = self.storage.load_users()
        user = users.get(user_id)
        if not user:
            return False, "User not found"
        user.membership_status = "Blocked"
        self.storage.save_users(users)
        log(f"Blocked user {user_id}", actor)
        return True, "User blocked"

    def unblock_user(self, user_id: str, actor: str) -> tuple[bool, str]:
        users = self.storage.load_users()
        user = users.get(user_id)
        if not user:
            return False, "User not found"
        user.membership_status = "Active"
        self.storage.save_users(users)
        log(f"Unblocked user {user_id}", actor)
        return True, "User unblocked"

    def renew_membership(
        self, user_id: str, days: int = 365, actor: str = "Admin"
    ) -> tuple[bool, str]:
        users = self.storage.load_users()
        user = users.get(user_id)
        if not user:
            return False, "User not found"
        new_expiry = datetime.now() + timedelta(days=days)
        user.membership_expiry = new_expiry.isoformat()
        user.membership_status = "Active"
        self.storage.save_users(users)
        log(
            f"Renewed membership for {user_id} till {new_expiry.strftime('%Y-%m-%d')}",
            actor,
        )
        return True, f"Membership renewed till {new_expiry.strftime('%Y-%m-%d')}"

    # ═══════════════════════════════════════════════════════════
    # ISSUE & RETURN
    # ═══════════════════════════════════════════════════════════

    def issue_book(self, user_id: str, book_id: str, actor: str = "Librarian") -> tuple[bool, str]:
        if self._service is not None:
            return self._service.issue_book(user_id, book_id, actor)
        users = self.storage.load_users()
        books = self.storage.load_books()

        user = users.get(user_id)
        book = books.get(book_id)

        if not user:
            return False, "User not found"
        if not book or book.is_deleted:
            return False, "Book not found"

        # Checks
        if not user.is_active():
            return False, f"User membership is {user.membership_status}"
        if not user.can_borrow():
            return (
                False,
                f"User has reached max borrow limit ({MAX_BORROW_LIMIT} books)",
            )
        if book_id in user.books_issued:
            return False, "User already has this book issued"
        if book.available_copies <= 0:
            # Add to reservation queue instead
            res = self.storage.load_reservations()
            queue = res.get(book_id, [])
            if user_id not in queue:
                queue.append(user_id)
                res[book_id] = queue
                self.storage.save_reservations(res)
                return (
                    False,
                    f"No copies available. User added to reservation queue (position {len(queue)})",
                )
            return False, "No copies available and user already in reservation queue"
        if user.unpaid_fine > 0:
            return (
                False,
                f"User has unpaid fine of ₹{user.unpaid_fine:.2f}. Please clear before issuing.",
            )

        # Issue
        issue_date = datetime.now()
        due_date = issue_date + timedelta(days=Config.ISSUE_DAYS)
        txn = {
            "txn_id": f"TXN-{uuid.uuid4().hex[:16]}",
            "type": "issue",
            "user_id": user_id,
            "book_id": book_id,
            "issue_date": issue_date.isoformat(),
            "due_date": due_date.isoformat(),
            "return_date": None,
            "fine": 0.0,
        }
        self.storage.append_transaction(txn)

        user.books_issued.append(book_id)
        book.available_copies -= 1
        book.issue_count += 1

        self.storage.save_users(users)
        self.storage.save_books(books)
        log(
            f"Issued book '{book.title}' to {user.name}",
            actor,
            f"Due:{due_date.strftime('%Y-%m-%d')}",
        )
        return True, f"Book issued! Due date: {due_date.strftime('%d %b %Y')}"

    def return_book(
        self, user_id: str, book_id: str, actor: str = "Librarian"
    ) -> tuple[bool, str, float]:
        if self._service is not None:
            return self._service.return_book(user_id, book_id, actor)
        users = self.storage.load_users()
        books = self.storage.load_books()

        user = users.get(user_id)
        book = books.get(book_id)

        if not user:
            return False, "User not found", 0
        if not book:
            return False, "Book not found", 0
        if book_id not in user.books_issued:
            return False, "This book is not issued to this user", 0

        # Find the matching open transaction
        txns = self.storage.load_transactions()
        txn = None
        for t in reversed(txns):
            if (
                t["user_id"] == user_id
                and t["book_id"] == book_id
                and t["return_date"] is None
                and t["type"] == "issue"
            ):
                txn = t
                break

        fine = 0.0
        return_date = datetime.now()
        if txn:
            due = datetime.fromisoformat(txn["due_date"])
            if return_date > due:
                days_late = (return_date - due).days
                fine = days_late * Config.FINE_PER_DAY
            txn["return_date"] = return_date.isoformat()
            txn["fine"] = fine
            self.storage.save_transactions(txns)

        # Update user
        user.books_issued.remove(book_id)
        if fine > 0:
            user.unpaid_fine += fine
            # Record fine
            self.storage.append_fine(
                {
                    "user_id": user_id,
                    "book_id": book_id,
                    "fine": fine,
                    "date": return_date.isoformat(),
                    "paid": False,
                }
            )

        # Update book
        book.available_copies = min(book.total_copies, book.available_copies + 1)
        self.storage.save_users(users)
        self.storage.save_books(books)

        # Check reservation queue
        res = self.storage.load_reservations()
        queue = res.get(book_id, [])
        notify_msg = ""
        if queue:
            next_user_id = queue[0]
            next_user = users.get(next_user_id)
            notify_msg = (
                f"\n  📢 NOTIFICATION: '{book.title}' is now available for "
                f"reserved user: {next_user.name if next_user else next_user_id}"
            )
            # Remove the user from the queue
            queue.pop(0)
            if queue:
                res[book_id] = queue
            else:
                del res[book_id]
            self.storage.save_reservations(res)
            # Add notification for the user
            if next_user:
                self.storage.append_notification(
                    {
                        "notif_id": f"NOTIF-{uuid.uuid4().hex[:16]}",
                        "user_id": next_user_id,
                        "type": "reservation_available",
                        "message": f"The book '{book.title}' you reserved is now available!",
                        "created_at": return_date.isoformat(),
                        "read": False,
                    }
                )
                # Send email notification for reservation available
                if _EMAIL_AVAILABLE and next_user.email:
                    _email_reserve(
                        user_email=next_user.email,
                        user_name=next_user.name,
                        book_title=book.title,
                        book_id=book_id,
                    )

        # Send email notification for overdue fine
        if fine > 0 and _EMAIL_AVAILABLE and user.email:
            due_dt = datetime.fromisoformat(txn["due_date"]) if txn else return_date
            days_overdue = (return_date - due_dt).days
            _email_overdue(
                user_email=user.email,
                user_name=user.name,
                book_title=book.title,
                days_overdue=days_overdue,
                accrued_fine=fine,
                due_date=due_dt.strftime("%d %b %Y"),
                book_id=book_id,
            )

        log(f"Returned book '{book.title}' from {user.name}", actor, f"Fine:₹{fine:.2f}")
        msg = f"Book returned. Fine: ₹{fine:.2f}" if fine > 0 else "Book returned successfully."
        return True, msg + notify_msg, fine

    def pay_fine(self, user_id: str, amount: float, actor: str) -> tuple[bool, str]:
        if self._service is not None:
            return self._service.pay_fine(user_id, amount, actor)
        users = self.storage.load_users()
        user = users.get(user_id)
        if not user:
            return False, "User not found"
        if user.unpaid_fine <= 0:
            return False, "No outstanding fine"
        paid = min(amount, user.unpaid_fine)
        user.unpaid_fine -= paid
        # Mark fines as paid
        fines = self.storage.load_fines()
        remaining = paid
        for f in fines:
            if f["user_id"] == user_id and not f["paid"] and remaining > 0:
                if remaining >= f["fine"]:
                    remaining -= f["fine"]
                    f["paid"] = True
                else:
                    f["fine"] -= remaining
                    remaining = 0
        self.storage.save_fines(fines)
        self.storage.save_users(users)
        log(f"Fine payment ₹{paid:.2f} from {user.name}", actor)
        return True, f"₹{paid:.2f} collected. Remaining fine: ₹{user.unpaid_fine:.2f}"

    # ═══════════════════════════════════════════════════════════
    # OVERDUE TRACKING
    # ═══════════════════════════════════════════════════════════

    def get_overdue_list(self) -> list[dict]:
        txns = self.storage.load_transactions()
        users = self.storage.load_users()
        books = self.storage.load_books()
        now = datetime.now()
        overdue: list[dict] = []
        for t in txns:
            if t["return_date"] is not None or t["type"] != "issue":
                continue
            due = datetime.fromisoformat(t["due_date"])
            if now > due:
                days = (now - due).days
                user = users.get(t["user_id"])
                book = books.get(t["book_id"])
                overdue.append(
                    {
                        "user": user.name if user else t["user_id"],
                        "user_id": t["user_id"],
                        "book_id": t["book_id"],
                        "book": book.title if book else t["book_id"],
                        "due_date": due.strftime("%d %b %Y"),
                        "days_overdue": days,
                        "accrued_fine": days * Config.FINE_PER_DAY,
                    }
                )
        return sorted(overdue, key=lambda x: x["days_overdue"], reverse=True)

    # ═══════════════════════════════════════════════════════════
    # REPORTS
    # ═══════════════════════════════════════════════════════════

    def report_most_issued(self, top: int = 10) -> list[dict]:
        books = self.storage.load_books()
        ranked = sorted(
            [b for b in books.values() if not b.is_deleted],
            key=lambda b: b.issue_count,
            reverse=True,
        )
        return [
            {
                "title": b.title,
                "author": b.author,
                "count": b.issue_count,
                "id": b.book_id,
            }
            for b in ranked[:top]
        ]

    def report_active_users(self, top: int = 10) -> list[dict]:
        txns = self.storage.load_transactions()
        users = self.storage.load_users()
        counts: dict[str, int] = {}
        for t in txns:
            if t["type"] == "issue":
                counts[t["user_id"]] = counts.get(t["user_id"], 0) + 1
        ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top]
        result: list[dict] = []
        for uid, cnt in ranked:
            u = users.get(uid)
            result.append({"name": u.name if u else uid, "user_id": uid, "total_issues": cnt})
        return result

    def report_issued_today(self) -> int:
        txns = self.storage.load_transactions()
        today = datetime.now().date()
        return sum(
            1
            for t in txns
            if t["type"] == "issue" and datetime.fromisoformat(t["issue_date"]).date() == today
        )

    def report_issued_this_month(self) -> int:
        txns = self.storage.load_transactions()
        now = datetime.now()
        return sum(
            1
            for t in txns
            if t["type"] == "issue"
            and datetime.fromisoformat(t["issue_date"]).year == now.year
            and datetime.fromisoformat(t["issue_date"]).month == now.month
        )

    def report_fine_collection(self) -> dict:
        fines = self.storage.load_fines()
        total = sum(f["fine"] for f in fines)
        collected = sum(f["fine"] for f in fines if f["paid"])
        pending = total - collected
        return {
            "total": total,
            "collected": collected,
            "pending": pending,
            "count": len(fines),
        }

    def report_category_count(self) -> dict:
        books = self.storage.load_books()
        counts: dict[str, int] = {}
        for b in books.values():
            if not b.is_deleted:
                counts[b.category] = counts.get(b.category, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))
