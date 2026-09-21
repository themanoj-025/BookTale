"""Tests for Book-Tale BookLists service.

Rewritten against the real app.services.books.lists API:
- add_book_to_list(list_id, book_id, user_id, note="") -> (ok, msg)
  (requires owner or collaborator; books are dicts with book_id key)
- remove_book_from_list(list_id, book_id, user_id) -> (ok, msg)
- get_user_lists(user_id, include_private=False) -> list
- delete_list(list_id, user_id) -> (ok, msg)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.books.lists import BookLists

pytestmark = pytest.mark.unit


@pytest.fixture()
def mgr() -> BookLists:
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
        ok, msg, _ = mgr.create_list("u1", "  ")
        assert ok is False
        assert "empty" in msg.lower()

    def test_create_list_types(self, mgr: BookLists) -> None:
        with patch.object(mgr, "_save_lists"):
            ok, _, lst = mgr.create_list("u1", "Top 10", list_type="top10")
            assert ok is True
            assert lst["list_type"] == "top10"


class TestBookListOperations:
    def test_add_book_to_list(self, mgr: BookLists) -> None:
        list_id = "LIST-123"
        mock_list = {
            "list_id": list_id,
            "books": [],
            "owner_id": "u1",
            "updated_at": "2024-01-01T00:00:00",
        }
        book = MagicMock()
        book.is_deleted = False
        book.title = "New Book"
        book.author = "Author"
        mgr.storage.load_books.return_value = {"new-book": book}
        with (
            patch.object(mgr, "_load_lists", return_value=[mock_list]),
            patch.object(mgr, "_save_lists"),
        ):
            ok, _msg = mgr.add_book_to_list(list_id, "new-book", "u1")
            assert ok is True
            assert mock_list["books"][0]["book_id"] == "new-book"

    def test_add_book_duplicate(self, mgr: BookLists) -> None:
        list_id = "LIST-123"
        mock_list = {
            "list_id": list_id,
            "books": [{"book_id": "b1"}],
            "owner_id": "u1",
        }
        with patch.object(mgr, "_load_lists", return_value=[mock_list]):
            ok, msg = mgr.add_book_to_list(list_id, "b1", "u1")
            assert ok is False
            assert "already" in msg.lower()

    def test_add_book_permission_denied(self, mgr: BookLists) -> None:
        list_id = "LIST-123"
        mock_list = {
            "list_id": list_id,
            "books": [],
            "owner_id": "someone-else",
        }
        with patch.object(mgr, "_load_lists", return_value=[mock_list]):
            ok, msg = mgr.add_book_to_list(list_id, "b1", "u1")
            assert ok is False
            assert "permission" in msg.lower()

    def test_remove_book_from_list(self, mgr: BookLists) -> None:
        list_id = "LIST-123"
        mock_list = {
            "list_id": list_id,
            "books": [{"book_id": "b1"}, {"book_id": "b2"}],
            "owner_id": "u1",
        }
        with (
            patch.object(mgr, "_load_lists", return_value=[mock_list]),
            patch.object(mgr, "_save_lists"),
        ):
            ok, _msg = mgr.remove_book_from_list(list_id, "b1", "u1")
            assert ok is True
            assert len(mock_list["books"]) == 1

    def test_get_user_lists(self, mgr: BookLists) -> None:
        lists = [
            {"owner_id": "u1", "name": "A", "updated_at": "2024-01-01T00:00:00"},
            {"owner_id": "u2", "name": "B", "updated_at": "2024-01-01T00:00:00"},
            {"owner_id": "u1", "name": "C", "updated_at": "2024-01-01T00:00:00"},
        ]
        with patch.object(mgr, "_load_lists", return_value=lists):
            result = mgr.get_user_lists("u1")
            assert len(result) == 2

    def test_delete_list(self, mgr: BookLists) -> None:
        mock_list = {"list_id": "L1", "owner_id": "u1"}
        with (
            patch.object(mgr, "_load_lists", return_value=[mock_list]),
            patch.object(mgr, "_save_lists"),
        ):
            ok, _msg = mgr.delete_list("L1", "u1")
            assert ok is True

    def test_delete_list_wrong_owner(self, mgr: BookLists) -> None:
        mock_list = {"list_id": "L1", "owner_id": "u2"}
        with patch.object(mgr, "_load_lists", return_value=[mock_list]):
            ok, _msg = mgr.delete_list("L1", "u1")
            assert ok is False
