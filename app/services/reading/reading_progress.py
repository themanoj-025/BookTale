"""
reading_progress.py - Bookmarks & Reading Progress Tracking

Features:
- Track current page / chapter for each book
- Reading progress percentage
- Estimated reading time remaining
- Reading history timeline
- Personal bookmarks with notes
"""

import json
import os
import uuid
from datetime import datetime

from app.config.settings import Config
from app.storage.storage import Storage

# Average reading speed: ~250 words/minute, ~1 page per 2 minutes
AVG_MINUTES_PER_PAGE = 2.0
AVG_WORDS_PER_PAGE = 250


def _gen_id(prefix: str = "BM") -> str:
    ts = int(datetime.now().timestamp() * 1000)
    uid = str(uuid.uuid4())[:8]
    return f"{prefix}-{ts}-{uid}"


class ReadingProgress:
    """Manages bookmarks and reading progress for users."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def _load_progress(self) -> dict:
        path = os.path.join(Config.DATA_DIR, "reading_progress.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_progress(self, data: dict) -> None:
        path = os.path.join(Config.DATA_DIR, "reading_progress.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _load_bookmarks(self) -> list:
        path = os.path.join(Config.DATA_DIR, "bookmarks.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_bookmarks(self, bookmarks: list) -> None:
        path = os.path.join(Config.DATA_DIR, "bookmarks.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(bookmarks, f, indent=2)

    # ── Reading Progress ────────────────────────────────────────

    def get_progress(self, user_id: str, book_id: str) -> dict:
        """Get reading progress for a specific book."""
        data = self._load_progress()
        key = f"{user_id}_{book_id}"
        book = self.storage.load_books().get(book_id)

        if key not in data:
            total_pages = book.pages if book and book.pages > 0 else 0
            return {
                "user_id": user_id,
                "book_id": book_id,
                "current_page": 0,
                "total_pages": total_pages,
                "percentage": 0,
                "started": False,
                "finished": False,
                "time_spent_minutes": 0,
                "estimated_minutes_remaining": (
                    total_pages * AVG_MINUTES_PER_PAGE if total_pages else 0
                ),
                "notes": "",
                "updated_at": "",
            }

        entry = data[key]
        total_pages = book.pages if book and book.pages > 0 else entry.get("total_pages", 0)
        current = entry.get("current_page", 0)
        percentage = round(current / total_pages * 100, 1) if total_pages > 0 else 0
        time_spent = entry.get("time_spent_minutes", 0)
        remaining_pages = max(0, total_pages - current)
        est_remaining = remaining_pages * AVG_MINUTES_PER_PAGE

        return {
            **entry,
            "total_pages": total_pages,
            "percentage": percentage,
            "estimated_minutes_remaining": round(est_remaining, 1),
            "time_spent_minutes": time_spent,
        }

    def update_progress(
        self,
        user_id: str,
        book_id: str,
        current_page: int = None,
        time_spent_minutes: int = None,
        notes: str = None,
        finished: bool = None,
    ) -> tuple[bool, str, dict]:
        """Update reading progress for a book."""
        data = self._load_progress()
        key = f"{user_id}_{book_id}"
        book = self.storage.load_books().get(book_id)
        now = datetime.now().isoformat()

        if key not in data:
            total_pages = book.pages if book and book.pages > 0 else 0
            data[key] = {
                "user_id": user_id,
                "book_id": book_id,
                "current_page": 0,
                "total_pages": total_pages,
                "started": True,
                "finished": False,
                "time_spent_minutes": 0,
                "notes": "",
                "started_at": now,
                "updated_at": now,
            }

        if current_page is not None:
            data[key]["current_page"] = max(0, int(current_page))
            data[key]["started"] = True
        if time_spent_minutes is not None:
            data[key]["time_spent_minutes"] = data[key].get("time_spent_minutes", 0) + int(
                time_spent_minutes
            )
        if notes is not None:
            data[key]["notes"] = notes
        if finished is not None:
            data[key]["finished"] = finished
            if finished:
                total_pages = (
                    book.pages if book and book.pages > 0 else data[key].get("total_pages", 0)
                )
                data[key]["current_page"] = total_pages

        # Update total_pages from book if available
        if book and book.pages > 0:
            data[key]["total_pages"] = book.pages

        data[key]["updated_at"] = now
        self._save_progress(data)

        progress = self.get_progress(user_id, book_id)
        status = "finished" if progress.get("finished") else "updated"
        return True, f"Reading progress {status}!", progress

    def mark_as_started(self, user_id: str, book_id: str) -> tuple[bool, str, dict]:
        """Mark a book as started reading."""
        return self.update_progress(user_id, book_id, current_page=1)

    def mark_as_finished(self, user_id: str, book_id: str) -> tuple[bool, str, dict]:
        """Mark a book as finished reading."""
        return self.update_progress(user_id, book_id, finished=True)

    def get_user_reading_list(self, user_id: str) -> dict:
        """Get all reading progress entries for a user."""
        data = self._load_progress()
        books = self.storage.load_books()
        currently_reading = []
        finished = []
        on_hold = []

        for key, entry in data.items():
            parts = key.split("_", 1)
            if len(parts) == 2 and parts[0] == user_id:
                book_id = parts[1]
                book = books.get(book_id)
                # total_pages is required by the progress dict below — derive it
                # from the book or the stored entry (prevents NameError).
                total_pages = book.pages if book and book.pages > 0 else entry.get("total_pages", 0)
                current = entry.get("current_page", 0)
                percentage = round(current / total_pages * 100, 1) if total_pages > 0 else 0
                progress = {
                    **entry,
                    "book_title": book.title if book else "Unknown",
                    "book_author": book.author if book else "",
                    "book_category": book.category if book else "",
                    "percentage": percentage,
                    "total_pages": total_pages,
                }

                if entry.get("finished"):
                    finished.append(progress)
                elif entry.get("current_page", 0) > 0:
                    currently_reading.append(progress)
                else:
                    on_hold.append(progress)

        currently_reading.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        finished.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        on_hold.sort(key=lambda x: x.get("updated_at", ""), reverse=True)

        return {
            "currently_reading": currently_reading,
            "finished": finished,
            "on_hold": on_hold,
            "total_books": len(currently_reading) + len(finished) + len(on_hold),
        }

    # ── Bookmarks ───────────────────────────────────────────────

    def add_bookmark(
        self, user_id: str, book_id: str, page: int, note: str = ""
    ) -> tuple[bool, str, dict | None]:
        """Add a bookmark at a specific page."""
        if page < 1:
            return False, "Page must be at least 1", None
        bookmarks = self._load_bookmarks()
        now = datetime.now().isoformat()
        bm = {
            "bookmark_id": _gen_id("BM"),
            "user_id": user_id,
            "book_id": book_id,
            "page": page,
            "note": note.strip(),
            "created_at": now,
        }
        bookmarks.append(bm)
        self._save_bookmarks(bookmarks)
        return True, "Bookmark added!", bm

    def remove_bookmark(self, bookmark_id: str, user_id: str) -> tuple[bool, str]:
        """Remove a bookmark."""
        bookmarks = self._load_bookmarks()
        for bm in bookmarks:
            if bm["bookmark_id"] == bookmark_id and bm["user_id"] == user_id:
                bookmarks.remove(bm)
                self._save_bookmarks(bookmarks)
                return True, "Bookmark removed!"
        return False, "Bookmark not found"

    def get_book_bookmarks(self, user_id: str, book_id: str) -> list[dict]:
        """Get all bookmarks for a specific book and user."""
        bookmarks = self._load_bookmarks()
        return [bm for bm in bookmarks if bm["user_id"] == user_id and bm["book_id"] == book_id]

    def get_user_bookmarks(self, user_id: str) -> list[dict]:
        """Get all bookmarks for a user."""
        bookmarks = self._load_bookmarks()
        user_bm = [bm for bm in bookmarks if bm["user_id"] == user_id]
        # Enrich with book info
        books = self.storage.load_books()
        for bm in user_bm:
            book = books.get(bm["book_id"])
            bm["book_title"] = book.title if book else "Unknown"
            bm["book_author"] = book.author if book else ""
        user_bm.sort(key=lambda b: b.get("created_at", ""), reverse=True)
        return user_bm

    # ── Reading Stats ───────────────────────────────────────────

    def get_reading_stats(self, user_id: str) -> dict:
        """Get aggregate reading statistics for a user."""
        data = self._load_progress()
        total_time = 0
        total_pages_read = 0
        books_started = 0
        books_finished = 0
        pages_by_month = {}

        for key, entry in data.items():
            parts = key.split("_", 1)
            if len(parts) == 2 and parts[0] == user_id:
                current = entry.get("current_page", 0)
                total_time += entry.get("time_spent_minutes", 0)
                total_pages_read += current
                books_started += 1
                if entry.get("finished"):
                    books_finished += 1
                # Track by month
                try:
                    updated = datetime.fromisoformat(entry.get("updated_at", ""))
                    month_key = updated.strftime("%Y-%m")
                    pages_by_month[month_key] = pages_by_month.get(month_key, 0) + current
                except Exception:
                    pass

        return {
            "total_time_spent_minutes": total_time,
            "total_pages_read": total_pages_read,
            "books_started": books_started,
            "books_finished": books_finished,
            "completion_rate": round(books_finished / max(1, books_started) * 100, 1),
            "pages_by_month": pages_by_month,
            "avg_time_per_book": (
                round(total_time / max(1, books_finished), 1) if books_finished else 0
            ),
        }
