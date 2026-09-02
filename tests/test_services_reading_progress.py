"""Tests for Book-Tale ReadingProgress."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.reading.reading_progress import ReadingProgress


@pytest.fixture()
def mgr() -> ReadingProgress:
    storage = MagicMock()
    return ReadingProgress(storage)


class TestReadingProgress:
    def test_update_progress(self, mgr: ReadingProgress) -> None:
        with patch.object(mgr, "_load_progress", return_value={}), patch.object(
            mgr, "_save_progress"
        ):
            result = mgr.update_progress("u1", "b1", page=50, total_pages=200)
            assert result is True

    def test_get_progress(self, mgr: ReadingProgress) -> None:
        data = {"u1": {"b1": {"current_page": 50, "total_pages": 200}}}
        with patch.object(mgr, "_load_progress", return_value=data):
            result = mgr.get_progress("u1", "b1")
            assert result["current_page"] == 50

    def test_get_progress_not_started(self, mgr: ReadingProgress) -> None:
        with patch.object(mgr, "_load_progress", return_value={}):
            result = mgr.get_progress("u1", "b1")
            assert result is None

    def test_get_all_progress(self, mgr: ReadingProgress) -> None:
        data = {
            "u1": {
                "b1": {"current_page": 50, "total_pages": 200},
                "b2": {"current_page": 100, "total_pages": 100},
            }
        }
        with patch.object(mgr, "_load_progress", return_value=data):
            result = mgr.get_all_progress("u1")
            assert len(result) == 2

    def test_add_bookmark(self, mgr: ReadingProgress) -> None:
        with patch.object(mgr, "_load_bookmarks", return_value=[]), patch.object(
            mgr, "_save_bookmarks"
        ):
            bm = mgr.add_bookmark("u1", "b1", page=42, note="Great chapter")
            assert bm["page"] == 42
            assert bm["note"] == "Great chapter"

    def test_get_bookmarks(self, mgr: ReadingProgress) -> None:
        bms = [
            {"user_id": "u1", "book_id": "b1", "page": 10},
            {"user_id": "u2", "book_id": "b1", "page": 20},
        ]
        with patch.object(mgr, "_load_bookmarks", return_value=bms):
            result = mgr.get_bookmarks("u1", "b1")
            assert len(result) == 1

    def test_delete_bookmark(self, mgr: ReadingProgress) -> None:
        bms = [{"bookmark_id": "BM-1", "user_id": "u1"}, {"bookmark_id": "BM-2", "user_id": "u1"}]
        with patch.object(mgr, "_load_bookmarks", return_value=bms), patch.object(
            mgr, "_save_bookmarks"
        ):
            ok = mgr.delete_bookmark("BM-1")
            assert ok is True
