"""
gamification.py - Points, Levels, Achievements & Leaderboards

Features:
- Points for reviews, posts, comments, likes received
- Reviewer levels (Bronze -> Diamond)
- Achievement badges
- Top critic leaderboard
- Daily reading/review streaks
"""

import json
import os
from collections import Counter
from datetime import date

from app.config.settings import Config
from app.core.logger import log
from app.storage.storage import Storage

# LEVEL CONFIG

LEVELS = [
    {"name": "New Reader", "min_points": 0, "icon": "seedling"},
    {"name": "Bronze Reader", "min_points": 50, "icon": "award"},
    {"name": "Silver Reader", "min_points": 200, "icon": "star"},
    {"name": "Gold Reader", "min_points": 500, "icon": "trophy"},
    {"name": "Platinum Reader", "min_points": 1000, "icon": "gem"},
    {"name": "Diamond Reader", "min_points": 2500, "icon": "diamond"},
    {"name": "Legendary Reader", "min_points": 5000, "icon": "lightning"},
]

ACHIEVEMENTS = [
    {
        "id": "first_review",
        "name": "First Review",
        "desc": "Write your first book review",
        "icon": "star",
        "points": 10,
    },
    {
        "id": "five_reviews",
        "name": "Critic",
        "desc": "Write 5 reviews",
        "icon": "stars",
        "points": 50,
    },
    {
        "id": "ten_reviews",
        "name": "Book Critic",
        "desc": "Write 10 reviews",
        "icon": "bookmark-star",
        "points": 100,
    },
    {
        "id": "first_post",
        "name": "First Post",
        "desc": "Create your first post",
        "icon": "chat-square",
        "points": 10,
    },
    {
        "id": "ten_posts",
        "name": "Social Butterfly",
        "desc": "Create 10 posts",
        "icon": "chat-square-fill",
        "points": 50,
    },
    {
        "id": "first_follower",
        "name": "Getting Popular",
        "desc": "Get your first follower",
        "icon": "people",
        "points": 20,
    },
    {
        "id": "ten_followers",
        "name": "Influencer",
        "desc": "Get 10 followers",
        "icon": "people-fill",
        "points": 100,
    },
    {
        "id": "first_list",
        "name": "Curator",
        "desc": "Create your first book list",
        "icon": "list-stars",
        "points": 20,
    },
    {
        "id": "club_member",
        "name": "Book Clubber",
        "desc": "Join a book club",
        "icon": "people",
        "points": 30,
    },
    {
        "id": "first_poll",
        "name": "Pollster",
        "desc": "Create your first poll",
        "icon": "bar-chart",
        "points": 25,
    },
    {
        "id": "streak_3",
        "name": "3-Day Streak",
        "desc": "Active for 3 days in a row",
        "icon": "fire",
        "points": 30,
    },
    {
        "id": "streak_7",
        "name": "Weekly Warrior",
        "desc": "Active for 7 days in a row",
        "icon": "fire",
        "points": 100,
    },
    {
        "id": "streak_30",
        "name": "Monthly Champion",
        "desc": "Active for 30 days in a row",
        "icon": "trophy-fill",
        "points": 500,
    },
    {
        "id": "helpful_5",
        "name": "Helpful Reviewer",
        "desc": "Get 5 helpful votes on reviews",
        "icon": "hand-thumbs-up",
        "points": 50,
    },
    {
        "id": "top_critic",
        "name": "Top Critic",
        "desc": "Be in the top 10 reviewers",
        "icon": "trophy",
        "points": 200,
    },
]


class Gamification:
    """Manages points, levels, achievements, streaks, and leaderboards."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def _get_gamification_path(self) -> str:
        return os.path.join(Config.DATA_DIR, "gamification.json")

    def _load_gamification(self) -> dict:
        path = self._get_gamification_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_gamification(self, data: dict) -> None:
        path = self._get_gamification_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _get_user_data(self, user_id: str) -> dict:
        data = self._load_gamification()
        if user_id not in data:
            data[user_id] = {
                "points": 0,
                "level": "New Reader",
                "achievements": [],
                "total_reviews": 0,
                "total_posts": 0,
                "total_comments": 0,
                "helpful_votes_received": 0,
                "streak_days": 0,
                "longest_streak": 0,
                "last_active_date": "",
                "daily_activity": {},
            }
        return data[user_id]

    def _save_user_data(self, user_id: str, user_data: dict) -> None:
        data = self._load_gamification()
        data[user_id] = user_data
        self._save_gamification(data)

    # ═══════════════════════════════════════════════════════════════
    # POINTS
    # ═══════════════════════════════════════════════════════════════

    def add_points(self, user_id: str, points: int, reason: str) -> tuple[int, str]:
        """Add points to a user. Returns (total_points, new_level)."""
        ud = self._get_user_data(user_id)
        ud["points"] += points
        new_level = self._calculate_level(ud["points"])
        ud["level"] = new_level
        self._save_user_data(user_id, ud)
        log(f"+{points} pts ({reason})", user_id, f"level:{new_level}")
        return ud["points"], new_level

    def _calculate_level(self, points: int) -> str:
        for i in range(len(LEVELS) - 1, -1, -1):
            if points >= LEVELS[i]["min_points"]:
                return LEVELS[i]["name"]
        return "New Reader"

    # ═══════════════════════════════════════════════════════════════
    # STREAKS
    # ═══════════════════════════════════════════════════════════════

    def check_streak(self, user_id: str) -> tuple[int, int]:
        """Check and update daily streak. Returns (current_streak, longest_streak)."""
        ud = self._get_user_data(user_id)
        today = date.today().isoformat()
        last_active = ud.get("last_active_date", "")

        if last_active == today:
            pass  # Already active today
        elif last_active:
            try:
                last_date = date.fromisoformat(last_active)
                diff = (date.today() - last_date).days
                if diff == 1:
                    ud["streak_days"] += 1
                elif diff > 1:
                    ud["streak_days"] = 1  # Reset streak
            except:
                ud["streak_days"] = 1
        else:
            ud["streak_days"] = 1

        ud["last_active_date"] = today
        if ud["streak_days"] > ud.get("longest_streak", 0):
            ud["longest_streak"] = ud["streak_days"]

        # Track daily activity
        month_key = today[:7]
        if "daily_activity" not in ud:
            ud["daily_activity"] = {}
        if month_key not in ud["daily_activity"]:
            ud["daily_activity"][month_key] = 0
        ud["daily_activity"][month_key] += 1

        self._save_user_data(user_id, ud)
        return ud["streak_days"], ud.get("longest_streak", 0)

    # ═══════════════════════════════════════════════════════════════
    # ACHIEVEMENTS
    # ═══════════════════════════════════════════════════════════════

    def check_achievements(self, user_id: str) -> list[dict]:
        """Check and award any newly unlocked achievements."""
        ud = self._get_user_data(user_id)
        unlocked = ud.get("achievements", [])
        newly_unlocked = []

        # Count stats from actual data
        reviews = self.storage.load_reviews()
        user_reviews = [r for r in reviews if r["user_id"] == user_id]
        helpful_votes = sum(len(r.get("helpful_votes", [])) for r in user_reviews)
        posts = self.storage.load_posts()
        user_posts = [p for p in posts if p["user_id"] == user_id]
        follows = self.storage.load_follows()
        followers = len(set(f["follower_id"] for f in follows if f["following_id"] == user_id))

        clubs_file = os.path.join(Config.DATA_DIR, "clubs.json")
        clubs = []
        try:
            with open(clubs_file, "r", encoding="utf-8") as f:
                clubs = json.load(f)
        except Exception:
            pass
        user_clubs = [c for c in clubs if user_id in c.get("members", [])]

        lists_file = os.path.join(Config.DATA_DIR, "book_lists.json")
        user_lists = []
        try:
            with open(lists_file, "r", encoding="utf-8") as f:
                all_lists = json.load(f)
            user_lists = [l for l in all_lists if l["owner_id"] == user_id]
        except Exception:
            pass

        polls_file = os.path.join(Config.DATA_DIR, "polls.json")
        user_polls = []
        try:
            with open(polls_file, "r", encoding="utf-8") as f:
                all_polls = json.load(f)
            user_polls = [p for p in all_polls if p["user_id"] == user_id]
        except Exception:
            pass

        streak_days = ud.get("streak_days", 0)

        # Check each achievement
        checks = {
            "first_review": len(user_reviews) >= 1,
            "five_reviews": len(user_reviews) >= 5,
            "ten_reviews": len(user_reviews) >= 10,
            "first_post": len(user_posts) >= 1,
            "ten_posts": len(user_posts) >= 10,
            "first_follower": followers >= 1,
            "ten_followers": followers >= 10,
            "first_list": len(user_lists) >= 1,
            "club_member": len(user_clubs) >= 1,
            "first_poll": len(user_polls) >= 1,
            "streak_3": streak_days >= 3,
            "streak_7": streak_days >= 7,
            "streak_30": streak_days >= 30,
            "helpful_5": helpful_votes >= 5,
        }

        for ach in ACHIEVEMENTS:
            if ach["id"] not in unlocked and checks.get(ach["id"], False):
                unlocked.append(ach["id"])
                ud["points"] += ach["points"]
                newly_unlocked.append(ach)
                log(f"Achievement unlocked: {ach['name']}", user_id)

        if newly_unlocked:
            ud["level"] = self._calculate_level(ud["points"])
            self._save_user_data(user_id, ud)

        return newly_unlocked

    def get_achievements(self, user_id: str) -> list[dict]:
        """Get all achievements with unlock status."""
        ud = self._get_user_data(user_id)
        unlocked = set(ud.get("achievements", []))
        result = []
        for ach in ACHIEVEMENTS:
            result.append(
                {
                    **ach,
                    "unlocked": ach["id"] in unlocked,
                    "unlocked_at": "",  # Could track timestamps
                }
            )
        return result

    # ═══════════════════════════════════════════════════════════════
    # LEADERBOARD
    # ═══════════════════════════════════════════════════════════════

    def get_leaderboard(self, top_n: int = 20, sort_by: str = "points") -> list[dict]:
        """Get the top users ranked by points or reviews."""
        data = self._load_gamification()
        users = self.storage.load_users()

        if sort_by == "reviews":
            reviews = self.storage.load_reviews()
            review_counts = Counter(r["user_id"] for r in reviews)
            ranked = sorted(review_counts.items(), key=lambda x: x[1], reverse=True)
        else:
            ranked = sorted(data.items(), key=lambda x: x[1].get("points", 0), reverse=True)

        result = []
        for rank, (uid, _) in enumerate(ranked[:top_n], 1):
            user = users.get(uid)
            ud = data.get(uid, {})
            result.append(
                {
                    "rank": rank,
                    "user_id": uid,
                    "name": user.name if user else "Unknown",
                    "points": ud.get("points", 0),
                    "level": ud.get("level", "New Reader"),
                    "reviews": ud.get("total_reviews", 0),
                    "posts": ud.get("total_posts", 0),
                    "achievements": len(ud.get("achievements", [])),
                    "streak": ud.get("streak_days", 0),
                }
            )
        return result

    # ═══════════════════════════════════════════════════════════════
    # USER STATS
    # ═══════════════════════════════════════════════════════════════

    def get_user_gamification(self, user_id: str) -> dict:
        """Get full gamification data for a user."""
        self.check_streak(user_id)
        ud = self._get_user_data(user_id)

        # Calculate next level
        current_level = ud.get("level", "New Reader")
        next_level = None
        next_points_needed = 0
        for i, lvl in enumerate(LEVELS):
            if lvl["name"] == current_level and i + 1 < len(LEVELS):
                next_level = LEVELS[i + 1]["name"]
                next_points_needed = LEVELS[i + 1]["min_points"] - ud["points"]

        achievements = self.get_achievements(user_id)
        unlocked_count = sum(1 for a in achievements if a["unlocked"])

        return {
            "user_id": user_id,
            "points": ud.get("points", 0),
            "level": current_level,
            "next_level": next_level,
            "next_level_points": next_points_needed,
            "streak_days": ud.get("streak_days", 0),
            "longest_streak": ud.get("longest_streak", 0),
            "achievements": achievements,
            "unlocked_achievements": unlocked_count,
            "total_achievements": len(ACHIEVEMENTS),
            "last_active": ud.get("last_active_date", ""),
        }

    # ═══════════════════════════════════════════════════════════════
    # EVENT HANDLERS (called from other modules)
    # ═══════════════════════════════════════════════════════════════

    def on_review_created(self, user_id: str) -> None:
        ud = self._get_user_data(user_id)
        ud["total_reviews"] += 1
        self._save_user_data(user_id, ud)
        self.add_points(user_id, 10, "Wrote a review")
        self.check_streak(user_id)
        self.check_achievements(user_id)

    def on_post_created(self, user_id: str) -> None:
        ud = self._get_user_data(user_id)
        ud["total_posts"] += 1
        self._save_user_data(user_id, ud)
        self.add_points(user_id, 5, "Created a post")
        self.check_streak(user_id)
        self.check_achievements(user_id)

    def on_comment_created(self, user_id: str) -> None:
        ud = self._get_user_data(user_id)
        ud["total_comments"] += 1
        self._save_user_data(user_id, ud)
        self.add_points(user_id, 2, "Left a comment")
        self.check_streak(user_id)

    def on_helpful_vote(self, reviewer_id: str) -> None:
        ud = self._get_user_data(reviewer_id)
        ud["helpful_votes_received"] += 1
        self._save_user_data(reviewer_id, ud)
        self.add_points(reviewer_id, 3, "Helpful vote received")
        self.check_achievements(reviewer_id)
