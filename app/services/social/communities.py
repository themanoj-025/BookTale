"""
communities.py - Book Clubs, Forums, Fan Communities & Polls

Features:
- Book clubs with members, discussions, reading schedules
- Discussion forums with topics and replies
- Fan communities (genre/author specific)
- Polls with voting
"""

import json
import os
import uuid
from collections import Counter
from datetime import datetime, timedelta

from app.config.settings import Config
from app.core.logger import log
from app.storage.storage import Storage


def _gen_id(prefix: str = "COM") -> str:
    ts = int(datetime.now().timestamp() * 1000)
    uid = str(uuid.uuid4())[:8]
    return f"{prefix}-{ts}-{uid}"


class Communities:
    """Manages book clubs, forums, communities, and polls."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def _data_path(self, filename: str) -> str:
        return os.path.join(Config.DATA_DIR, filename)

    def _load_json(self, filename: str) -> list:
        path = self._data_path(filename)
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_json(self, filename: str, data: list) -> None:
        path = self._data_path(filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    # ═══════════════════════════════════════════════════════════════
    # BOOK CLUBS
    # ═══════════════════════════════════════════════════════════════

    def create_club(
        self,
        name: str,
        description: str,
        owner_id: str,
        category: str = "General",
        is_public: bool = True,
        max_members: int = 50,
    ) -> tuple[bool, str, dict | None]:
        if not name.strip():
            return False, "Club name required", None
        clubs = self._load_json("clubs.json")
        now = datetime.now().isoformat()
        club = {
            "club_id": _gen_id("CLUB"),
            "name": name.strip(),
            "description": description.strip(),
            "owner_id": owner_id,
            "category": category,
            "is_public": is_public,
            "max_members": max_members,
            "members": [owner_id],
            "moderators": [owner_id],
            "current_book": None,
            "meeting_schedule": "",
            "created_at": now,
            "updated_at": now,
        }
        clubs.append(club)
        self._save_json("clubs.json", clubs)
        log(f"Created club '{name}'", owner_id, category)
        return True, "Club created!", club

    def join_club(self, club_id: str, user_id: str) -> tuple[bool, str]:
        clubs = self._load_json("clubs.json")
        for c in clubs:
            if c["club_id"] == club_id:
                if user_id in c["members"]:
                    return False, "Already a member"
                if len(c["members"]) >= c.get("max_members", 50):
                    return False, "Club is full"
                c["members"].append(user_id)
                c["updated_at"] = datetime.now().isoformat()
                self._save_json("clubs.json", clubs)
                return True, "Joined club!"
        return False, "Club not found"

    def leave_club(self, club_id: str, user_id: str) -> tuple[bool, str]:
        clubs = self._load_json("clubs.json")
        for c in clubs:
            if c["club_id"] == club_id:
                if user_id not in c["members"]:
                    return False, "Not a member"
                c["members"].remove(user_id)
                if user_id in c.get("moderators", []):
                    c["moderators"].remove(user_id)
                c["updated_at"] = datetime.now().isoformat()
                self._save_json("clubs.json", clubs)
                return True, "Left club"
        return False, "Club not found"

    def set_club_book(self, club_id: str, book_id: str, user_id: str) -> tuple[bool, str]:
        clubs = self._load_json("clubs.json")
        for c in clubs:
            if c["club_id"] == club_id and c["owner_id"] == user_id:
                books = self.storage.load_books()
                book = books.get(book_id)
                if not book or book.is_deleted:
                    return False, "Book not found"
                c["current_book"] = {
                    "book_id": book_id,
                    "title": book.title,
                    "author": book.author,
                    "set_by": user_id,
                    "set_at": datetime.now().isoformat(),
                }
                c["updated_at"] = datetime.now().isoformat()
                self._save_json("clubs.json", clubs)
                return True, f"Club is now reading {book.title}!"
        return False, "Club not found or not authorized"

    def get_clubs(
        self, user_id: str = "", page: int = 1, per_page: int = 20
    ) -> tuple[list[dict], int]:
        clubs = self._load_json("clubs.json")
        if user_id:
            user_clubs = [c for c in clubs if user_id in c["members"]]
        else:
            user_clubs = [c for c in clubs if c.get("is_public", True)]
        user_clubs.sort(key=lambda c: len(c["members"]), reverse=True)
        total = len(user_clubs)
        start = (page - 1) * per_page
        end = start + per_page
        return user_clubs[start:end], total

    def get_club(self, club_id: str) -> dict | None:
        clubs = self._load_json("clubs.json")
        for c in clubs:
            if c["club_id"] == club_id:
                return c
        return None

    def search_clubs(self, query: str) -> list[dict]:
        q = query.lower()
        clubs = self._load_json("clubs.json")
        return [
            c
            for c in clubs
            if c.get("is_public", True)
            and (q in c["name"].lower() or q in c.get("description", "").lower())
        ][:20]

    # ═══════════════════════════════════════════════════════════════
    # DISCUSSION FORUMS
    # ═══════════════════════════════════════════════════════════════

    def create_topic(
        self,
        club_id: str,
        user_id: str,
        title: str,
        content: str,
        is_pinned: bool = False,
    ) -> tuple[bool, str, dict | None]:
        if not title.strip() or not content.strip():
            return False, "Title and content required", None
        topics = self._load_json("forum_topics.json")
        now = datetime.now().isoformat()
        topic = {
            "topic_id": _gen_id("TOPIC"),
            "club_id": club_id,
            "user_id": user_id,
            "title": title.strip(),
            "content": content.strip(),
            "is_pinned": is_pinned,
            "views": 0,
            "replies_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        topics.append(topic)
        self._save_json("forum_topics.json", topics)
        return True, "Topic created!", topic

    def get_topics(self, club_id: str, page: int = 1, per_page: int = 20) -> tuple[list[dict], int]:
        topics = self._load_json("forum_topics.json")
        club_topics = [t for t in topics if t["club_id"] == club_id]
        club_topics.sort(
            key=lambda t: (not t.get("is_pinned", False), t["updated_at"]), reverse=True
        )
        total = len(club_topics)
        start = (page - 1) * per_page
        end = start + per_page
        # Enrich with user data
        users = self.storage.load_users()
        enriched = []
        for t in club_topics[start:end]:
            author = users.get(t["user_id"])
            enriched.append({**t, "author_name": author.name if author else "Unknown"})
        return enriched, total

    def get_topic(self, topic_id: str) -> dict | None:
        topics = self._load_json("forum_topics.json")
        for t in topics:
            if t["topic_id"] == topic_id:
                t["views"] = t.get("views", 0) + 1
                self._save_json("forum_topics.json", topics)
                return t
        return None

    def add_reply(self, topic_id: str, user_id: str, content: str) -> tuple[bool, str, dict | None]:
        if not content.strip():
            return False, "Reply cannot be empty", None
        replies = self._load_json("forum_replies.json")
        now = datetime.now().isoformat()
        reply = {
            "reply_id": _gen_id("REPLY"),
            "topic_id": topic_id,
            "user_id": user_id,
            "content": content.strip(),
            "created_at": now,
            "likes": [],
        }
        replies.append(reply)
        self._save_json("forum_replies.json", replies)
        # Update reply count
        topics = self._load_json("forum_topics.json")
        for t in topics:
            if t["topic_id"] == topic_id:
                t["replies_count"] = len([r for r in replies if r["topic_id"] == topic_id])
                t["updated_at"] = now
                self._save_json("forum_topics.json", topics)
                break
        return True, "Reply posted!", reply

    def get_replies(self, topic_id: str) -> list[dict]:
        replies = self._load_json("forum_replies.json")
        topic_replies = [r for r in replies if r["topic_id"] == topic_id]
        topic_replies.sort(key=lambda r: r["created_at"])
        users = self.storage.load_users()
        enriched = []
        for r in topic_replies:
            author = users.get(r["user_id"])
            enriched.append({**r, "author_name": author.name if author else "Unknown"})
        return enriched

    # ═══════════════════════════════════════════════════════════════
    # POLLS
    # ═══════════════════════════════════════════════════════════════

    def create_poll(
        self,
        club_id: str,
        user_id: str,
        question: str,
        options: list[str],
        is_multiple_choice: bool = False,
        expires_in_hours: int = 168,
    ) -> tuple[bool, str, dict | None]:
        if len(options) < 2:
            return False, "At least 2 options required", None
        if len(options) > 10:
            return False, "Maximum 10 options", None
        polls = self._load_json("polls.json")
        now = datetime.now().isoformat()
        expiry = (datetime.now() + timedelta(hours=expires_in_hours)).isoformat()
        poll = {
            "poll_id": _gen_id("POLL"),
            "club_id": club_id,
            "user_id": user_id,
            "question": question.strip(),
            "options": [{"text": o.strip(), "votes": []} for o in options],
            "is_multiple_choice": is_multiple_choice,
            "is_active": True,
            "created_at": now,
            "expires_at": expiry,
        }
        polls.append(poll)
        self._save_json("polls.json", polls)
        return True, "Poll created!", poll

    def vote_poll(self, poll_id: str, user_id: str, option_indices: list[int]) -> tuple[bool, str]:
        polls = self._load_json("polls.json")
        for p in polls:
            if p["poll_id"] == poll_id:
                if not p.get("is_active", True):
                    return False, "Poll has ended"
                expiry = datetime.fromisoformat(p.get("expires_at", "2099-01-01"))
                if datetime.now() > expiry:
                    p["is_active"] = False
                    self._save_json("polls.json", polls)
                    return False, "Poll has expired"
                # Remove previous votes by this user
                for opt in p["options"]:
                    if user_id in opt["votes"]:
                        opt["votes"].remove(user_id)
                # Add new votes
                for idx in option_indices:
                    if 0 <= idx < len(p["options"]):
                        p["options"][idx]["votes"].append(user_id)
                self._save_json("polls.json", polls)
                return True, "Vote recorded!"
        return False, "Poll not found"

    def get_polls(self, club_id: str) -> list[dict]:
        polls = self._load_json("polls.json")
        club_polls = [p for p in polls if p["club_id"] == club_id]
        # Expire polls
        now = datetime.now()
        for p in club_polls:
            if p.get("is_active", True):
                try:
                    if datetime.fromisoformat(p.get("expires_at", "2099-01-01")) < now:
                        p["is_active"] = False
                except Exception:
                    pass
        club_polls.sort(key=lambda p: p["created_at"], reverse=True)
        users = self.storage.load_users()
        enriched = []
        for p in club_polls:
            author = users.get(p["user_id"])
            enriched.append({**p, "author_name": author.name if author else "Unknown"})
        return enriched

    # ═══════════════════════════════════════════════════════════════
    # FAN COMMUNITIES (Genre/Author-based)
    # ═══════════════════════════════════════════════════════════════

    def get_fan_communities(self) -> list[dict]:
        """Auto-generate fan communities based on existing clubs and genres."""
        clubs = self._load_json("clubs.json")
        categories = Counter()
        for c in clubs:
            categories[c.get("category", "General")] += 1
        return [
            {"name": cat, "club_count": count, "type": "genre"}
            for cat, count in categories.most_common()
        ]
