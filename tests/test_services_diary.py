"""Tests for Book-Tale diary service."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.services.reading.diary as diary_mod
from app.services.reading.diary import RATING_LABELS, RATING_SCORES, DiaryManager


@pytest.fixture()
def mgr() -> DiaryManager:
    storage = MagicMock()
    storage.load_books.return_value = {
        "b1": SimpleNamespace(
            title="Book One",
            author="Jane",
            category="Fiction",
            cover_url="",
            cover_image="",
            pages=200,
        )
    }
    return DiaryManager(storage)


class TestRatingLabels:
    def test_rating_labels_defined(self) -> None:
        assert "perfection" in RATING_LABELS
        assert "worth_it" in RATING_LABELS
        assert "timepass" in RATING_LABELS
        assert "skip" in RATING_LABELS

    def test_rating_scores(self) -> None:
        assert RATING_SCORES["perfection"] == 4
        assert RATING_SCORES["skip"] == 1


class TestLogRead:
    def test_log_read_creates_entry(self, mgr: DiaryManager) -> None:
        with (
            patch.object(diary_mod, "_load_diary", return_value=[]),
            patch.object(diary_mod, "_save_diary") as m_save,
        ):
            ok, _msg, entry = mgr.log_read(
                "u1",
                "b1",
                rating_label="perfection",
                star_rating=5,
                diary_text="Amazing!",
            )
        assert ok is True
        assert entry is not None
        assert entry["book_id"] == "b1"
        assert entry["rating_label"] == "perfection"
        assert entry["star_rating"] == 5
        assert entry["id"].startswith("DIARY-")
        m_save.assert_called_once()

    def test_invalid_rating_rejected(self, mgr: DiaryManager) -> None:
        ok, msg, _entry = mgr.log_read("u1", "b1", rating_label="invalid")
        assert ok is False
        assert "Invalid rating" in msg

    def test_unknown_book_rejected(self, mgr: DiaryManager) -> None:
        ok, msg, _entry = mgr.log_read("u1", "nope", rating_label="perfection")
        assert ok is False
        assert "Book not found" in msg

    def test_duplicate_entry_updated(self, mgr: DiaryManager) -> None:
        existing = [
            {
                "id": "DIARY-1",
                "user_id": "u1",
                "book_id": "b1",
                "date_read": "",
                "rating_label": "skip",
                "star_rating": 1,
            }
        ]
        with (
            patch.object(diary_mod, "_load_diary", return_value=existing),
            patch.object(diary_mod, "_save_diary"),
        ):
            ok, msg, _entry = mgr.log_read("u1", "b1", rating_label="perfection")
        assert ok is True
        assert "updated" in msg.lower()
        assert existing[0]["rating_label"] == "perfection"


class TestGetUserDiary:
    def test_filters_by_user(self, mgr: DiaryManager) -> None:
        entries = [
            {
                "user_id": "u1",
                "book_id": "b1",
                "rating_label": "perfection",
                "star_rating": 5,
            },
            {"user_id": "u2", "book_id": "b1", "rating_label": "skip"},
        ]
        with patch.object(diary_mod, "_load_diary", return_value=entries):
            result, total = mgr.get_user_diary("u1")
        assert total == 1
        assert result[0]["user_id"] == "u1"
        assert result[0]["book_title"] == "Book One"

    def test_pagination(self, mgr: DiaryManager) -> None:
        entries = [
            {
                "user_id": "u1",
                "book_id": "b1",
                "rating_label": "perfection",
                "date_read": f"2025-01-{i:02d}",
            }
            for i in range(1, 6)
        ]
        with patch.object(diary_mod, "_load_diary", return_value=entries):
            page1, total = mgr.get_user_diary("u1", page=1, per_page=2)
        assert total == 5
        assert len(page1) == 2


class TestDeleteEntry:
    def test_delete_own_entry(self, mgr: DiaryManager) -> None:
        entries = [
            {"id": "E1", "user_id": "u1", "book_id": "b1", "rating_label": "skip"},
            {"id": "E2", "user_id": "u1", "book_id": "b1", "rating_label": "perfection"},
        ]
        with (
            patch.object(diary_mod, "_load_diary", return_value=entries),
            patch.object(diary_mod, "_save_diary"),
        ):
            ok, _msg = mgr.delete_entry("E1", "u1")
        assert ok is True
        assert [e["id"] for e in entries] == ["E2"]

    def test_delete_missing_entry_returns_false(self, mgr: DiaryManager) -> None:
        with patch.object(diary_mod, "_load_diary", return_value=[]):
            ok, msg = mgr.delete_entry("E1", "u1")
        assert ok is False
        assert "not found" in msg


class TestStats:
    def test_get_stats_counts_books(self, mgr: DiaryManager) -> None:
        entries = [
            {
                "user_id": "u1",
                "book_id": "b1",
                "rating_label": "perfection",
                "star_rating": 5,
                "date_read": "2025-01-02",
                "vibe_tags": [],
            },
            {
                "user_id": "u1",
                "book_id": "b1",
                "rating_label": "worth_it",
                "star_rating": 4,
                "date_read": "2025-02-02",
                "vibe_tags": ["deep"],
            },
            {
                "user_id": "u1",
                "book_id": "b1",
                "rating_label": "skip",
                "star_rating": 1,
                "date_read": "2025-03-02",
                "vibe_tags": [],
            },
        ]
        with patch.object(diary_mod, "_load_diary", return_value=entries):
            stats = mgr.get_stats("u1")
        assert stats["total_books"] == 3
        assert stats["books_by_month"]["2025-01"] == 1
        assert stats["rating_distribution"]["perfection"] == 1
        assert stats["vibe_tags_cloud"] == [("deep", 1)]

    def test_empty_stats(self, mgr: DiaryManager) -> None:
        with patch.object(diary_mod, "_load_diary", return_value=[]):
            stats = mgr.get_stats("u1")
        assert stats["total_books"] == 0
