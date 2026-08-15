"""
wishlist.py - Book Wishlist & Suggestion System

Features:
- Community book suggestions with title, author, reason
- Upvote/downvote on suggestions
- Admin approval workflow (approve/reject)
- Notifications when suggestion is approved
- Trending suggestions
- Purchase status tracking
"""

import json
import os
import uuid
from collections import Counter
from datetime import datetime

from app.config.settings import Config
from app.core.logger import log
from app.storage.storage import Storage


def _gen_id(prefix: str = "WISH") -> str:
    ts = int(datetime.now().timestamp() * 1000)
    uid = str(uuid.uuid4())[:8]
    return f"{prefix}-{ts}-{uid}"


SUGGESTION_STATUSES = ["pending", "approved", "rejected", "purchased"]


class Wishlist:
    """Manages book suggestions, voting, and approval workflow."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def _get_wishlist_path(self) -> str:
        return os.path.join(Config.DATA_DIR, "wishlist.json")

    def _load_suggestions(self) -> list:
        path = self._get_wishlist_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_suggestions(self, suggestions: list) -> None:
        path = self._get_wishlist_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(suggestions, f, indent=2)

    def add_suggestion(
        self,
        user_id: str,
        title: str,
        author: str = "",
        reason: str = "",
        isbn: str = "",
        category: str = "",
        url: str = "",
    ) -> tuple[bool, str, dict | None]:
        """Submit a new book suggestion."""
        if not title.strip():
            return False, "Book title is required", None
        suggestions = self._load_suggestions()
        now = datetime.now().isoformat()
        suggestion = {
            "suggestion_id": _gen_id("WISH"),
            "user_id": user_id,
            "title": title.strip(),
            "author": author.strip(),
            "reason": reason.strip(),
            "isbn": isbn.strip(),
            "category": category,
            "url": url.strip(),
            "status": "pending",
            "upvotes": [],
            "downvotes": [],
            "comments": [],
            "admin_notes": "",
            "created_at": now,
            "updated_at": now,
            "resolved_at": "",
        }
        suggestions.append(suggestion)
        self._save_suggestions(suggestions)
        log(f"Suggested book: '{title}'", user_id)
        return True, "Book suggestion submitted for review!", suggestion

    def vote_suggestion(
        self, suggestion_id: str, user_id: str, vote: str
    ) -> tuple[bool, str, dict]:
        """Upvote or downvote a suggestion."""
        if vote not in ("up", "down"):
            return False, "Vote must be 'up' or 'down'", {}
        suggestions = self._load_suggestions()
        for s in suggestions:
            if s["suggestion_id"] == suggestion_id:
                upvotes = s.get("upvotes", [])
                downvotes = s.get("downvotes", [])
                # Remove existing votes by this user
                if user_id in upvotes:
                    upvotes.remove(user_id)
                if user_id in downvotes:
                    downvotes.remove(user_id)
                # Add new vote
                if vote == "up":
                    upvotes.append(user_id)
                else:
                    downvotes.append(user_id)
                s["upvotes"] = upvotes
                s["downvotes"] = downvotes
                s["score"] = len(upvotes) - len(downvotes)
                s["updated_at"] = datetime.now().isoformat()
                self._save_suggestions(suggestions)
                return (
                    True,
                    "Vote recorded!",
                    {
                        "score": s["score"],
                        "upvotes": len(upvotes),
                        "downvotes": len(downvotes),
                        "user_vote": vote,
                    },
                )
        return False, "Suggestion not found", {}

    def moderate_suggestion(
        self, suggestion_id: str, admin_id: str, status: str, admin_notes: str = ""
    ) -> tuple[bool, str]:
        """Approve, reject, or mark suggestion as purchased."""
        if status not in SUGGESTION_STATUSES:
            return False, f"Invalid status. Use: {', '.join(SUGGESTION_STATUSES)}"
        suggestions = self._load_suggestions()
        now = datetime.now().isoformat()
        for s in suggestions:
            if s["suggestion_id"] == suggestion_id:
                old_status = s["status"]
                s["status"] = status
                s["admin_notes"] = admin_notes.strip()
                s["resolved_at"] = now if status in ("approved", "rejected") else ""
                s["updated_at"] = now
                s["moderated_by"] = admin_id
                self._save_suggestions(suggestions)

                # If approved, automatically add the book if it doesn't exist
                if status == "approved":
                    self._auto_add_book(s, admin_id)

                log(f"Suggestion '{s['title']}' {old_status} -> {status}", admin_id)
                return True, f"Suggestion {status}!"
        return False, "Suggestion not found"

    def _auto_add_book(self, suggestion: dict, admin_id: str) -> None:
        """Try to auto-add a book from an approved suggestion."""
        from app.services.books.library import Library

        try:
            lib = Library(self.storage)
            ok, msg = lib.add_book(
                title=suggestion["title"],
                author=suggestion.get("author", "Unknown") or "Unknown",
                isbn=suggestion.get("isbn", ""),
                category=suggestion.get("category", "Other") or "Other",
                copies=1,
                actor=admin_id,
            )
            if ok:
                # Send notification to suggester
                from app.services.notifications.notifications import NotificationManager

                notif = NotificationManager(self.storage)
                notif.add_notification(
                    suggestion["user_id"],
                    "suggestion_approved",
                    f'Your suggestion "{suggestion["title"]}" was approved and added to the library! (ID: {msg})',
                )
        except Exception as e:
            log(f"Auto-add book failed for suggestion: {e}", admin_id)

    def get_suggestions(
        self,
        status: str = "",
        user_id: str = "",
        page: int = 1,
        per_page: int = 20,
        sort_by: str = "score",
    ) -> tuple[list[dict], int]:
        """Get suggestions with optional filtering."""
        suggestions = self._load_suggestions()
        users = self.storage.load_users()

        # Filter
        if status and status in SUGGESTION_STATUSES:
            suggestions = [s for s in suggestions if s["status"] == status]
        if user_id:
            suggestions = [s for s in suggestions if s["user_id"] == user_id]

        # Calculate scores
        for s in suggestions:
            s["score"] = len(s.get("upvotes", [])) - len(s.get("downvotes", []))
            # Enrich with user info
            suggester = users.get(s["user_id"])
            s["suggester_name"] = suggester.name if suggester else "Unknown"

        # Sort
        if sort_by == "newest":
            suggestions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        elif sort_by == "oldest":
            suggestions.sort(key=lambda s: s.get("created_at", ""))
        elif sort_by == "votes":
            suggestions.sort(key=lambda s: len(s.get("upvotes", [])), reverse=True)
        else:  # score
            suggestions.sort(key=lambda s: s.get("score", 0), reverse=True)

        total = len(suggestions)
        start = (page - 1) * per_page
        end = start + per_page
        return suggestions[start:end], total

    def get_suggestion(self, suggestion_id: str) -> dict | None:
        """Get a single suggestion by ID."""
        suggestions = self._load_suggestions()
        for s in suggestions:
            if s["suggestion_id"] == suggestion_id:
                s["score"] = len(s.get("upvotes", [])) - len(s.get("downvotes", []))
                users = self.storage.load_users()
                suggester = users.get(s["user_id"])
                s["suggester_name"] = suggester.name if suggester else "Unknown"
                return s
        return None

    def add_suggestion_comment(
        self, suggestion_id: str, user_id: str, content: str
    ) -> tuple[bool, str]:
        """Add a comment to a suggestion."""
        if not content.strip():
            return False, "Comment cannot be empty"
        suggestions = self._load_suggestions()
        for s in suggestions:
            if s["suggestion_id"] == suggestion_id:
                comments = s.get("comments", [])
                comments.append(
                    {
                        "user_id": user_id,
                        "content": content.strip(),
                        "created_at": datetime.now().isoformat(),
                    }
                )
                s["comments"] = comments
                s["updated_at"] = datetime.now().isoformat()
                self._save_suggestions(suggestions)
                return True, "Comment added!"
        return False, "Suggestion not found"

    def get_trending_suggestions(self, limit: int = 10) -> list[dict]:
        """Get trending/popular suggestions (high score, pending)."""
        pending, _ = self.get_suggestions(status="pending", sort_by="score")
        return pending[:limit]

    def get_user_suggestions(self, user_id: str) -> list[dict]:
        """Get all suggestions by a user."""
        suggestions, _ = self.get_suggestions(user_id=user_id)
        return suggestions

    def get_suggestion_stats(self) -> dict:
        """Get aggregate statistics about suggestions."""
        suggestions = self._load_suggestions()
        total = len(suggestions)
        by_status = Counter(s["status"] for s in suggestions)
        total_votes = sum(
            len(s.get("upvotes", [])) + len(s.get("downvotes", [])) for s in suggestions
        )
        return {
            "total": total,
            "pending": by_status.get("pending", 0),
            "approved": by_status.get("approved", 0),
            "rejected": by_status.get("rejected", 0),
            "purchased": by_status.get("purchased", 0),
            "total_votes": total_votes,
            "unique_suggesters": len(set(s["user_id"] for s in suggestions)),
        }
