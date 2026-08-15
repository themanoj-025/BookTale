"""
series.py - Book Series Management

Features:
- Group books into series/collections
- Track series order and volume numbers
- Series detail pages with all books
- API endpoints for series CRUD
"""

import json
import os
import uuid
from datetime import datetime

from app.config.settings import Config
from app.core.logger import log
from app.storage.storage import Storage


def _gen_id(prefix: str = "SER") -> str:
    ts = int(datetime.now().timestamp() * 1000)
    uid = str(uuid.uuid4())[:8]
    return f"{prefix}-{ts}-{uid}"


class SeriesManager:
    """Manages book series/collections."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def _get_series_path(self) -> str:
        return os.path.join(Config.DATA_DIR, "series.json")

    def _load_series(self) -> list:
        path = self._get_series_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_series(self, series_list: list) -> None:
        path = self._get_series_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(series_list, f, indent=2)

    def create_series(
        self, name: str, description: str = "", category: str = "", created_by: str = ""
    ) -> tuple[bool, str, dict | None]:
        """Create a new book series."""
        if not name.strip():
            return False, "Series name cannot be empty", None
        series_list = self._load_series()
        now = datetime.now().isoformat()
        series = {
            "series_id": _gen_id("SER"),
            "name": name.strip(),
            "description": description.strip(),
            "category": category,
            "book_count": 0,
            "total_books": 0,  # planned total books in series
            "author": "",
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
        }
        series_list.append(series)
        self._save_series(series_list)
        log(f"Created series '{name}'", created_by)
        return True, "Series created!", series

    def get_series(self, series_id: str) -> dict | None:
        series_list = self._load_series()
        for s in series_list:
            if s["series_id"] == series_id:
                return s
        return None

    def update_series(
        self,
        series_id: str,
        name: str = None,
        description: str = None,
        category: str = None,
        total_books: int = None,
    ) -> tuple[bool, str]:
        series_list = self._load_series()
        for s in series_list:
            if s["series_id"] == series_id:
                if name is not None:
                    s["name"] = name.strip()
                if description is not None:
                    s["description"] = description.strip()
                if category is not None:
                    s["category"] = category
                if total_books is not None:
                    s["total_books"] = total_books
                s["updated_at"] = datetime.now().isoformat()
                self._save_series(series_list)
                return True, "Series updated!"
        return False, "Series not found"

    def delete_series(self, series_id: str) -> tuple[bool, str]:
        series_list = self._load_series()
        for s in series_list:
            if s["series_id"] == series_id:
                series_list.remove(s)
                self._save_series(series_list)
                # Also remove series_name from all books in this series
                books = self.storage.load_books()
                changed = False
                for b in books.values():
                    if b.series_name == s["name"]:
                        b.series_name = ""
                        b.series_order = 0
                        changed = True
                if changed:
                    self.storage.save_books(books)
                return True, "Series deleted!"
        return False, "Series not found"

    def get_all_series(self, page: int = 1, per_page: int = 20) -> tuple[list[dict], int]:
        series_list = self._load_series()
        # Recalculate book counts
        books = self.storage.load_books()
        for s in series_list:
            s["book_count"] = sum(
                1 for b in books.values() if not b.is_deleted and b.series_name == s["name"]
            )
        series_list.sort(key=lambda s: s.get("book_count", 0), reverse=True)
        total = len(series_list)
        start = (page - 1) * per_page
        end = start + per_page
        return series_list[start:end], total

    def get_series_by_name(self, series_name: str) -> dict | None:
        """Get a series by its exact name."""
        series_list = self._load_series()
        for s in series_list:
            if s["name"].lower() == series_name.lower():
                return s
        return None

    def get_series_books(self, series_name: str) -> list[dict]:
        """Get all books in a series, sorted by series_order."""
        books = self.storage.load_books()
        matches = [
            b
            for b in books.values()
            if not b.is_deleted and b.series_name.lower() == series_name.lower()
        ]
        matches.sort(key=lambda b: b.series_order if b.series_order else 999)
        return [b.to_dict() for b in matches]

    def search_series(self, query: str) -> list[dict]:
        """Search series by name."""
        q = query.lower()
        series_list = self._load_series()
        result = [
            s
            for s in series_list
            if q in s["name"].lower() or q in s.get("description", "").lower()
        ]
        return result[:20]

    def get_series_suggestions(self, query: str) -> list[str]:
        """Get series name autocomplete suggestions."""
        q = query.lower()
        series_list = self._load_series()
        names = set()
        for s in series_list:
            if q in s["name"].lower():
                names.add(s["name"])
        # Also get series names directly from books
        books = self.storage.load_books()
        for b in books.values():
            if b.series_name and q in b.series_name.lower():
                names.add(b.series_name)
        return sorted(names)[:10]

    def get_books_without_series(self) -> list[dict]:
        """Get books not assigned to any series."""
        books = self.storage.load_books()
        return [b.to_dict() for b in books.values() if not b.is_deleted and not b.series_name]
