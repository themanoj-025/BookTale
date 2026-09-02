"""Tests for Book-Tale Gamification service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.social.gamification import Gamification, LEVELS, ACHIEVEMENTS


@pytest.fixture()
def mgr() -> Gamification:
    storage = MagicMock()
    return Gamification(storage)


class TestLevels:
    def test_get_level_new_reader(self, mgr: Gamification) -> None:
        result = mgr.get_level("u1")
        assert result["name"] == "New Reader"

    def test_level_definitions(self) -> None:
        assert len(LEVELS) >= 7
        assert LEVELS[0]["name"] == "New Reader"
        assert LEVELS[-1]["name"] == "Legendary Reader"

    def test_achievement_definitions(self) -> None:
        assert len(ACHIEVEMENTS) >= 5
        ids = [a["id"] for a in ACHIEVEMENTS]
        assert "first_review" in ids


class TestPoints:
    def test_add_points(self, mgr: Gamification) -> None:
        with patch.object(mgr, "_load_user_points", return_value=0), patch.object(
            mgr, "_save_user_points"
        ):
            mgr.add_points("u1", 10, "review")
            mgr._save_user_points.assert_called_once()

    def test_get_total_points(self, mgr: Gamification) -> None:
        with patch.object(mgr, "_load_user_points", return_value=150):
            result = mgr.get_total_points("u1")
            assert result == 150


class TestAchievements:
    def test_check_achievements_first_review(self, mgr: Gamification) -> None:
        with patch.object(mgr, "_load_user_points", return_value=10), patch.object(
            mgr, "_load_user_achievements", return_value=[]
        ), patch.object(mgr, "_save_user_achievements"):
            new = mgr.check_achievements("u1", {"reviews": 1})
            assert isinstance(new, list)

    def test_no_new_achievements(self, mgr: Gamification) -> None:
        with patch.object(mgr, "_load_user_points", return_value=0), patch.object(
            mgr, "_load_user_achievements", return_value=["first_review"]
        ):
            new = mgr.check_achievements("u1", {"reviews": 0})
            assert len(new) == 0


class TestLeaderboard:
    def test_get_leaderboard(self, mgr: Gamification) -> None:
        with patch.object(mgr, "_load_all_points", return_value=[
            {"user_id": "u1", "points": 100},
            {"user_id": "u2", "points": 50},
            {"user_id": "u3", "points": 200},
        ]):
            result = mgr.get_leaderboard()
            assert len(result) == 3
            assert result[0]["user_id"] == "u3"  # Highest first
