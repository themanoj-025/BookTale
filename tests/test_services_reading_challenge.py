"""Tests for Book-Tale reading challenge service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.reading.reading_challenge import ReadingChallenge


@pytest.fixture()
def mgr() -> ReadingChallenge:
    storage = MagicMock()
    return ReadingChallenge(storage)


class TestReadingChallenge:
    def test_create_challenge(self, mgr: ReadingChallenge) -> None:
        with patch.object(mgr, "_load_challenges", return_value=[]), patch.object(
            mgr, "_save_challenges"
        ):
            ok, _msg, ch = mgr.create_challenge(
                "u1", "Read 20 books in 2026", target=20
            )
            assert ok is True
            assert ch["target"] == 20

    def test_create_challenge_empty_desc(self, mgr: ReadingChallenge) -> None:
        ok, _msg, _ = mgr.create_challenge("u1", "  ", target=10)
        assert ok is False

    def test_join_challenge(self, mgr: ReadingChallenge) -> None:
        ch = {"challenge_id": "CH1", "participants": {}}
        with patch.object(mgr, "_load_challenges", return_value=[ch]), patch.object(
            mgr, "_save_challenges"
        ):
            ok, _msg = mgr.join_challenge("CH1", "u2")
            assert ok is True

    def test_join_already_joined(self, mgr: ReadingChallenge) -> None:
        ch = {"challenge_id": "CH1", "participants": {"u2": {"progress": 0}}}
        with patch.object(mgr, "_load_challenges", return_value=[ch]):
            ok, _msg = mgr.join_challenge("CH1", "u2")
            assert ok is False or "already" in _msg.lower()

    def test_update_progress(self, mgr: ReadingChallenge) -> None:
        ch = {"challenge_id": "CH1", "participants": {"u1": {"progress": 3}}, "target": 20}
        with patch.object(mgr, "_load_challenges", return_value=[ch]), patch.object(
            mgr, "_save_challenges"
        ):
            ok, _msg = mgr.update_progress("CH1", "u1", books_read=5)
            assert ok is True

    def test_get_challenge(self, mgr: ReadingChallenge) -> None:
        ch = {"challenge_id": "CH1", "name": "Test Challenge"}
        with patch.object(mgr, "_load_challenges", return_value=[ch]):
            result = mgr.get_challenge("CH1")
            assert result is not None
            assert result["name"] == "Test Challenge"
