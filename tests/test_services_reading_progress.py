"""Tests for Book-Tale ReadingProgress service.

Rewritten against the real app.services.reading.reading_progress API:
- update_progress(user_id, book_id, current_page=..., time_spent_minutes=...,
  notes=..., finished=...) -> (success, message, progress_dict)
- mark_as_started / mark_as_finished delegate to update_progress
- add_bookmark / remove_bookmark / get_*_bookmarks
"""

from __future__ import annotations

import pytest

from app.services.reading.reading_progress import ReadingProgress

pytestmark = pytest.mark.unit


class FakeBook:
    def __init__(self, pages: int = 300) -> None:
        self.pages = pages
        self.title = "Test Book"
        self.author = "Test Author"
        self.category = "Fiction"


@pytest.fixture()
def storage(monkeypatch):
    st = type("Storage", (), {})()
    st.load_books = lambda: {"b1": FakeBook(pages=300)}
    return st


@pytest.fixture()
def progress(storage) -> ReadingProgress:
    return ReadingProgress(storage)


class TestUpdateProgress:
    def test_start_creates_entry(self, progress: ReadingProgress) -> None:
        ok, msg, data = progress.update_progress("u1", "b1", current_page=10)
        assert ok is True
        assert "progress" in msg.lower()
        assert data["user_id"] == "u1"
        assert data["book_id"] == "b1"
        assert data["current_page"] == 10
        assert data["started"] is True
        assert data["finished"] is False

    def test_total_pages_from_book(self, progress: ReadingProgress) -> None:
        _ok, _msg, data = progress.update_progress("u1", "b1", current_page=1)
        assert data["total_pages"] == 300

    def test_time_spent_accumulates(self, progress: ReadingProgress) -> None:
        progress.update_progress("u1", "b1", time_spent_minutes=30)
        _ok, _msg, data = progress.update_progress("u1", "b1", time_spent_minutes=15)
        assert data["time_spent_minutes"] == 45

    def test_notes_saved(self, progress: ReadingProgress) -> None:
        _ok, _msg, data = progress.update_progress("u1", "b1", notes="great chapter")
        assert data["notes"] == "great chapter"

    def test_finish_sets_current_page_to_total(self, progress: ReadingProgress) -> None:
        _ok, _msg, data = progress.update_progress("u1", "b1", finished=True)
        assert data["finished"] is True
        assert data["current_page"] == 300

    def test_negative_page_clamped(self, progress: ReadingProgress) -> None:
        _ok, _msg, data = progress.update_progress("u1", "b1", current_page=-5)
        assert data["current_page"] == 0


class TestMarkAs:
    def test_mark_as_started(self, progress: ReadingProgress) -> None:
        ok, _msg, data = progress.mark_as_started("u1", "b1")
        assert ok is True
        assert data["started"] is True

    def test_mark_as_finished(self, progress: ReadingProgress) -> None:
        ok, msg, data = progress.mark_as_finished("u1", "b1")
        assert ok is True
        assert "finished" in msg.lower()
        assert data["finished"] is True


class TestGetters:
    def test_get_progress_missing_returns_empty(self, progress: ReadingProgress) -> None:
        result = progress.get_progress("u1", "missing")
        assert result.get("finished") is False or result == {}

    def test_get_user_reading_list(self, progress: ReadingProgress) -> None:
        progress.update_progress("list-user", "b1", current_page=5)
        result = progress.get_user_reading_list("list-user")
        assert result["total_books"] == 1
        assert len(result["currently_reading"]) == 1
        assert result["currently_reading"][0]["book_title"] == "Test Book"
        assert result["currently_reading"][0]["percentage"] == 1.7  # 5/300

    def test_get_reading_stats(self, progress: ReadingProgress) -> None:
        progress.update_progress("u1", "b1", current_page=100)
        stats = progress.get_reading_stats("u1")
        assert stats is not None


class TestBookmarks:
    def test_add_and_get_bookmarks(self, progress: ReadingProgress) -> None:
        ok, msg, bm = progress.add_bookmark("u1", "b1", page=42, note="ch 3")
        assert ok is True
        assert bm["page"] == 42
        bookmarks = progress.get_user_bookmarks("u1")
        assert len(bookmarks) == 1
        assert bookmarks[0]["page"] == 42

    def test_add_bookmark_invalid_page(self, progress: ReadingProgress) -> None:
        ok, msg, bm = progress.add_bookmark("u1", "b1", page=0)
        assert ok is False
        assert bm is None

    def test_remove_bookmark(self, progress: ReadingProgress) -> None:
        _ok, _msg, bm = progress.add_bookmark("rm-user", "b1", page=42)
        ok, _msg = progress.remove_bookmark(bm["bookmark_id"], "rm-user")
        assert ok is True
        assert progress.get_user_bookmarks("rm-user") == []

    def test_remove_bookmark_wrong_user(self, progress: ReadingProgress) -> None:
        _ok, _msg, bm = progress.add_bookmark("u1", "b1", page=42)
        ok, msg = progress.remove_bookmark(bm["bookmark_id"], "attacker")
        assert ok is False
        assert "not found" in msg.lower()

    def test_get_book_bookmarks(self, progress: ReadingProgress) -> None:
        progress.add_bookmark("bb-user", "bb-book", page=10)
        progress.add_bookmark("bb-user", "other", page=20)
        result = progress.get_book_bookmarks("bb-user", "bb-book")
        assert len(result) == 1
