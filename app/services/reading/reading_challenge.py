"""
reading_challenge.py - Reading Challenge / Yearly Reading Goals

Features:
- Set yearly reading goals (number of books)
- Track progress throughout the year
- Weekly/monthly reading streaks
- Dashboard widget showing progress
- Reading pace calculator
"""

import json
import os
from collections import defaultdict
from datetime import datetime

from app.config.settings import Config
from app.core.logger import log
from app.storage.storage import Storage


class ReadingChallenge:
    """Manages yearly reading goals and progress tracking."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def _get_challenge_path(self) -> str:
        return os.path.join(Config.DATA_DIR, "reading_challenges.json")

    def _load_challenges(self) -> dict:
        path = self._get_challenge_path()
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_challenges(self, data: dict) -> None:
        path = self._get_challenge_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def set_goal(self, user_id: str, year: int, goal: int) -> tuple[bool, str]:
        """Set a yearly reading goal for a user."""
        if goal < 1:
            return False, "Goal must be at least 1 book"
        if goal > 1000:
            return False, "Goal cannot exceed 1000 books"
        data = self._load_challenges()
        key = f"{user_id}_{year}"
        now = datetime.now().isoformat()
        if key not in data:
            data[key] = {
                "user_id": user_id,
                "year": year,
                "goal": goal,
                "books_read": [],  # list of book_ids read this year
                "created_at": now,
                "updated_at": now,
            }
        else:
            data[key]["goal"] = goal
            data[key]["updated_at"] = now
        self._save_challenges(data)
        log(f"Set reading goal: {goal} books for {year}", user_id)
        return True, f"Goal set to {goal} books for {year}!"

    def get_goal(self, user_id: str, year: int | None = None) -> dict:
        """Get a user's reading goal for a given year (defaults to current year)."""
        if year is None:
            year = datetime.now().year
        key = f"{user_id}_{year}"
        data = self._load_challenges()
        entry = data.get(
            key,
            {
                "user_id": user_id,
                "year": year,
                "goal": 0,
                "books_read": [],
                "created_at": "",
                "updated_at": "",
            },
        )
        # Recalculate books_read from transactions
        books_read = self._count_books_read(user_id, year)
        entry["books_read"] = books_read
        entry["progress"] = len(books_read)
        entry["goal"] = entry.get("goal", 0)
        entry["percentage"] = (
            round(len(books_read) / entry["goal"] * 100, 1) if entry.get("goal", 0) > 0 else 0
        )
        entry["remaining"] = max(0, entry["goal"] - len(books_read))
        # Calculate pace
        entry = self._add_pace_info(entry, year)
        return entry

    def _count_books_read(self, user_id: str, year: int) -> list:
        """Count unique books a user has read (returned) in a given year."""
        txns = self.storage.load_transactions()
        books_set = set()
        for t in txns:
            if t.get("user_id") == user_id and t["type"] == "return":
                try:
                    dt = datetime.fromisoformat(t.get("return_date", ""))
                    if dt.year == year:
                        books_set.add(t["book_id"])
                except (ValueError, TypeError):
                    pass
        # Also check reading_progress if available
        try:
            from app.services.reading.reading_progress import ReadingProgress

            rp = ReadingProgress(self.storage)
            progress_data = rp._load_progress()
            for pid, pdata in progress_data.items():
                parts = pid.split("_", 1)
                if len(parts) == 2 and parts[0] == user_id:
                    try:
                        updated = datetime.fromisoformat(pdata.get("updated_at", ""))
                        if updated.year == year and pdata.get("finished", False):
                            books_set.add(parts[1])
                    except Exception:
                        pass
        except ImportError:
            pass
        return list(books_set)

    def _add_pace_info(self, entry: dict, year: int) -> dict:
        """Calculate reading pace and projections."""
        goal = entry.get("goal", 0)
        progress = entry.get("progress", 0)
        now = datetime.now()
        start_of_year = datetime(year, 1, 1)
        days_passed = max(1, (now - start_of_year).days)
        days_remaining = max(0, (datetime(year, 12, 31) - now).days)

        pace = progress / days_passed * 30 if days_passed > 0 else 0  # books per month

        projected = round(pace / 30 * 365) if pace > 0 else 0
        needed_pace = (
            max(0, (goal - progress) / max(1, days_remaining / 30))
            if days_remaining > 0 and goal > progress
            else 0
        )

        entry["pace"] = round(pace, 1)
        entry["projected_total"] = projected
        entry["needed_pace"] = round(needed_pace, 1)
        entry["days_passed"] = days_passed
        entry["days_remaining"] = days_remaining
        entry["on_track"] = projected >= goal if goal > 0 else False

        return entry

    def get_progress_chart_data(self, user_id: str, year: int | None = None) -> dict:
        """Get monthly reading progress for chart visualization."""
        if year is None:
            year = datetime.now().year
        txns = self.storage.load_transactions()
        monthly = defaultdict(int)
        for t in txns:
            if t.get("user_id") == user_id and t["type"] == "return":
                try:
                    dt = datetime.fromisoformat(t.get("return_date", ""))
                    if dt.year == year:
                        monthly[dt.month] += 1
                except Exception:
                    pass

        months = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        labels = months[: datetime.now().month]
        values = [monthly.get(i + 1, 0) for i in range(len(labels))]
        cumulative = []
        running = 0
        for v in values:
            running += v
            cumulative.append(running)
        return {"labels": labels, "monthly": values, "cumulative": cumulative}

    def get_leaderboard(self, year: int | None = None, top_n: int = 10) -> list[dict]:
        """Get leaderboard of readers for a given year."""
        if year is None:
            year = datetime.now().year
        data = self._load_challenges()
        users = self.storage.load_users()
        results = []

        # Count books read per user from transactions
        txns = self.storage.load_transactions()
        user_counts = defaultdict(set)
        for t in txns:
            if t["type"] == "return":
                try:
                    dt = datetime.fromisoformat(t.get("return_date", ""))
                    if dt.year == year:
                        user_counts[t["user_id"]].add(t["book_id"])
                except Exception:
                    pass

        for uid, books_set in user_counts.items():
            user = users.get(uid)
            entry = data.get(f"{uid}_{year}", {})
            goal = entry.get("goal", 0)
            count = len(books_set)
            results.append(
                {
                    "user_id": uid,
                    "name": user.name if user else "Unknown",
                    "count": count,
                    "goal": goal,
                    "percentage": round(count / goal * 100, 1) if goal > 0 else 0,
                }
            )

        results.sort(key=lambda x: x["count"], reverse=True)
        # Add rank
        for i, r in enumerate(results[:top_n], 1):
            r["rank"] = i
        return results[:top_n]

    def get_user_challenges_summary(self, user_id: str) -> dict:
        """Get summary of all reading challenges across years."""
        summaries = []
        current_year = datetime.now().year
        for year_offset in range(3):  # past 2 years + current
            year = current_year - year_offset
            entry = self.get_goal(user_id, year)
            summaries.append(entry)
        return {"years": summaries}
