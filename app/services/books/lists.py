"""
lists.py - Book Lists & Collections System

Features:
- Custom lists (watchlists, top 10, curated collections)
- Public/private visibility
- Collaborative lists (multiple editors)
- List following
- Weekly trending books
"""

import json
import os
import uuid
from collections import Counter
from datetime import datetime, timedelta

from app.config.settings import Config
from app.core.logger import log
from app.storage.storage import Storage


def _gen_id(prefix: str = "LIST") -> str:
    ts = int(datetime.now().timestamp() * 1000)
    uid = str(uuid.uuid4())[:8]
    return f"{prefix}-{ts}-{uid}"


class BookLists:
    """Manages book lists, collections, and weekly trending."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def _get_lists_path(self) -> str:
        return os.path.join(Config.DATA_DIR, "book_lists.json")

    def _load_lists(self) -> list:
        path = self._get_lists_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_lists(self, lists: list) -> None:
        path = self._get_lists_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(lists, f, indent=2)

    # ── CRUD ────────────────────────────────────────────────────

    def create_list(
        self,
        user_id: str,
        name: str,
        description: str = "",
        is_public: bool = True,
        list_type: str = "custom",
    ) -> tuple[bool, str, dict | None]:
        """Create a new book list."""
        if not name.strip():
            return False, "List name cannot be empty", None
        lists = self._load_lists()
        now = datetime.now().isoformat()
        new_list = {
            "list_id": _gen_id("LIST"),
            "name": name.strip(),
            "description": description.strip(),
            "owner_id": user_id,
            "is_public": is_public,
            "list_type": list_type,  # custom, top10, watchlist, weekly
            "books": [],
            "collaborators": [],
            "followers": [],
            "upvotes": 0,
            "upvoters": [],
            "created_at": now,
            "updated_at": now,
        }
        lists.append(new_list)
        self._save_lists(lists)
        log(f"Created list '{name}'", user_id, f"type:{list_type}")
        return True, "List created!", new_list

    def get_list(self, list_id: str) -> dict | None:
        lists = self._load_lists()
        for lst in lists:
            if lst["list_id"] == list_id:
                return lst
        return None

    def update_list(
        self,
        list_id: str,
        user_id: str,
        name: str = None,
        description: str = None,
        is_public: bool = None,
    ) -> tuple[bool, str]:
        lists = self._load_lists()
        for lst in lists:
            if lst["list_id"] == list_id:
                if lst["owner_id"] != user_id and user_id not in lst.get(
                    "collaborators", []
                ):
                    return False, "You don't have permission to edit this list"
                if name is not None:
                    lst["name"] = name.strip()
                if description is not None:
                    lst["description"] = description.strip()
                if is_public is not None:
                    lst["is_public"] = is_public
                lst["updated_at"] = datetime.now().isoformat()
                self._save_lists(lists)
                return True, "List updated!"
        return False, "List not found"

    def delete_list(self, list_id: str, user_id: str) -> tuple[bool, str]:
        lists = self._load_lists()
        for lst in lists:
            if lst["list_id"] == list_id:
                if lst["owner_id"] != user_id:
                    return False, "Only the owner can delete this list"
                lists.remove(lst)
                self._save_lists(lists)
                return True, "List deleted!"
        return False, "List not found"

    # ── Books in Lists ──────────────────────────────────────────

    def add_book_to_list(
        self, list_id: str, book_id: str, user_id: str, note: str = ""
    ) -> tuple[bool, str]:
        lists = self._load_lists()
        for lst in lists:
            if lst["list_id"] == list_id:
                if lst["owner_id"] != user_id and user_id not in lst.get(
                    "collaborators", []
                ):
                    return False, "Permission denied"
                if any(b["book_id"] == book_id for b in lst["books"]):
                    return False, "Book already in list"
                books_data = self.storage.load_books()
                book = books_data.get(book_id)
                if not book or book.is_deleted:
                    return False, "Book not found"
                lst["books"].append(
                    {
                        "book_id": book_id,
                        "title": book.title,
                        "author": book.author,
                        "added_by": user_id,
                        "added_at": datetime.now().isoformat(),
                        "note": note.strip(),
                        "order": len(lst["books"]),
                    }
                )
                lst["updated_at"] = datetime.now().isoformat()
                self._save_lists(lists)
                return True, "Book added to list!"
        return False, "List not found"

    def remove_book_from_list(
        self, list_id: str, book_id: str, user_id: str
    ) -> tuple[bool, str]:
        lists = self._load_lists()
        for lst in lists:
            if lst["list_id"] == list_id:
                if lst["owner_id"] != user_id and user_id not in lst.get(
                    "collaborators", []
                ):
                    return False, "Permission denied"
                lst["books"] = [b for b in lst["books"] if b["book_id"] != book_id]
                lst["updated_at"] = datetime.now().isoformat()
                self._save_lists(lists)
                return True, "Book removed from list!"
        return False, "List not found"

    def reorder_list(
        self, list_id: str, user_id: str, book_ids: list[str]
    ) -> tuple[bool, str]:
        lists = self._load_lists()
        for lst in lists:
            if lst["list_id"] == list_id and lst["owner_id"] == user_id:
                ordered = []
                for bid in book_ids:
                    for b in lst["books"]:
                        if b["book_id"] == bid:
                            b["order"] = len(ordered)
                            ordered.append(b)
                            break
                lst["books"] = ordered
                lst["updated_at"] = datetime.now().isoformat()
                self._save_lists(lists)
                return True, "List reordered!"
        return False, "List not found"

    # ── Collaboration ───────────────────────────────────────────

    def add_collaborator(
        self, list_id: str, owner_id: str, collaborator_id: str
    ) -> tuple[bool, str]:
        lists = self._load_lists()
        for lst in lists:
            if lst["list_id"] == list_id:
                if lst["owner_id"] != owner_id:
                    return False, "Only the owner can add collaborators"
                if collaborator_id not in lst["collaborators"]:
                    lst["collaborators"].append(collaborator_id)
                    self._save_lists(lists)
                return True, "Collaborator added!"
        return False, "List not found"

    def remove_collaborator(
        self, list_id: str, owner_id: str, collaborator_id: str
    ) -> tuple[bool, str]:
        lists = self._load_lists()
        for lst in lists:
            if lst["list_id"] == list_id and lst["owner_id"] == owner_id:
                lst["collaborators"] = [
                    c for c in lst["collaborators"] if c != collaborator_id
                ]
                self._save_lists(lists)
                return True, "Collaborator removed!"
        return False, "List not found"

    # ── Following & Voting ──────────────────────────────────────

    def follow_list(self, list_id: str, user_id: str) -> tuple[bool, str]:
        lists = self._load_lists()
        for lst in lists:
            if lst["list_id"] == list_id:
                if user_id not in lst["followers"]:
                    lst["followers"].append(user_id)
                    self._save_lists(lists)
                return True, "Following list!"
        return False, "List not found"

    def unfollow_list(self, list_id: str, user_id: str) -> tuple[bool, str]:
        lists = self._load_lists()
        for lst in lists:
            if lst["list_id"] == list_id:
                lst["followers"] = [f for f in lst["followers"] if f != user_id]
                self._save_lists(lists)
                return True, "Unfollowed list!"
        return False, "List not found"

    def upvote_list(self, list_id: str, user_id: str) -> tuple[bool, str, bool]:
        lists = self._load_lists()
        for lst in lists:
            if lst["list_id"] == list_id:
                if user_id in lst.get("upvoters", []):
                    lst["upvoters"].remove(user_id)
                    lst["upvotes"] = len(lst["upvoters"])
                    self._save_lists(lists)
                    return True, "Upvote removed", False
                lst["upvoters"].append(user_id)
                lst["upvotes"] = len(lst["upvoters"])
                self._save_lists(lists)
                return True, "List upvoted!", True
        return False, "List not found", False

    # ── Querying ────────────────────────────────────────────────

    def get_user_lists(self, user_id: str, include_private: bool = False) -> list[dict]:
        lists = self._load_lists()
        result = [
            lst
            for lst in lists
            if lst["owner_id"] == user_id
            or user_id in lst.get("collaborators", [])
            or (include_private and lst["is_public"])
        ]
        result.sort(key=lambda l: l["updated_at"], reverse=True)
        return result

    def get_public_lists(
        self, page: int = 1, per_page: int = 20
    ) -> tuple[list[dict], int]:
        lists = self._load_lists()
        public = [lst for lst in lists if lst["is_public"]]
        public.sort(
            key=lambda l: (l.get("upvotes", 0), len(l["followers"])), reverse=True
        )
        total = len(public)
        start = (page - 1) * per_page
        end = start + per_page
        return public[start:end], total

    def get_trending_lists(self, limit: int = 10) -> list[dict]:
        lists = self._load_lists()
        public = [lst for lst in lists if lst["is_public"]]
        public.sort(
            key=lambda l: (
                l.get("upvotes", 0) * 3 + len(l["followers"]) * 2 + len(l["books"])
            ),
            reverse=True,
        )
        return public[:limit]

    def get_weekly_trending_books(self, limit: int = 10) -> list[dict]:
        """Books that are most popular this week across all lists and activity."""
        txns = self.storage.load_transactions()
        posts = self.storage.load_posts()
        week_ago = datetime.now() - timedelta(days=7)
        book_scores = Counter()

        # Transaction activity this week
        for t in txns:
            try:
                dt = datetime.fromisoformat(t.get("issue_date", ""))
                if dt >= week_ago and t["type"] == "issue":
                    book_scores[t["book_id"]] += 3
            except Exception:
                pass

        # Posts mentioning books this week
        for p in posts:
            try:
                dt = datetime.fromisoformat(p.get("created_at", ""))
                if dt >= week_ago:
                    for bid in p.get("book_ids", []):
                        book_scores[bid] += 1
            except Exception:
                pass

        # Reviews this week
        reviews = self.storage.load_reviews()
        for r in reviews:
            try:
                dt = datetime.fromisoformat(r.get("created_at", ""))
                if dt >= week_ago:
                    book_scores[r["book_id"]] += 2
            except Exception:
                pass

        books_data = self.storage.load_books()
        result = []
        for bid, score in book_scores.most_common(limit):
            book = books_data.get(bid)
            if book and not book.is_deleted:
                result.append(
                    {
                        "book_id": bid,
                        "title": book.title,
                        "author": book.author,
                        "category": book.category,
                        "score": score,
                        "available": book.available_copies,
                    }
                )
        return result

    def search_lists(self, query: str) -> list[dict]:
        q = query.lower()
        lists = self._load_lists()
        result = [
            lst
            for lst in lists
            if lst["is_public"]
            and (q in lst["name"].lower() or q in lst["description"].lower())
        ]
        result.sort(key=lambda l: l.get("upvotes", 0), reverse=True)
        return result[:20]

    def get_user_feed_lists(self, user_id: str, following: list[str]) -> list[dict]:
        """Get lists from users the given user follows."""
        lists = self._load_lists()
        result = [
            lst
            for lst in lists
            if lst["owner_id"] in following or user_id in lst.get("collaborators", [])
        ]
        result.sort(key=lambda l: l["updated_at"], reverse=True)
        return result[:20]
