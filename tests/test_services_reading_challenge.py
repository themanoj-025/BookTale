"""Tests for Book-Tale ReadingChallenge service.

Rewritten against the real app.services.reading.reading_challenge API:
- set_goal(user_id, year, goal) -> (success, message); 1..1000 books
- get_goal(user_id, year=None) -> dict with goal/progress/percentage/remaining
- books_read counted from "return" transactions + finished reading progress
- get_leaderboard counts returns per user across ALL users (needs load_users)
Each test uses a unique user_id: challenge state persists in a shared JSON file.
"""

from __future__ import annotations

import pytest

from app.services.reading.reading_challenge import ReadingChallenge

pytestmark = pytest.mark.unit


@pytest.fixture()
def storage(monkeypatch):
    st = type("Storage", (), {})()
    st.load_transactions = list
    st.load_users = dict
    return st


@pytest.fixture()
def challenge(storage) -> ReadingChallenge:
    return ReadingChallenge(storage)


class TestSetGoal:
    def test_set_goal(self, challenge: ReadingChallenge) -> None:
        ok, msg = challenge.set_goal("set-goal-user", 2026, 12)
        assert ok is True
        assert "12" in msg

    def test_set_goal_zero_invalid(self, challenge: ReadingChallenge) -> None:
        ok, msg = challenge.set_goal("zero-goal-user", 2026, 0)
        assert ok is False
        assert "at least 1" in msg

    def test_set_goal_too_high(self, challenge: ReadingChallenge) -> None:
        ok, msg = challenge.set_goal("high-goal-user", 2026, 1001)
        assert ok is False
        assert "1000" in msg

    def test_set_goal_updates_existing(self, challenge: ReadingChallenge) -> None:
        challenge.set_goal("update-goal-user", 2026, 12)
        ok, _msg = challenge.set_goal("update-goal-user", 2026, 20)
        assert ok is True
        assert challenge.get_goal("update-goal-user", 2026)["goal"] == 20


class TestGetGoal:
    def test_get_goal_unset(self, challenge: ReadingChallenge) -> None:
        entry = challenge.get_goal("never-set-user", 2026)
        assert entry["goal"] == 0
        assert entry["progress"] == 0
        assert entry["percentage"] == 0

    def test_get_goal_counts_returned_books(self, challenge: ReadingChallenge, storage) -> None:
        storage.load_transactions = lambda: [
            {
                "user_id": "return-counter",
                "type": "return",
                "book_id": "b1",
                "return_date": "2026-03-01T10:00:00",
            },
            {
                "user_id": "return-counter",
                "type": "return",
                "book_id": "b2",
                "return_date": "2026-05-01T10:00:00",
            },
            {  # wrong year — must not count
                "user_id": "return-counter",
                "type": "return",
                "book_id": "b3",
                "return_date": "2025-01-01T10:00:00",
            },
            {  # not a return — must not count
                "user_id": "return-counter",
                "type": "checkout",
                "book_id": "b4",
                "return_date": "2026-05-02T10:00:00",
            },
        ]
        entry = challenge.get_goal("return-counter", 2026)
        assert entry["progress"] == 2
        assert set(entry["books_read"]) == {"b1", "b2"}

    def test_percentage_math(self, challenge: ReadingChallenge, storage) -> None:
        storage.load_transactions = lambda: [
            {
                "user_id": "pct-user",
                "type": "return",
                "book_id": f"b{i}",
                "return_date": "2026-03-01T10:00:00",
            }
            for i in range(6)
        ]
        challenge.set_goal("pct-user", 2026, 12)
        entry = challenge.get_goal("pct-user", 2026)
        assert entry["percentage"] == 50.0
        assert entry["remaining"] == 6


class TestLeaderboardAndSummary:
    def test_get_leaderboard(self, challenge: ReadingChallenge, storage) -> None:
        storage.load_transactions = lambda: [
            {
                "user_id": "board-user",
                "type": "return",
                "book_id": "b1",
                "return_date": "2026-03-01T10:00:00",
            }
        ]
        storage.load_users = dict
        board = challenge.get_leaderboard(2026)
        assert isinstance(board, list)
        assert len(board) == 1
        assert board[0]["user_id"] == "board-user"
        assert board[0]["count"] == 1
        assert board[0]["rank"] == 1

    def test_get_user_challenges_summary(self, challenge: ReadingChallenge) -> None:
        challenge.set_goal("summary-user", 2026, 12)
        summary = challenge.get_user_challenges_summary("summary-user")
        assert summary is not None
