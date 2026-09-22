"""Tests for Book-Tale Communities service (clubs + polls).

Rewritten against the real app.services.social.communities API:
- create_club(name, description, owner_id) -> (ok, msg, club)
- join_club / leave_club(club_id, user_id) -> (ok, msg)
- get_club(club_id) -> club | None
- create_poll(club_id, user_id, question, options, ...) -> (ok, msg, poll)
- vote_poll(poll_id, user_id, option_indices) -> (ok, msg)
  (re-voting is allowed: previous votes are removed first; option votes are lists)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.social.communities import Communities


@pytest.fixture()
def mgr() -> Communities:
    storage = MagicMock()
    storage.load_users.return_value = {}
    return Communities(storage)


class TestBookClubs:
    def test_create_club(self, mgr: Communities) -> None:
        with patch.object(mgr, "_save_json"):
            ok, _msg, club = mgr.create_club("Fantasy Readers", "Read fantasy books", "u1")
            assert ok is True
            assert club["name"] == "Fantasy Readers"

    def test_create_club_empty_name(self, mgr: Communities) -> None:
        ok, _msg, _ = mgr.create_club("  ", "desc", "u1")
        assert ok is False

    def test_join_club(self, mgr: Communities) -> None:
        club = {"club_id": "C1", "members": [], "owner_id": "u1"}
        with patch.object(mgr, "_load_json", return_value=[club]), patch.object(mgr, "_save_json"):
            ok, _msg = mgr.join_club("C1", "u2")
            assert ok is True

    def test_join_club_already_member(self, mgr: Communities) -> None:
        club = {"club_id": "C1", "members": ["u2"], "owner_id": "u1"}
        with patch.object(mgr, "_load_json", return_value=[club]):
            ok, _msg = mgr.join_club("C1", "u2")
            assert ok is False or "already" in _msg.lower()

    def test_leave_club(self, mgr: Communities) -> None:
        club = {"club_id": "C1", "members": ["u1", "u2"], "owner_id": "u1"}
        with patch.object(mgr, "_load_json", return_value=[club]), patch.object(mgr, "_save_json"):
            ok, _msg = mgr.leave_club("C1", "u2")
            assert ok is True

    def test_get_club(self, mgr: Communities) -> None:
        club = {"club_id": "C1", "name": "Test"}
        with patch.object(mgr, "_load_json", return_value=[club]):
            result = mgr.get_club("C1")
            assert result is not None
            assert result["name"] == "Test"

    def test_get_club_not_found(self, mgr: Communities) -> None:
        with patch.object(mgr, "_load_json", return_value=[]):
            assert mgr.get_club("NONEXISTENT") is None


class TestPolls:
    def test_create_poll(self, mgr: Communities) -> None:
        with patch.object(mgr, "_save_json"):
            ok, _msg, poll = mgr.create_poll(
                "C1", "u1", "Best fantasy book?", ["LOTR", "HP", "Narnia"]
            )
            assert ok is True
            assert poll["question"] == "Best fantasy book?"
            assert len(poll["options"]) == 3

    def test_create_poll_needs_two_options(self, mgr: Communities) -> None:
        ok, _msg, _ = mgr.create_poll("C1", "u1", "Only one?", ["LOTR"])
        assert ok is False

    def test_vote_poll(self, mgr: Communities) -> None:
        poll = {
            "poll_id": "P1",
            "is_active": True,
            "expires_at": "2099-01-01T00:00:00",
            "options": [
                {"text": "A", "votes": []},
                {"text": "B", "votes": []},
            ],
        }
        with patch.object(mgr, "_load_json", return_value=[poll]), patch.object(mgr, "_save_json"):
            ok, _msg = mgr.vote_poll("P1", "u1", [0])
            assert ok is True
            assert poll["options"][0]["votes"] == ["u1"]

    def test_vote_poll_revotes_clear_previous(self, mgr: Communities) -> None:
        # vote_poll removes previous votes before adding new ones (no rejection)
        poll = {
            "poll_id": "P1",
            "is_active": True,
            "expires_at": "2099-01-01T00:00:00",
            "options": [
                {"text": "A", "votes": ["u1"]},
                {"text": "B", "votes": []},
            ],
        }
        with patch.object(mgr, "_load_json", return_value=[poll]), patch.object(mgr, "_save_json"):
            ok, _msg = mgr.vote_poll("P1", "u1", [1])
            assert ok is True
            assert poll["options"][0]["votes"] == []
            assert poll["options"][1]["votes"] == ["u1"]

    def test_vote_poll_not_found(self, mgr: Communities) -> None:
        with patch.object(mgr, "_load_json", return_value=[]):
            ok, msg = mgr.vote_poll("NOPE", "u1", [0])
            assert ok is False
            assert "not found" in msg.lower()

    def test_vote_poll_ended(self, mgr: Communities) -> None:
        poll = {
            "poll_id": "P1",
            "is_active": False,
            "options": [{"text": "A", "votes": []}],
        }
        with patch.object(mgr, "_load_json", return_value=[poll]):
            ok, msg = mgr.vote_poll("P1", "u1", [0])
            assert ok is False
            assert "ended" in msg.lower()
