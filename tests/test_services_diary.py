"""Tests for Book-Tale diary service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.reading.diary import (
    RATING_LABELS,
    RATING_SCORES,
    ReadingDiary,
)


@pytest.fixture()
def mgr() -> ReadingDiary:
    storage = MagicMock()
    return ReadingDiary(storage)


class TestRatingLabels:
    def test_rating_labels_defined(self) -> None:
        assert "perfection" in RATING_LABELS
        assert "worth_it" in RATING_LABELS
        assert "timepass" in RATING_LABELS
        assert "skip" in RATING_LABELS

    def test_rating_scores(self) -> None:
        assert RATING_SCORES["perfection"] == 4
        assert RATING_SCORES["skip"] == 1


class TestDiaryEntries:
    def test_add_entry(self, mgr: ReadingDiary) -> None:
        with patch.object(mgr, "_load_diary", return_value=[]), patch.object(
            mgr, "_save_diary"
        ):
            ok, _entry = mgr.add_entry(
                "u1", "b1", rating_label="perfection", stars=5, notes="Amazing!"
            )
            assert ok is True
            assert _entry["rating_label"] == "perfection"

    def test_add_entry_invalid_rating(self, mgr: ReadingDiary) -> None:
        ok, _entry = mgr.add_entry("u1", "b1", rating_label="invalid")
        assert ok is False

    def test_get_entries(self, mgr: ReadingDiary) -> None:
        entries = [
            {"user_id": "u1", "book_id": "b1", "rating_label": "perfection"},
            {"user_id": "u2", "book_id": "b1", "rating_label": "skip"},
        ]
        with patch.object(mgr, "_load_diary", return_value=entries):
            result = mgr.get_entries("u1")
            assert len(result) == 1

    def test_get_stats(self, mgr: ReadingDiary) -> None:
        entries = [
            {"user_id": "u1", "rating_label": "perfection", "stars": 5},
            {"user_id": "u1", "rating_label": "worth_it", "stars": 4},
            {"user_id": "u1", "rating_label": "skip", "stars": 1},
        ]
        with patch.object(mgr, "_load_diary", return_value=entries):
            stats = mgr.get_stats("u1")
            assert isinstance(stats, dict)
            assert stats.get("total_entries", 0) == 3

    def test_delete_entry(self, mgr: ReadingDiary) -> None:
        entries = [
            {"entry_id": "E1", "user_id": "u1"},
            {"entry_id": "E2", "user_id": "u1"},
        ]
        with patch.object(mgr, "_load_diary", return_value=entries), patch.object(
            mgr, "_save_diary"
        ):
            ok = mgr.delete_entry("E1", "u1")
            assert ok is True
