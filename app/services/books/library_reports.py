"""Report methods for the Library class.

Extracted from library.py for maintainability. Contains all analytics
and reporting methods that read from storage without modifying state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.config.settings import Config


class LibraryReportMixin:
    """Mixin providing report methods for the Library class."""

    storage: Any  # injected by Library

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
