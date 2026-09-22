"""Tests for Book-Tale Wishlist service.

Rewritten against the real app.services.reading.wishlist API:
- add_suggestion(user_id, title, author=...) -> (ok, msg, suggestion)
- vote_suggestion(suggestion_id, user_id, vote: "up"|"down") -> (ok, msg, summary)
  (re-voting removes the previous vote then records the new one)
- moderate_suggestion(suggestion_id, admin_id, status) -> (ok, msg)
- get_suggestions(status=..., ...) -> (page_items, total)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.reading.wishlist import Wishlist

pytestmark = pytest.mark.unit


@pytest.fixture()
def storage() -> MagicMock:
    st = MagicMock()
    st.load_users.return_value = {}
    return st


@pytest.fixture()
def mgr(storage) -> Wishlist:
    return Wishlist(storage)


class TestAddSuggestion:
    def test_add_suggestion(self, mgr: Wishlist) -> None:
        with (
            patch.object(mgr, "_load_suggestions", return_value=[]),
            patch.object(mgr, "_save_suggestions"),
        ):
            ok, _msg, s = mgr.add_suggestion("u1", "The Hobbit", "Tolkien")
            assert ok is True
            assert s["title"] == "The Hobbit"

    def test_add_suggestion_empty_title(self, mgr: Wishlist) -> None:
        ok, _msg, _ = mgr.add_suggestion("u1", "  ")
        assert ok is False


class TestGetSuggestions:
    def test_get_suggestions_filters_by_status(self, mgr: Wishlist) -> None:
        suggs = [
            {"suggestion_id": "W1", "status": "pending", "user_id": "u1", "title": "A"},
            {"suggestion_id": "W2", "status": "approved", "user_id": "u1", "title": "B"},
        ]
        with (
            patch.object(mgr, "_load_suggestions", return_value=suggs),
            patch.object(mgr, "_save_suggestions"),
        ):
            result, total = mgr.get_suggestions(status="pending")
            assert total == 1
            assert result[0]["suggestion_id"] == "W1"

    def test_get_suggestions_scores_votes(self, mgr: Wishlist) -> None:
        suggs = [
            {
                "suggestion_id": "W1",
                "status": "pending",
                "user_id": "u1",
                "upvotes": ["a", "b"],
                "downvotes": [],
            },
        ]
        with (
            patch.object(mgr, "_load_suggestions", return_value=suggs),
            patch.object(mgr, "_save_suggestions"),
        ):
            result, _total = mgr.get_suggestions()
            assert result[0]["score"] == 2


class TestVoteSuggestion:
    def test_vote_up(self, mgr: Wishlist) -> None:
        sugg = {
            "suggestion_id": "W1",
            "upvotes": [],
            "downvotes": [],
        }
        with (
            patch.object(mgr, "_load_suggestions", return_value=[sugg]),
            patch.object(mgr, "_save_suggestions"),
        ):
            ok, _msg, summary = mgr.vote_suggestion("W1", "u1", vote="up")
            assert ok is True
            assert summary["score"] == 1
            assert summary["upvotes"] == 1
            assert summary["user_vote"] == "up"

    def test_vote_down(self, mgr: Wishlist) -> None:
        sugg = {"suggestion_id": "W1", "upvotes": [], "downvotes": []}
        with (
            patch.object(mgr, "_load_suggestions", return_value=[sugg]),
            patch.object(mgr, "_save_suggestions"),
        ):
            ok, _msg, summary = mgr.vote_suggestion("W1", "u1", vote="down")
            assert ok is True
            assert summary["score"] == -1

    def test_revote_switches_vote(self, mgr: Wishlist) -> None:
        # vote_suggestion removes any prior vote before recording the new one
        sugg = {"suggestion_id": "W1", "upvotes": ["u1"], "downvotes": []}
        with (
            patch.object(mgr, "_load_suggestions", return_value=[sugg]),
            patch.object(mgr, "_save_suggestions"),
        ):
            ok, _msg, summary = mgr.vote_suggestion("W1", "u1", vote="down")
            assert ok is True
            assert summary["user_vote"] == "down"
            assert summary["score"] == -1

    def test_vote_invalid_direction(self, mgr: Wishlist) -> None:
        ok, msg, _ = mgr.vote_suggestion("W1", "u1", vote="sideways")
        assert ok is False
        assert "up" in msg and "down" in msg

    def test_vote_missing_suggestion(self, mgr: Wishlist) -> None:
        with patch.object(mgr, "_load_suggestions", return_value=[]):
            ok, msg, _ = mgr.vote_suggestion("NOPE", "u1", vote="up")
            assert ok is False
            assert "not found" in msg.lower()


class TestModeration:
    def test_approve_suggestion(self, mgr: Wishlist) -> None:
        sugg = {"suggestion_id": "W1", "status": "pending", "title": "A"}
        with (
            patch.object(mgr, "_load_suggestions", return_value=[sugg]),
            patch.object(mgr, "_save_suggestions"),
            patch.object(mgr, "_auto_add_book"),  # approval triggers auto-add
        ):
            ok, _msg = mgr.moderate_suggestion("W1", "admin-1", "approved")
            assert ok is True
            assert sugg["status"] == "approved"

    def test_reject_suggestion(self, mgr: Wishlist) -> None:
        sugg = {"suggestion_id": "W1", "status": "pending", "title": "A"}
        with (
            patch.object(mgr, "_load_suggestions", return_value=[sugg]),
            patch.object(mgr, "_save_suggestions"),
        ):
            ok, _msg = mgr.moderate_suggestion("W1", "admin-1", "rejected")
            assert ok is True
            assert sugg["status"] == "rejected"

    def test_moderate_invalid_status(self, mgr: Wishlist) -> None:
        ok, msg = mgr.moderate_suggestion("W1", "admin-1", "banished")
        assert ok is False
        assert "invalid status" in msg.lower()
