"""
diary.py — Reading Diary & Custom Rating System

Manages diary entries for books users have read, with:
- Custom rating labels (perfection/worth_it/timepass/skip)
- Star ratings (1-5) for backward compatibility
- Vibe tags, spoiler tags, reread tracking
- Statistics aggregation
"""

import json
import os
import uuid
from collections import Counter
from datetime import date, datetime

import app.storage.storage as storage_lib
from app.core.logger import log
from app.storage.storage import Storage

RATING_LABELS = {
    "perfection": {
        "emoji": "📖",
        "label": "Perfection",
        "color": "#059669",
        "bg": "rgba(16,185,129,0.12)",
    },
    "worth_it": {
        "emoji": "☕",
        "label": "Worth the Read",
        "color": "#4f46e5",
        "bg": "rgba(79,70,229,0.12)",
    },
    "timepass": {
        "emoji": "⌛",
        "label": "Timepass",
        "color": "#d97706",
        "bg": "rgba(245,158,11,0.12)",
    },
    "skip": {
        "emoji": "❌",
        "label": "Skip It",
        "color": "#dc2626",
        "bg": "rgba(239,68,68,0.12)",
    },
}

RATING_SCORES = {"perfection": 4, "worth_it": 3, "timepass": 2, "skip": 1}

DIARY_FILE = "diary.json"


def _gen_id() -> str:
    return f"DIARY-{int(datetime.now().timestamp() * 1000000)}-{uuid.uuid4().hex[:6]}"


def _load_diary(storage: Storage) -> list:
    path = os.path.join(storage_lib.Config.DATA_DIR, DIARY_FILE)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_diary(storage: Storage, entries: list) -> None:
    path = os.path.join(storage_lib.Config.DATA_DIR, DIARY_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)


def rating_badge_html(rating_label: str) -> str:
    """Render a rating label as an HTML badge."""
    info = RATING_LABELS.get(rating_label, RATING_LABELS["timepass"])
    return (
        f'<span class="bt-rating-badge bt-rating-{rating_label}" '
        f'style="background:{info["bg"]};color:{info["color"]};">'
        f"{info['emoji']} {info['label']}</span>"
    )


def star_rating_html(star_rating: int | None) -> str:
    """Render star rating 1-5 as HTML stars."""
    if not star_rating:
        return ""
    filled = "★" * star_rating
    empty = "☆" * (5 - star_rating)
    color = "#f59e0b"
    return f'<span style="color:{color};">{filled}{empty}</span>'


class DiaryManager:
    """Manages reading diary entries."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    # ═══════════════════════════════════════════════════════════════
    # CRUD OPERATIONS
    # ═══════════════════════════════════════════════════════════════

    def log_read(
        self,
        user_id: str,
        book_id: str,
        date_read: str = "",
        rating_label: str = "worth_it",
        star_rating: int | None = None,
        diary_text: str = "",
        is_reread: bool = False,
        spoiler: bool = False,
        vibe_tags: list[str] | None = None,
    ) -> tuple[bool, str, dict | None]:
        """Log a book as read."""
        # Validate
        if rating_label not in RATING_LABELS:
            return (
                False,
                f"Invalid rating label. Choose from: {', '.join(RATING_LABELS.keys())}",
                None,
            )

        books = self.storage.load_books()
        if book_id not in books:
            return False, "Book not found", None

        # Check for duplicate entry (user + book on same date or without date)
        entries = _load_diary(self.storage)
        for e in entries:
            if e["user_id"] == user_id and e["book_id"] == book_id:
                if not date_read or e.get("date_read", "") == date_read:
                    # Update existing entry
                    e["rating_label"] = rating_label
                    if star_rating is not None:
                        e["star_rating"] = star_rating
                    if diary_text:
                        e["diary_text"] = diary_text
                    e["is_reread"] = is_reread
                    e["spoiler"] = spoiler
                    e["vibe_tags"] = vibe_tags or []
                    e["updated_at"] = datetime.now().isoformat()
                    _save_diary(self.storage, entries)
                    log(f"Updated diary entry for {book_id}", user_id, rating_label)
                    return True, "Diary entry updated", e

        if not date_read:
            date_read = date.today().isoformat()

        entry = {
            "id": _gen_id(),
            "user_id": user_id,
            "book_id": book_id,
            "date_read": date_read,
            "is_reread": is_reread,
            "rating_label": rating_label,
            "star_rating": star_rating,
            "diary_text": diary_text.strip(),
            "spoiler": spoiler,
            "vibe_tags": vibe_tags or [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        entries.append(entry)
        _save_diary(self.storage, entries)
        log(f"Logged read of {book_id}", user_id, rating_label)

        # Update reading challenge automatically
        try:
            from app.services.reading.reading_challenge import ReadingChallenge

            rc = ReadingChallenge(self.storage)
            year = int(date_read[:4]) if date_read else datetime.now().year
            goal = rc.get_goal(user_id, year)
            if goal.get("goal", 0) > 0:
                rc.set_goal(user_id, year, goal["goal"])
        except Exception:
            pass

        return True, "Book logged in your reading diary!", entry

    def get_user_diary(
        self,
        user_id: str,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[dict], int]:
        """Get paginated diary entries for a user, enriched with book data."""
        entries = _load_diary(self.storage)
        user_entries = [e for e in entries if e["user_id"] == user_id]
        user_entries.sort(key=lambda e: e.get("date_read", ""), reverse=True)

        total = len(user_entries)
        start = (page - 1) * per_page
        end = start + per_page
        page_entries = user_entries[start:end]

        # Enrich with book data
        books = self.storage.load_books()
        enriched = []
        for e in page_entries:
            book = books.get(e["book_id"])
            enriched.append(
                {
                    **e,
                    "book_title": book.title if book else "Unknown Book",
                    "book_author": book.author if book else "",
                    "book_category": book.category if book else "",
                    "book_cover": book.cover_url or book.cover_image or "" if book else "",
                    "rating_badge": rating_badge_html(e.get("rating_label", "timepass")),
                    "star_html": star_rating_html(e.get("star_rating")),
                    "vibe_tags": e.get("vibe_tags", []),
                }
            )

        return enriched, total

    def get_entry(self, entry_id: str) -> dict | None:
        """Get a single diary entry by ID."""
        entries = _load_diary(self.storage)
        for e in entries:
            if e["id"] == entry_id:
                return e
        return None

    def update_entry(
        self,
        entry_id: str,
        user_id: str,
        **kwargs,
    ) -> tuple[bool, str]:
        """Update a diary entry."""
        entries = _load_diary(self.storage)
        for e in entries:
            if e["id"] == entry_id:
                if e["user_id"] != user_id:
                    # Allow admin to update any entry
                    users = self.storage.load_users()
                    user = users.get(user_id)
                    if not user or user.role != "admin":
                        return False, "You can only edit your own entries"
                allowed = {
                    "date_read",
                    "rating_label",
                    "star_rating",
                    "diary_text",
                    "is_reread",
                    "spoiler",
                    "vibe_tags",
                }
                for k, v in kwargs.items():
                    if k in allowed and v is not None:
                        e[k] = v
                e["updated_at"] = datetime.now().isoformat()
                _save_diary(self.storage, entries)
                log(f"Updated diary entry {entry_id}", user_id)
                return True, "Entry updated"
        return False, "Entry not found"

    def delete_entry(self, entry_id: str, user_id: str) -> tuple[bool, str]:
        """Delete a diary entry."""
        entries = _load_diary(self.storage)
        for i, e in enumerate(entries):
            if e["id"] == entry_id:
                if e["user_id"] != user_id:
                    users = self.storage.load_users()
                    user = users.get(user_id)
                    if not user or user.role != "admin":
                        return False, "You can only delete your own entries"
                entries.pop(i)
                _save_diary(self.storage, entries)
                log(f"Deleted diary entry {entry_id}", user_id)
                return True, "Entry deleted"
        return False, "Entry not found"

    # ═══════════════════════════════════════════════════════════════
    # BOOK LOGS
    # ═══════════════════════════════════════════════════════════════

    def get_book_logs(self, book_id: str, include_spoilers: bool = False) -> list[dict]:
        """Get all diary entries for a book (no spoilers unless opted in)."""
        entries = _load_diary(self.storage)
        book_entries = [e for e in entries if e["book_id"] == book_id]
        book_entries.sort(key=lambda e: e.get("date_read", ""), reverse=True)

        users = self.storage.load_users()
        enriched = []
        for e in book_entries:
            if e.get("spoiler") and not include_spoilers:
                # Show spoiler-tagged entry but redact text
                e = dict(e)
                e["diary_text"] = "[Spoiler hidden]"
            user = users.get(e["user_id"])
            enriched.append(
                {
                    **e,
                    "user_name": user.name if user else "Unknown",
                    "user_avatar": e["user_id"][:2].upper(),
                    "rating_badge": rating_badge_html(e.get("rating_label", "timepass")),
                }
            )

        return enriched

    # ═══════════════════════════════════════════════════════════════
    # STATISTICS
    # ═══════════════════════════════════════════════════════════════

    def get_stats(self, user_id: str) -> dict:
        """Get comprehensive reading stats for a user."""
        entries = _load_diary(self.storage)
        user_entries = [e for e in entries if e["user_id"] == user_id]

        if not user_entries:
            return {
                "total_books": 0,
                "books_by_month": {},
                "rating_distribution": {},
                "top_genres": [],
                "total_pages_read": 0,
                "avg_rating_label": "timepass",
                "reread_count": 0,
                "vibe_tags_cloud": [],
            }

        books = self.storage.load_books()

        # Books by month
        books_by_month = Counter()
        for e in user_entries:
            month_key = e.get("date_read", "")[:7]
            if month_key:
                books_by_month[month_key] += 1

        # Rating distribution
        rating_dist = Counter(e.get("rating_label", "timepass") for e in user_entries)

        # Top genres
        genre_counts = Counter()
        total_pages = 0
        for e in user_entries:
            book = books.get(e["book_id"])
            if book:
                genre_counts[book.category] += 1
                total_pages += getattr(book, "pages", 0) or 0

        # Average rating (by score)
        total_score = sum(
            RATING_SCORES.get(e.get("rating_label", "timepass"), 0) for e in user_entries
        )
        avg_score = total_score / len(user_entries) if user_entries else 0
        if avg_score >= 3.5:
            avg_label = "perfection"
        elif avg_score >= 2.5:
            avg_label = "worth_it"
        elif avg_score >= 1.5:
            avg_label = "timepass"
        else:
            avg_label = "skip"

        # Reread count
        reread_count = sum(1 for e in user_entries if e.get("is_reread"))

        # Vibe tags cloud
        all_vibes = Counter()
        for e in user_entries:
            for tag in e.get("vibe_tags", []):
                all_vibes[tag] += 1

        return {
            "total_books": len(user_entries),
            "books_by_month": dict(sorted(books_by_month.items())),
            "rating_distribution": dict(rating_dist),
            "top_genres": genre_counts.most_common(5),
            "total_pages_read": total_pages,
            "avg_rating_label": avg_label,
            "reread_count": reread_count,
            "vibe_tags_cloud": all_vibes.most_common(20),
        }
