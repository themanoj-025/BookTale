"""
db/repositories.py - Indexed data-access layer.

Replaces the O(n) full-file JSON scans (storage.load_* -> Python loops) with
SQL queries that hit the indexes defined in db/models.py. Every list endpoint
gets real LIMIT/OFFSET pagination instead of "load everything, slice in Python".
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.config.settings import Config
from app.db.models import Book, Fine, Transaction, User


def _parse_dt(value: str | None) -> datetime | None:
    """Tolerant ISO/legacy date parser.

    The legacy JSON layer wrote dates in several formats (ISO 8601 from
    datetime.isoformat() and human "%d %b %Y" in older exports). The migration
    copies them verbatim, so consumers must not crash on non-ISO values.
    Returns None for unparseable values so callers can skip the row instead of
    500ing the page.
    """
    if not value:
        return None
    for fmt in (None, "%d %b %Y", "%Y-%m-%d"):
        try:
            dt = (
                datetime.fromisoformat(value)
                if fmt is None
                else datetime.strptime(value, fmt)
            )
            # Normalize to naive so comparisons against datetime.now() (naive)
            # never raise TypeError on tz-aware legacy values.
            return dt.replace(tzinfo=None)
        except ValueError:
            continue
    return None


def paginate(query: Select, page: int = 1, per_page: int = 20) -> Select:
    """Apply LIMIT/OFFSET pagination to a select statement."""
    page = max(1, page)
    per_page = min(max(1, per_page), 100)
    return query.limit(per_page).offset((page - 1) * per_page)


class BookRepository:
    """Indexed book queries (search, filters, stats)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, book_id: str) -> Book | None:
        return self.db.get(Book, book_id)

    def search(
        self,
        query: str = "",
        category: str = "",
        available_only: bool = False,
        min_issues: int = 0,
        author_exact: str = "",
        publisher: str = "",
        isbn_exact: str = "",
        sort_by: str = "relevance",
        page: int = 1,
        per_page: int = 20,
    ) -> list[Book]:
        """Indexed search with the same filters as Library.search_books."""
        stmt = select(Book).where(Book.is_deleted.is_(False))

        if category:
            stmt = stmt.where(func.lower(Book.category) == category.lower())
        if available_only:
            stmt = stmt.where(Book.available_copies > 0)
        if min_issues > 0:
            stmt = stmt.where(Book.issue_count >= min_issues)
        if author_exact:
            stmt = stmt.where(func.lower(Book.author) == author_exact.lower())
        if publisher:
            stmt = stmt.where(func.lower(Book.publisher).contains(publisher.lower()))
        if isbn_exact:
            clean = isbn_exact.replace("-", "").lower()
            stmt = stmt.where(func.replace(func.lower(Book.isbn), "-", "") == clean)

        q = query.strip().lower()
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(
                    func.lower(Book.title).like(like),
                    func.lower(Book.author).like(like),
                    func.lower(Book.isbn).like(like),
                    func.lower(Book.category).like(like),
                    Book.book_id.ilike(like),
                )
            )

        # ORDER BY (indexed where possible; relevance keeps natural order)
        if sort_by == "title":
            stmt = stmt.order_by(Book.title.asc())
        elif sort_by == "author":
            stmt = stmt.order_by(Book.author.asc())
        elif sort_by == "newest":
            stmt = stmt.order_by(Book.added_on.desc())
        elif sort_by == "oldest":
            stmt = stmt.order_by(Book.added_on.asc())
        elif sort_by == "popular":
            stmt = stmt.order_by(Book.issue_count.desc())
        elif sort_by == "available":
            stmt = stmt.order_by(Book.available_copies.desc())

        return list(self.db.scalars(paginate(stmt, page, per_page)).all())

    def count(self, category: str = "", available_only: bool = False) -> int:
        stmt = select(func.count(Book.book_id)).where(Book.is_deleted.is_(False))
        if category:
            stmt = stmt.where(Book.category == category)
        if available_only:
            stmt = stmt.where(Book.available_copies > 0)
        return int(self.db.scalar(stmt) or 0)

    def category_counts(self) -> dict[str, int]:
        rows = self.db.execute(
            select(Book.category, func.count(Book.book_id))
            .where(Book.is_deleted.is_(False))
            .group_by(Book.category)
            .order_by(func.count(Book.book_id).desc())
        ).all()
        return {cat: cnt for cat, cnt in rows}

    def most_issued(self, top: int = 10) -> list[dict]:
        rows = (
            self.db.execute(
                select(Book)
                .where(Book.is_deleted.is_(False))
                .order_by(Book.issue_count.desc())
                .limit(top)
            )
            .scalars()
            .all()
        )
        return [
            {
                "title": b.title,
                "author": b.author,
                "count": b.issue_count,
                "id": b.book_id,
            }
            for b in rows
        ]


class UserRepository:
    """Indexed user queries."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, user_id: str) -> User | None:
        return self.db.get(User, user_id)

    def search(
        self,
        query: str = "",
        role: str = "",
        status: str = "",
        page: int = 1,
        per_page: int = 20,
    ) -> list[User]:
        stmt = select(User)
        q = query.strip().lower()
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(
                    func.lower(User.name).like(like),
                    func.lower(User.user_id).like(like),
                    func.lower(User.email).like(like),
                )
            )
        if role:
            stmt = stmt.where(func.lower(User.role) == role.lower())
        if status:
            stmt = stmt.where(func.lower(User.membership_status) == status.lower())
        stmt = stmt.order_by(User.name.asc())
        return list(self.db.scalars(paginate(stmt, page, per_page)).all())

    def count(self, role: str = "", status: str = "") -> int:
        stmt = select(func.count(User.user_id))
        if role:
            stmt = stmt.where(User.role == role)
        if status:
            stmt = stmt.where(User.membership_status == status)
        return int(self.db.scalar(stmt) or 0)


class TransactionRepository:
    """Indexed transaction queries — overdue list, stats, reports."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_overdue_list(self) -> list[dict]:
        """Open issues whose due_date is in the past, joined with user/book names.

        Uses the ix_txns_open_due index to narrow to open issues only (SQL
        cannot compare mixed date formats lexicographically, so the actual
        overdue check happens in Python with the tolerant parser).
        """
        now = datetime.now()
        rows = self.db.execute(
            select(Transaction, User.name, Book.title)
            .join(User, User.user_id == Transaction.user_id)
            .outerjoin(Book, Book.book_id == Transaction.book_id)
            .where(Transaction.return_date.is_(None), Transaction.type == "issue")
            .order_by(Transaction.due_date.asc())
        ).all()

        overdue = []
        for txn, user_name, book_title in rows:
            due = _parse_dt(txn.due_date)
            # `due >= now` intentionally excludes a same-day-midnight due date
            # (legacy `now > due` counted it overdue at 0 days) — a book is
            # overdue only once its due day has fully passed.
            if due is None or due >= now:
                continue  # legacy/unparseable or not-yet-due — skip
            days = (now - due).days
            overdue.append(
                {
                    "user": user_name or txn.user_id,
                    "user_id": txn.user_id,
                    "book_id": txn.book_id,
                    "book": book_title or txn.book_id,
                    "due_date": due.strftime("%d %b %Y"),
                    "days_overdue": days,
                    "accrued_fine": days * Config.FINE_PER_DAY,
                }
            )
        return sorted(overdue, key=lambda x: x["days_overdue"], reverse=True)

    def active_loans_for_user(self, user_id: str) -> list[Transaction]:
        stmt = select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.return_date.is_(None),
            Transaction.type == "issue",
        )
        return list(self.db.scalars(stmt).all())

    def open_txn_for(self, user_id: str, book_id: str) -> Transaction | None:
        return self.db.scalar(
            select(Transaction)
            .where(
                Transaction.user_id == user_id,
                Transaction.book_id == book_id,
                Transaction.return_date.is_(None),
                Transaction.type == "issue",
            )
            .order_by(Transaction.issue_date.desc())
            .limit(1)
        )

    def counts(self) -> dict:
        total = int(self.db.scalar(select(func.count(Transaction.txn_id))) or 0)
        open_issues = int(
            self.db.scalar(
                select(func.count(Transaction.txn_id)).where(
                    Transaction.return_date.is_(None), Transaction.type == "issue"
                )
            )
            or 0
        )
        return {"total": total, "open_issues": open_issues}

    def issued_today(self) -> int:
        today = datetime.now().date().isoformat()
        return int(
            self.db.scalar(
                select(func.count(Transaction.txn_id)).where(
                    Transaction.type == "issue",
                    func.substr(Transaction.issue_date, 1, 10) == today,
                )
            )
            or 0
        )

    def issued_this_month(self) -> int:
        now = datetime.now()
        prefix = now.strftime("%Y-%m")
        return int(
            self.db.scalar(
                select(func.count(Transaction.txn_id)).where(
                    Transaction.type == "issue",
                    func.substr(Transaction.issue_date, 1, 7) == prefix,
                )
            )
            or 0
        )

    def unique_borrowers(self) -> int:
        return int(
            self.db.scalar(
                select(func.count(func.distinct(Transaction.user_id))).where(
                    Transaction.type == "issue"
                )
            )
            or 0
        )


class FineRepository:
    """Indexed fine queries."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def collection(self) -> dict:
        total = float(
            self.db.scalar(select(func.coalesce(func.sum(Fine.fine), 0.0))) or 0
        )
        collected = float(
            self.db.scalar(
                select(func.coalesce(func.sum(Fine.fine), 0.0)).where(
                    Fine.paid.is_(True)
                )
            )
            or 0
        )
        pending = total - collected
        return {
            "total": total,
            "collected": collected,
            "pending": pending,
            "count": int(self.db.scalar(select(func.count(Fine.id))) or 0),
        }


class AuditLogRepository:
    """Append-only admin audit trail queries (searchable admin UI)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def add(
        self,
        admin_id: str,
        action: str,
        target: str = "",
        old_value: str | None = None,
        new_value: str | None = None,
        ip_address: str = "",
        user_agent: str = "",
    ) -> None:
        """Insert one audit row (plain INSERT; never updated or deleted)."""
        from app.db.models import AuditLog

        self.db.add(
            AuditLog(
                admin_id=admin_id,
                action=action,
                target=target,
                old_value=old_value,
                new_value=new_value,
                ip_address=(ip_address or "")[:64],
                user_agent=(user_agent or "")[:255],
            )
        )

    def search(
        self,
        query: str = "",
        admin_id: str = "",
        action: str = "",
        page: int = 1,
        per_page: int = 20,
    ) -> list:
        """Filtered, paginated audit rows, newest first (indexed)."""
        from app.db.models import AuditLog

        stmt = select(AuditLog)
        q = query.strip().lower()
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(
                    AuditLog.admin_id.ilike(like),
                    AuditLog.target.ilike(like),
                    AuditLog.action.ilike(like),
                    AuditLog.ip_address.ilike(like),
                    AuditLog.new_value.ilike(like),
                    AuditLog.old_value.ilike(like),
                )
            )
        if admin_id:
            stmt = stmt.where(AuditLog.admin_id == admin_id)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        stmt = stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        return [
            self._plain(r)
            for r in self.db.scalars(paginate(stmt, page, per_page)).all()
        ]

    def count(self, query: str = "", admin_id: str = "", action: str = "") -> int:
        from app.db.models import AuditLog

        stmt = select(func.count(AuditLog.id))
        q = query.strip().lower()
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(
                    AuditLog.admin_id.ilike(like),
                    AuditLog.target.ilike(like),
                    AuditLog.action.ilike(like),
                    AuditLog.ip_address.ilike(like),
                    AuditLog.new_value.ilike(like),
                    AuditLog.old_value.ilike(like),
                )
            )
        if admin_id:
            stmt = stmt.where(AuditLog.admin_id == admin_id)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        return int(self.db.scalar(stmt) or 0)

    def _plain(self, row) -> dict:
        return {
            "id": row.id,
            "admin_id": row.admin_id,
            "action": row.action,
            "target": row.target,
            "old_value": row.old_value,
            "new_value": row.new_value,
            "ip_address": row.ip_address,
            "user_agent": row.user_agent,
            "created_at": row.created_at,
        }


def library_stats(db: Session) -> dict:
    """One-shot aggregate query replacing the multi-file _library_stats() scan."""
    books = BookRepository(db)
    txns = TransactionRepository(db)
    users = UserRepository(db)
    fines = FineRepository(db)

    total_books = books.count()
    avail_copies = int(
        db.scalar(
            select(func.coalesce(func.sum(Book.available_copies), 0)).where(
                Book.is_deleted.is_(False)
            )
        )
        or 0
    )
    total_copies = int(
        db.scalar(
            select(func.coalesce(func.sum(Book.total_copies), 0)).where(
                Book.is_deleted.is_(False)
            )
        )
        or 0
    )
    issued_copies = total_copies - avail_copies

    month_start = datetime.now().replace(day=1).isoformat()
    new_books_month = int(
        db.scalar(
            select(func.count(Book.book_id)).where(
                Book.is_deleted.is_(False), Book.added_on >= month_start
            )
        )
        or 0
    )

    txn_counts = txns.counts()
    total_users = users.count()
    active_users = users.count(status="Active")
    blocked_users = users.count(status="Blocked")
    unique_borrowers = txns.unique_borrowers()
    fine_stats = fines.collection()

    return {
        "total_books": total_books,
        "total_copies": total_copies,
        "avail_copies": avail_copies,
        "issued_copies": issued_copies,
        "avail_rate": round(avail_copies / total_copies * 100, 1)
        if total_copies
        else 0,
        "new_books_month": new_books_month,
        "total_users": total_users,
        "active_users": active_users,
        "blocked_users": blocked_users,
        "new_users_month": int(
            db.scalar(
                select(func.count(User.user_id)).where(
                    User.registered_on >= month_start
                )
            )
            or 0
        ),
        "total_issues": txn_counts["total"],
        "active_issues": txn_counts["open_issues"],
        "total_txns": txn_counts["total"],
        "month_txns": txns.issued_this_month(),
        "unique_borrowers": unique_borrowers,
        "avg_books_per_user": round(txn_counts["total"] / total_users, 1)
        if total_users
        else 0,
        "total_fines": round(fine_stats["total"], 2),
        "paid_fines": round(fine_stats["collected"], 2),
        "pending_fines": round(fine_stats["pending"], 2),
    }
