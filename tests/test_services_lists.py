"""Tests for Book-Tale BookLists service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.books.lists import BookLists


@pytest.fixture()
def mgr(tmp_path: object) -> BookLists:
    storage = MagicMock()
    return BookLists(storage)


class TestCreateList:
    def test_create_list_success(self, mgr: BookLists) -> None:
        with patch.object(mgr, "_save_lists"):
            ok, _msg, lst = mgr.create_list("u1", "My List", "Description")
            assert ok is True
            assert lst is not None
            assert lst["name"] == "My List"

    def test_create_list_empty_name(self, mgr: BookLists) -> None:
        ok, _msg, _ = mgr.create_list("u1", "  ")
        assert ok is False
        assert "empty" in _msg.lower()

    def test_create_list_types(self, mgr: BookLists) -> None:
        with patch.object(mgr, "_save_lists"):
            ok, _, lst = mgr.create_list("u1", "Top 10", list_type="top10")
            assert ok is True
            assert lst["list_type"] == "top10"


class TestBookListOperations:
    def test_add_book_to_list(self, mgr: BookLists) -> None:
        list_id = "LIST-123"
        mock_list = {"list_id": list_id, "books": ["existing"], "owner_id": "u1"}
        with patch.object(mgr, "_load_lists", return_value=[mock_list]), patch.object(
            mgr, "_save_lists"
        ):
            ok, _msg = mgr.add_book_to_list(list_id, "new-book")
            assert ok is True

    def test_add_book_duplicate(self, mgr: BookLists) -> None:
        list_id = "LIST-123"
        mock_list = {"list_id": list_id, "books": ["b1"], "owner_id": "u1"}
        with patch.object(mgr, "_load_lists", return_value=[mock_list]):
            ok, _msg = mgr.add_book_to_list(list_id, "b1")
            assert ok is False or "already" in _msg.lower()

    def test_remove_book_from_list(self, mgr: BookLists) -> None:
        list_id = "LIST-123"
        mock_list = {"list_id": list_id, "books": ["b1", "b2"], "owner_id": "u1"}
        with patch.object(mgr, "_load_lists", return_value=[mock_list]), patch.object(
            mgr, "_save_lists"
        ):
            ok, _msg = mgr.remove_book_from_list(list_id, "b1")
            assert ok is True

    def test_get_user_lists(self, mgr: BookLists) -> None:
        lists = [
            {"owner_id": "u1", "name": "A"},
            {"owner_id": "u2", "name": "B"},
            {"owner_id": "u1", "name": "C"},
        ]
        with patch.object(mgr, "_load_lists", return_value=lists):
            result = mgr.get_user_lists("u1")
            assert len(result) == 2

    def test_delete_list(self, mgr: BookLists) -> None:
        mock_list = {"list_id": "L1", "owner_id": "u1"}
        with patch.object(mgr, "_load_lists", return_value=[mock_list]), patch.object(
            mgr, "_save_lists"
        ):
            ok, _msg = mgr.delete_list("L1", "u1")
            assert ok is True

    def test_delete_list_wrong_owner(self, mgr: BookLists) -> None:
        mock_list = {"list_id": "L1", "owner_id": "u2"}
        with patch.object(mgr, "_load_lists", return_value=[mock_list]):
            ok, _msg = mgr.delete_list("L1", "u1")
            assert ok is False
