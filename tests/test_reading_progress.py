"""
tests/test_reading_progress.py - Regression tests for ReadingProgress.

Lock in the `total_pages` contract in get_user_reading_list: the method derives
total_pages from the book OR the stored entry and must never raise NameError
(the pyflakes cleanup almost removed the assignment, which would have 500'd
every user's reading list page).
"""

from __future__ import annotations

import json


def _write_progress(tmp_path, data: dict) -> None:
    (tmp_path / "reading_progress.json").write_text(json.dumps(data), encoding="utf-8")


def test_get_user_reading_list_returns_total_pages(monkeypatch, tmp_path) -> None:
    from app.config.settings import Config

    # Point the data dir (dynamic lookups) and book file (static) at tmp_path.
    monkeypatch.setattr(Config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(Config, "BOOKS_FILE", str(tmp_path / "books.json"))

    _write_progress(
        tmp_path,
        {
            "U001_BK1": {
                "book_id": "BK1",
                "current_page": 50,
                "total_pages": 200,
                "updated_at": "2026-08-01T00:00:00",
                "finished": False,
            },
        },
    )

    from app.services.reading.reading_progress import ReadingProgress
    from app.storage.storage import Storage

    rp = ReadingProgress(Storage())

    result = rp.get_user_reading_list("U001")
    assert result["total_books"] == 1
    entry = result["currently_reading"][0]
    assert entry["total_pages"] == 200  # falls back to stored entry (no book file)
    assert entry["percentage"] == 25.0


def test_get_user_reading_list_other_user_empty(monkeypatch, tmp_path) -> None:
    from app.config.settings import Config

    monkeypatch.setattr(Config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(Config, "BOOKS_FILE", str(tmp_path / "books.json"))
    _write_progress(
        tmp_path,
        {
            "U001_BK1": {
                "book_id": "BK1",
                "current_page": 1,
                "total_pages": 10,
                "updated_at": "2026-08-01T00:00:00",
                "finished": False,
            },
        },
    )
    from app.services.reading.reading_progress import ReadingProgress
    from app.storage.storage import Storage

    rp = ReadingProgress(Storage())
    result = rp.get_user_reading_list("U999")
    assert result["total_books"] == 0
    assert result["currently_reading"] == []
    assert result["finished"] == []
    assert result["on_hold"] == []
