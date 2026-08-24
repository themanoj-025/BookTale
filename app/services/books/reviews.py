"""
reviews.py - Book Reviews, Ratings & Bookshelves System

Features:
- Star ratings (1-5) + written reviews
- Spoiler tag support
- Helpful votes
- Bookshelves (Want to Read, Reading, Read)
- Reading stats & progress tracking
"""

import json
import os
import random
import uuid
from collections import defaultdict
from datetime import datetime

import app.storage.storage as storage_lib
from app.core.logger import log
from app.storage.storage import Storage


def _gen_id(prefix: str = "REV") -> str:
    ts = int(datetime.now().timestamp() * 1000)
    uid = str(uuid.uuid4())[:8]
    return f"{prefix}-{ts}-{uid}"


DEFAULT_SHELVES = ["want_to_read", "reading", "read"]

CUSTOM_SHELVES_FILE = "custom_shelves.json"


def _load_custom_shelves(storage: Storage) -> list:
    """Load custom shelf definitions from storage."""
    path = os.path.join(storage_lib.Config.DATA_DIR, CUSTOM_SHELVES_FILE)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def _save_custom_shelves(storage: Storage, shelves: list) -> None:
    """Save custom shelf definitions to storage."""
    path = os.path.join(storage_lib.Config.DATA_DIR, CUSTOM_SHELVES_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(shelves, f, indent=2)


class ReviewManager:
    """Manages book reviews, ratings, and bookshelves."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    # ═══════════════════════════════════════════════════════════════
    # REVIEWS & RATINGS
    # ═══════════════════════════════════════════════════════════════

    def add_review(
        self,
        user_id: str,
        book_id: str,
        rating: int,
        content: str = "",
        spoiler: bool = False,
    ) -> tuple[bool, str, dict | None]:
        """Add or update a review for a book."""
        if rating < 1 or rating > 5:
            return False, "Rating must be between 1 and 5", None

        reviews = self.storage.load_reviews()

        # Check if user already reviewed this book
        for r in reviews:
            if r["user_id"] == user_id and r["book_id"] == book_id:
                # Update existing review
                r["rating"] = rating
                r["content"] = content.strip()
                r["spoiler"] = spoiler
                r["updated_at"] = datetime.now().isoformat()
                self.storage.save_reviews(reviews)
                log(f"Updated review for {book_id}", user_id, f"rating:{rating}")
                return True, "Review updated", r

        now = datetime.now().isoformat()
        review = {
            "review_id": _gen_id("REV"),
            "user_id": user_id,
            "book_id": book_id,
            "rating": rating,
            "content": content.strip(),
            "spoiler": spoiler,
            "helpful_votes": [],
            "created_at": now,
            "updated_at": now,
        }
        self.storage.append_review(review)
        log(f"Added review for {book_id}", user_id, f"rating:{rating}")
        return True, "Review added!", review

    def mark_helpful(self, review_id: str, user_id: str) -> tuple[bool, str, bool]:
        """Toggle helpful vote on a review."""
        reviews = self.storage.load_reviews()
        for r in reviews:
            if r["review_id"] == review_id:
                if user_id in r.get("helpful_votes", []):
                    r["helpful_votes"].remove(user_id)
                    self.storage.save_reviews(reviews)
                    return True, "Marked not helpful", False
                else:
                    r["helpful_votes"].append(user_id)
                    self.storage.save_reviews(reviews)
                    return True, "Marked helpful", True
        return False, "Review not found", False

    def delete_review(self, review_id: str, user_id: str) -> tuple[bool, str]:
        """Delete a review. Author or admin can delete."""
        reviews = self.storage.load_reviews()
        users = self.storage.load_users()
        user = users.get(user_id)
        is_admin = user and user.role == "admin"
        for r in reviews:
            if r["review_id"] == review_id:
                if r["user_id"] != user_id and not is_admin:
                    return False, "You can only delete your own reviews"
                reviews.remove(r)
                self.storage.save_reviews(reviews)
                return True, "Review deleted"
        return False, "Review not found"

    # ═══════════════════════════════════════════════════════════════
    # REVIEW COMMENTS
    # ═══════════════════════════════════════════════════════════════

    def add_review_comment(
        self, review_id: str, user_id: str, content: str
    ) -> tuple[bool, str, dict | None]:
        """Add a comment to a review."""
        reviews = self.storage.load_reviews()
        review_exists = any(r["review_id"] == review_id for r in reviews)
        if not review_exists:
            return False, "Review not found", None
        if not content.strip():
            return False, "Comment cannot be empty", None

        comments_path = os.path.join(storage_lib.Config.DATA_DIR, "review_comments.json")
        try:
            with open(comments_path, encoding="utf-8") as f:
                comments = json.load(f)
        except:
            comments = []

        comment = {
            "comment_id": _gen_id("RC"),
            "review_id": review_id,
            "user_id": user_id,
            "content": content.strip(),
            "created_at": datetime.now().isoformat(),
            "likes": [],
        }
        comments.append(comment)
        with open(comments_path, "w", encoding="utf-8") as f:
            json.dump(comments, f, indent=2)
        return True, "Comment added", comment

    def get_review_comments(self, review_id: str) -> list[dict]:
        """Get all comments on a review."""
        comments_path = os.path.join(storage_lib.Config.DATA_DIR, "review_comments.json")
        try:
            with open(comments_path, encoding="utf-8") as f:
                all_comments = json.load(f)
        except:
            return []
        review_comments = [c for c in all_comments if c["review_id"] == review_id]
        review_comments.sort(key=lambda c: c["created_at"])
        # Enrich with user data
        users = self.storage.load_users()
        enriched = []
        for c in review_comments:
            commenter = users.get(c["user_id"])
            enriched.append(
                {
                    **c,
                    "author_name": commenter.name if commenter else "Unknown",
                    "author_avatar": c["user_id"][:2].upper(),
                    "time_ago": self._time_ago(c["created_at"]),
                }
            )
        return enriched

    def get_book_reviews(
        self,
        book_id: str,
        user_id: str = "",
        page: int = 1,
        per_page: int = 10,
        sort_by: str = "recent",
    ) -> tuple[list[dict], dict]:
        """Get all reviews for a book with stats. Supports sorting."""
        reviews = self.storage.load_reviews()
        users = self.storage.load_users()
        book_reviews = [r for r in reviews if r["book_id"] == book_id]

        # Calculate stats
        total = len(book_reviews)
        if total > 0:
            avg_rating = sum(r["rating"] for r in book_reviews) / total
            distribution = defaultdict(int)
            for r in book_reviews:
                distribution[r["rating"]] += 1
        else:
            avg_rating = 0
            distribution = {}

        # Sort
        if sort_by == "helpful":
            book_reviews.sort(key=lambda r: len(r.get("helpful_votes", [])), reverse=True)
        elif sort_by == "rating":
            book_reviews.sort(key=lambda r: r["rating"], reverse=True)
        elif sort_by == "lowest":
            book_reviews.sort(key=lambda r: r["rating"])
        else:  # recent
            book_reviews.sort(key=lambda r: r["created_at"], reverse=True)

        total_pages = max(1, (total + per_page - 1) // per_page)
        start = (page - 1) * per_page
        end = start + per_page
        page_reviews = book_reviews[start:end]

        # Enrich with user data
        enriched = []
        for r in page_reviews:
            reviewer = users.get(r["user_id"])
            enriched.append(
                {
                    **r,
                    "author_name": reviewer.name if reviewer else "Unknown",
                    "author_avatar": r["user_id"][:2].upper(),
                    "is_helpful": user_id in r.get("helpful_votes", []),
                    "helpful_count": len(r.get("helpful_votes", [])),
                    "time_ago": self._time_ago(r["created_at"]),
                }
            )

        stats = {
            "total": total,
            "average": round(avg_rating, 1),
            "distribution": dict(distribution),
            "page": page,
            "total_pages": total_pages,
        }

        return enriched, stats

    def get_user_reviews(
        self, user_id: str, viewer_id: str = "", page: int = 1, per_page: int = 10
    ) -> tuple[list[dict], int]:
        """Get all reviews by a user."""
        reviews = self.storage.load_reviews()
        books = self.storage.load_books()
        user_reviews = [r for r in reviews if r["user_id"] == user_id]
        user_reviews.sort(key=lambda r: r["created_at"], reverse=True)

        total = len(user_reviews)
        start = (page - 1) * per_page
        end = start + per_page
        page_reviews = user_reviews[start:end]

        enriched = []
        for r in page_reviews:
            book = books.get(r["book_id"])
            enriched.append(
                {
                    **r,
                    "book_title": book.title if book else "Unknown Book",
                    "book_author": book.author if book else "",
                    "book_category": book.category if book else "",
                    "is_helpful": viewer_id in r.get("helpful_votes", []),
                    "helpful_count": len(r.get("helpful_votes", [])),
                    "time_ago": self._time_ago(r["created_at"]),
                }
            )

        return enriched, total

    # ═══════════════════════════════════════════════════════════════
    # BOOKSHELVES
    # ═══════════════════════════════════════════════════════════════

    def add_to_shelf(
        self, user_id: str, book_id: str, shelf: str = "want_to_read"
    ) -> tuple[bool, str]:
        """Add a book to a user's shelf. Supports both default and custom shelves."""
        # Validate: if it's not a default shelf, it must exist as a custom shelf
        if shelf not in DEFAULT_SHELVES:
            custom = _load_custom_shelves(self.storage)
            valid = any(s["user_id"] == user_id and s["name"] == shelf for s in custom)
            if not valid:
                return (
                    False,
                    f"Shelf '{shelf}' not found. Create it first or use one of: {', '.join(DEFAULT_SHELVES)}",
                )

        books = self.storage.load_books()
        if book_id not in books:
            return False, "Book not found"

        shelves = self.storage.load_bookshelves()
        # Remove existing entry for this user+book
        shelves = [s for s in shelves if not (s["user_id"] == user_id and s["book_id"] == book_id)]
        now = datetime.now().isoformat()
        shelves.append({"user_id": user_id, "book_id": book_id, "shelf": shelf, "created_at": now})
        self.storage.save_bookshelves(shelves)
        log(f"Added {book_id} to {shelf}", user_id)
        return True, f"Book added to {shelf.replace('_', ' ')}"

    def get_user_shelf(self, user_id: str, shelf: str = "") -> list[dict]:
        """Get books on a user's shelf. Supports both default and custom shelves."""
        shelves = self.storage.load_bookshelves()
        books = self.storage.load_books()
        user_shelves = [s for s in shelves if s["user_id"] == user_id]
        if shelf:
            user_shelves = [s for s in user_shelves if s["shelf"] == shelf]

        enriched = []
        for s in user_shelves:
            book = books.get(s["book_id"])
            if book and not book.is_deleted:
                enriched.append(
                    {
                        "book_id": book.book_id,
                        "title": book.title,
                        "author": book.author,
                        "category": book.category,
                        "shelf": s["shelf"],
                        "added_at": s["created_at"],
                    }
                )

        # Sort: reading first, then want_to_read, then read, then custom alphabetic
        shelf_order = {"reading": 0, "want_to_read": 1, "read": 2}
        enriched.sort(key=lambda x: (shelf_order.get(x["shelf"], 9), x["added_at"]))
        return enriched

    def get_shelf_counts(self, user_id: str) -> dict:
        """Get count of books in each shelf for a user. Includes custom shelves."""
        shelves = self.storage.load_bookshelves()
        user_shelves = [s for s in shelves if s["user_id"] == user_id]
        counts = defaultdict(int)
        for s in user_shelves:
            counts[s["shelf"]] += 1
        result = {"total": sum(counts.values())}
        for s in DEFAULT_SHELVES:
            result[s] = counts.get(s, 0)
        # Add custom shelf counts
        custom = _load_custom_shelves(self.storage)
        user_custom = [c for c in custom if c["user_id"] == user_id]
        for c in user_custom:
            result[c["name"]] = counts.get(c["name"], 0)
        return result

    def remove_from_shelf(self, user_id: str, book_id: str) -> tuple[bool, str]:
        """Remove a book from a user's shelf entirely."""
        shelves = self.storage.load_bookshelves()
        old_len = len(shelves)
        shelves = [s for s in shelves if not (s["user_id"] == user_id and s["book_id"] == book_id)]
        if len(shelves) == old_len:
            return False, "Book not found on any shelf"
        self.storage.save_bookshelves(shelves)
        log(f"Removed {book_id} from shelves", user_id)
        return True, "Book removed from shelf"

    def move_to_shelf(self, user_id: str, book_id: str, shelf: str) -> tuple[bool, str]:
        """Move a book from one shelf to another."""
        ok, _msg = self.remove_from_shelf(user_id, book_id)
        if not ok:
            # It's okay if the book wasn't on any shelf
            pass
        return self.add_to_shelf(user_id, book_id, shelf)

    # ── Custom Shelf Management ──

    def create_custom_shelf(
        self, user_id: str, name: str, description: str = "", icon: str = "bookmark"
    ) -> tuple[bool, str]:
        """Create a custom shelf for a user."""
        name = name.strip()
        if not name:
            return False, "Shelf name cannot be empty"
        if name in DEFAULT_SHELVES:
            return False, f"'{name}' is a default shelf and cannot be recreated"
        if len(name) > 50:
            return False, "Shelf name too long (max 50 chars)"

        custom = _load_custom_shelves(self.storage)
        for c in custom:
            if c["user_id"] == user_id and c["name"].lower() == name.lower():
                return False, f"Shelf '{name}' already exists"

        custom.append(
            {
                "user_id": user_id,
                "name": name,
                "description": description,
                "icon": icon,
                "color": random.choice(  # nosec B311 (non-security UI accent color)
                    [
                        "#4f46e5",
                        "#059669",
                        "#d97706",
                        "#dc2626",
                        "#0891b2",
                        "#7c3aed",
                        "#db2777",
                        "#ca8a04",
                        "#16a34a",
                        "#e11d48",
                    ]
                ),
                "created_at": datetime.now().isoformat(),
            }
        )
        _save_custom_shelves(self.storage, custom)
        log(f"Created custom shelf '{name}'", user_id)
        return True, f"Shelf '{name}' created!"

    def delete_custom_shelf(self, user_id: str, name: str) -> tuple[bool, str]:
        """Delete a custom shelf. Books on the shelf are removed."""
        if name in DEFAULT_SHELVES:
            return False, "Cannot delete default shelves"
        custom = _load_custom_shelves(self.storage)
        idx = -1
        for i, c in enumerate(custom):
            if c["user_id"] == user_id and c["name"] == name:
                idx = i
                break
        if idx < 0:
            return False, f"Shelf '{name}' not found"
        custom.pop(idx)
        _save_custom_shelves(self.storage, custom)
        # Remove all books from this shelf
        shelves = self.storage.load_bookshelves()
        shelves = [s for s in shelves if not (s["user_id"] == user_id and s["shelf"] == name)]
        self.storage.save_bookshelves(shelves)
        log(f"Deleted custom shelf '{name}'", user_id)
        return True, f"Shelf '{name}' deleted"

    def rename_custom_shelf(self, user_id: str, old_name: str, new_name: str) -> tuple[bool, str]:
        """Rename a custom shelf. Books are preserved."""
        new_name = new_name.strip()
        if not new_name:
            return False, "New name cannot be empty"
        if new_name in DEFAULT_SHELVES:
            return False, f"'{new_name}' is a default shelf"
        custom = _load_custom_shelves(self.storage)
        # Check for duplicate name
        for c in custom:
            if (
                c["user_id"] == user_id
                and c["name"].lower() == new_name.lower()
                and c["name"] != old_name
            ):
                return False, f"Shelf '{new_name}' already exists"
        found = False
        for c in custom:
            if c["user_id"] == user_id and c["name"] == old_name:
                c["name"] = new_name
                found = True
                break
        if not found:
            return False, f"Shelf '{old_name}' not found"
        _save_custom_shelves(self.storage, custom)
        # Update all bookshelf entries with old name to new name
        shelves = self.storage.load_bookshelves()
        for s in shelves:
            if s["user_id"] == user_id and s["shelf"] == old_name:
                s["shelf"] = new_name
        self.storage.save_bookshelves(shelves)
        log(f"Renamed shelf '{old_name}' -> '{new_name}'", user_id)
        return True, f"Shelf renamed to '{new_name}'"

    def get_user_custom_shelves(self, user_id: str) -> list[dict]:
        """Get all custom shelves for a user."""
        custom = _load_custom_shelves(self.storage)
        user_custom = [c for c in custom if c["user_id"] == user_id]
        # Add book counts
        shelves = self.storage.load_bookshelves()
        for c in user_custom:
            c["book_count"] = sum(
                1 for s in shelves if s["user_id"] == user_id and s["shelf"] == c["name"]
            )
        return user_custom

    def get_all_shelf_names(self, user_id: str) -> list[str]:
        """Get all shelf names for a user (defaults + custom)."""
        names = list(DEFAULT_SHELVES)
        custom = _load_custom_shelves(self.storage)
        for c in custom:
            if c["user_id"] == user_id:
                names.append(c["name"])
        return names

    def is_on_shelf(self, user_id: str, book_id: str) -> str | None:
        """Check if a book is on any shelf. Returns shelf name or None."""
        shelves = self.storage.load_bookshelves()
        for s in shelves:
            if s["user_id"] == user_id and s["book_id"] == book_id:
                return s["shelf"]
        return None

    # ═══════════════════════════════════════════════════════════════
    # READING STATS
    # ═══════════════════════════════════════════════════════════════

    def get_user_reading_stats(self, user_id: str) -> dict:
        """Get comprehensive reading statistics for a user."""
        shelves = self.storage.load_bookshelves()
        reviews = self.storage.load_reviews()
        user_shelves = [s for s in shelves if s["user_id"] == user_id]
        user_reviews = [r for r in reviews if r["user_id"] == user_id]

        read_books = [s for s in user_shelves if s["shelf"] == "read"]

        # Category breakdown
        books = self.storage.load_books()
        categories = defaultdict(int)
        for s in read_books:
            book = books.get(s["book_id"])
            if book:
                categories[book.category] += 1

        # Rating distribution
        rating_dist = defaultdict(int)
        total_rating = 0
        for r in user_reviews:
            rating_dist[r["rating"]] += 1
            total_rating += r["rating"]

        # Monthly reading (last 12 months)
        monthly = defaultdict(int)
        for s in read_books:
            try:
                month_key = s["created_at"][:7]  # YYYY-MM
                monthly[month_key] += 1
            except (ValueError, TypeError):
                pass

        avg_rating = round(total_rating / len(user_reviews), 1) if user_reviews else 0
        top_category = max(categories, key=categories.get) if categories else "None"

        return {
            "total_read": len(read_books),
            "total_reviews": len(user_reviews),
            "total_on_shelves": len(user_shelves),
            "avg_rating": avg_rating,
            "top_category": top_category,
            "categories": dict(categories),
            "rating_distribution": dict(rating_dist),
            "monthly_reading": dict(sorted(monthly.items())),
        }

    def _time_ago(self, iso_str: str) -> str:
        try:
            dt = datetime.fromisoformat(iso_str)
            now = datetime.now()
            diff = now - dt
            seconds = int(diff.total_seconds())
            if seconds < 60:
                return "just now"
            minutes = seconds // 60
            if minutes < 60:
                return f"{minutes}m ago"
            hours = minutes // 60
            if hours < 24:
                return f"{hours}h ago"
            days = hours // 24
            if days < 7:
                return f"{days}d ago"
            weeks = days // 7
            if weeks < 4:
                return f"{weeks}w ago"
            months = days // 30
            if months < 12:
                return f"{months}mo ago"
            years = days // 365
            return f"{years}y ago"
        except (ValueError, TypeError, AttributeError):
            return iso_str[:10]
