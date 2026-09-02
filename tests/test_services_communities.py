"""Tests for Book-Tale Communities service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.social.communities import Communities


@pytest.fixture()
def mgr() -> Communities:
    storage = MagicMock()
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
        with patch.object(mgr, "_load_json", return_value=[club]), patch.object(
            mgr, "_save_json"
        ):
            ok, _msg = mgr.join_club("C1", "u2")
            assert ok is True

    def test_join_club_already_member(self, mgr: Communities) -> None:
        club = {"club_id": "C1", "members": ["u2"], "owner_id": "u1"}
        with patch.object(mgr, "_load_json", return_value=[club]):
            ok, _msg = mgr.join_club("C1", "u2")
            assert ok is False or "already" in _msg.lower()

    def test_leave_club(self, mgr: Communities) -> None:
        club = {"club_id": "C1", "members": ["u1", "u2"], "owner_id": "u1"}
        with patch.object(mgr, "_load_json", return_value=[club]), patch.object(
            mgr, "_save_json"
        ):
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
                "u1", "Best fantasy book?", ["LOTR", "HP", "Narnia"]
            )
            assert ok is True
            assert poll["question"] == "Best fantasy book?"

    def test_vote_poll(self, mgr: Communities) -> None:
        poll = {
            "poll_id": "P1",
            "options": [
                {"text": "A", "votes": 0, "voters": []},
                {"text": "B", "votes": 0, "voters": []},
            ],
        }
        with patch.object(mgr, "_load_json", return_value=[poll]), patch.object(
            mgr, "_save_json"
        ):
            ok, _msg = mgr.vote_poll("P1", 0, "u1")
            assert ok is True

    def test_vote_poll_already_voted(self, mgr: Communities) -> None:
        poll = {
            "poll_id": "P1",
            "options": [
                {"text": "A", "votes": 1, "voters": ["u1"]},
                {"text": "B", "votes": 0, "voters": []},
            ],
        }
        with patch.object(mgr, "_load_json", return_value=[poll]):
            ok, _msg = mgr.vote_poll("P1", 0, "u1")
            assert ok is False or "already" in _msg.lower()
