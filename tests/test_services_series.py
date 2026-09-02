"""Tests for Book-Tale SeriesManager."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.books.series import SeriesManager


@pytest.fixture()
def mgr() -> SeriesManager:
    storage = MagicMock()
    return SeriesManager(storage)


class TestSeriesCRUD:
    def test_create_series(self, mgr: SeriesManager) -> None:
        with patch.object(mgr, "_save_series"):
            ok, _msg, s = mgr.create_series("Lord of the Rings", "Fantasy epic")
            assert ok is True
            assert s["name"] == "Lord of the Rings"

    def test_create_series_empty_name(self, mgr: SeriesManager) -> None:
        ok, _msg, _ = mgr.create_series("  ")
        assert ok is False
        assert "empty" in _msg.lower()

    def test_get_series(self, mgr: SeriesManager) -> None:
        series = [{"series_id": "SER-1", "name": "Test"}]
        with patch.object(mgr, "_load_series", return_value=series):
            result = mgr.get_series("SER-1")
            assert result is not None
            assert result["name"] == "Test"

    def test_get_series_not_found(self, mgr: SeriesManager) -> None:
        with patch.object(mgr, "_load_series", return_value=[]):
            assert mgr.get_series("NONEXISTENT") is None

    def test_get_all_series(self, mgr: SeriesManager) -> None:
        series = [
            {"series_id": "S1", "name": "A"},
            {"series_id": "S2", "name": "B"},
        ]
        with patch.object(mgr, "_load_series", return_value=series):
            result = mgr.get_all_series()
            assert len(result) == 2

    def test_delete_series(self, mgr: SeriesManager) -> None:
        series = [{"series_id": "S1", "name": "A"}]
        with patch.object(mgr, "_load_series", return_value=series), patch.object(
            mgr, "_save_series"
        ):
            ok, _msg = mgr.delete_series("S1")
            assert ok is True

    def test_delete_series_not_found(self, mgr: SeriesManager) -> None:
        with patch.object(mgr, "_load_series", return_value=[]):
            ok, _msg = mgr.delete_series("NONEXISTENT")
            assert ok is False
