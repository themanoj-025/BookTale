"""Tests for Book-Tale Gamification service.

Rewritten against the real app.services.social.gamification API:
- add_points(user_id, points, reason) -> (total_points, level)
- LEVELS: New Reader(0) / Bronze(50) / Silver(200) / Gold(500) / Platinum(1000)
  / Diamond(2500) / Legendary(5000)
- get_achievements returns the FULL catalog with per-item unlocked flags
- check_achievements reads reviews/posts/follows from storage
- get_user_gamification returns a shaped dict (points/level/next_level/...)
- hooks: on_review_created / on_post_created / on_comment_created / on_helpful_vote
Each test uses a unique user_id: gamification state persists in a shared JSON file.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.social.gamification import ACHIEVEMENTS, Gamification

pytestmark = pytest.mark.unit


@pytest.fixture()
def storage() -> MagicMock:
    st = MagicMock()
    st.load_reviews.return_value = []
    st.load_posts.return_value = []
    st.load_follows.return_value = []
    return st


@pytest.fixture()
def gamification(storage) -> Gamification:
    return Gamification(storage=storage)


class TestPoints:
    def test_add_points_accumulates(self, gamification: Gamification) -> None:
        total, _level = gamification.add_points("pts-a", 10, "test")
        assert total == 10
        total, _level = gamification.add_points("pts-a", 5, "test")
        assert total == 15

    def test_level_bronze_at_50(self, gamification: Gamification) -> None:
        _total, level = gamification.add_points("bronze-user", 50, "reach bronze")
        assert level == "Bronze Reader"

    def test_level_new_reader_at_zero(self, gamification: Gamification) -> None:
        ud = gamification.get_user_gamification("fresh-reader")
        assert ud["points"] == 0
        assert ud["level"] == "New Reader"
        assert ud["next_level"] == "Bronze Reader"

    def test_negative_points_recalculates_level(self, gamification: Gamification) -> None:
        gamification.add_points("debit-user", 100, "grant")
        total, level = gamification.add_points("debit-user", -50, "debit")
        assert total == 50
        assert level == "Bronze Reader"


class TestAchievements:
    def test_get_achievements_returns_full_catalog(self, gamification: Gamification) -> None:
        result = gamification.get_achievements("nobody-here")
        assert len(result) == len(ACHIEVEMENTS)
        assert all(a["unlocked"] is False for a in result)

    def test_check_achievements_counts_storage_data(
        self, gamification: Gamification, storage
    ) -> None:
        storage.load_reviews.return_value = [
            {"user_id": "reviewer", "helpful_votes": ["v1", "v2"]},
        ]
        unlocked = gamification.check_achievements("reviewer")
        assert isinstance(unlocked, list)
        ids = [a["id"] for a in unlocked]
        assert "first_review" in ids  # one review written

    def test_on_review_created_grants_points_and_counter(
        self, gamification: Gamification, storage
    ) -> None:
        # The hook increments the counter but does NOT register the review in
        # storage — seed it so check_achievements sees first_review criteria met.
        storage.load_reviews.return_value = [
            {"user_id": "hook-reviewer", "helpful_votes": []},
        ]
        gamification.on_review_created("hook-reviewer")
        ud = gamification.get_user_gamification("hook-reviewer")
        assert ud["points"] >= 10  # 10 pts for the review (+ achievement bonus)
        assert ud["unlocked_achievements"] >= 1  # first_review unlocked

    def test_on_post_created_grants_points(
        self, gamification: Gamification, storage
    ) -> None:
        gamification.on_post_created("hook-poster")
        ud = gamification.get_user_gamification("hook-poster")
        assert ud["points"] >= 5

    def test_on_comment_created_grants_points(self, gamification: Gamification) -> None:
        gamification.on_comment_created("hook-commenter")
        ud = gamification.get_user_gamification("hook-commenter")
        assert ud["points"] >= 2

    def test_on_helpful_vote(self, gamification: Gamification, storage) -> None:
        gamification.on_helpful_vote("vote-magnet")
        ud = gamification.get_user_gamification("vote-magnet")
        assert ud["points"] >= 3


class TestStreaks:
    def test_check_streak_returns_tuple(self, gamification: Gamification) -> None:
        current, longest = gamification.check_streak("streak-user")
        assert isinstance(current, int)
        assert isinstance(longest, int)
        assert current >= 0 and longest >= 0


class TestLeaderboard:
    def test_get_leaderboard_sorted_desc(self, gamification: Gamification) -> None:
        gamification.add_points("board-low", 10, "test")
        gamification.add_points("board-high", 100, "test")
        board = gamification.get_leaderboard()
        assert isinstance(board, list)
        points = [entry["points"] for entry in board]
        assert points == sorted(points, reverse=True)
        ids = [entry["user_id"] for entry in board]
        assert "board-low" in ids and "board-high" in ids

    def test_get_user_gamification_shape(self, gamification: Gamification) -> None:
        ud = gamification.get_user_gamification("shape-user")
        for key in (
            "user_id",
            "points",
            "level",
            "next_level",
            "streak_days",
            "longest_streak",
            "achievements",
            "unlocked_achievements",
            "total_achievements",
        ):
            assert key in ud
        assert ud["total_achievements"] == len(ACHIEVEMENTS)
