"""Tests for Book-Tale Wishlist service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.reading.wishlist import Wishlist


@pytest.fixture()
def mgr() -> Wishlist:
    storage = MagicMock()
    return Wishlist(storage)


class TestWishlist:
    def test_add_suggestion(self, mgr: Wishlist) -> None:
        with patch.object(mgr, "_load_suggestions", return_value=[]), patch.object(
            mgr, "_save_suggestions"
        ):
            ok, _msg, s = mgr.add_suggestion("u1", "The Hobbit", "Tolkien")
            assert ok is True
            assert s["title"] == "The Hobbit"

    def test_add_suggestion_empty_title(self, mgr: Wishlist) -> None:
        ok, _msg, _ = mgr.add_suggestion("u1", "  ")
        assert ok is False

    def test_get_suggestions(self, mgr: Wishlist) -> None:
        suggs = [
            {"suggestion_id": "W1", "status": "pending", "title": "A"},
            {"suggestion_id": "W2", "status": "approved", "title": "B"},
        ]
        with patch.object(mgr, "_load_suggestions", return_value=suggs):
            result = mgr.get_suggestions(status="pending")
            assert len(result) == 1

    def test_vote_up(self, mgr: Wishlist) -> None:
        sugg = {
            "suggestion_id": "W1",
            "upvotes": 0,
            "upvoters": [],
            "downvotes": 0,
            "downvoters": [],
        }
        with patch.object(mgr, "_load_suggestions", return_value=[sugg]), patch.object(
            mgr, "_save_suggestions"
        ):
            ok, _msg = mgr.vote("W1", "u1", direction="up")
            assert ok is True

    def test_vote_duplicate(self, mgr: Wishlist) -> None:
        sugg = {
            "suggestion_id": "W1",
            "upvotes": 1,
            "upvoters": ["u1"],
            "downvotes": 0,
            "downvoters": [],
        }
        with patch.object(mgr, "_load_suggestions", return_value=[sugg]):
            ok, _msg = mgr.vote("W1", "u1", direction="up")
            assert ok is False or "already" in _msg.lower()

    def test_approve_suggestion(self, mgr: Wishlist) -> None:
        sugg = {"suggestion_id": "W1", "status": "pending"}
        with patch.object(mgr, "_load_suggestions", return_value=[sugg]), patch.object(
            mgr, "_save_suggestions"
        ):
            ok, _msg = mgr.approve("W1")
            assert ok is True
            assert sugg["status"] == "approved"

    def test_reject_suggestion(self, mgr: Wishlist) -> None:
        sugg = {"suggestion_id": "W1", "status": "pending"}
        with patch.object(mgr, "_load_suggestions", return_value=[sugg]), patch.object(
            mgr, "_save_suggestions"
        ):
            ok, _msg = mgr.reject("W1")
            assert ok is True
            assert sugg["status"] == "rejected"
