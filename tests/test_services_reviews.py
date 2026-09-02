"""Tests for Book-Tale ReviewManager."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.books.reviews import ReviewManager

pytestmark = pytest.mark.unit



@pytest.fixture()
def mgr() -> ReviewManager:
    storage = MagicMock()
    storage.load_reviews.return_value = []
    storage.load_books.return_value = {}
    storage.load_users.return_value = {}
    return ReviewManager(storage)


class TestAddReview:
    def test_add_review_success(self, mgr: ReviewManager) -> None:
        ok, _msg, rev = mgr.add_review("u1", "b1", 5, "Great book!")
        assert ok is True
        assert rev is not None
        assert rev["rating"] == 5

    def test_add_review_invalid_rating_low(self, mgr: ReviewManager) -> None:
        ok, _msg, _ = mgr.add_review("u1", "b1", 0)
        assert ok is False
        assert "1 and 5" in _msg

    def test_add_review_invalid_rating_high(self, mgr: ReviewManager) -> None:
        ok, _msg, _ = mgr.add_review("u1", "b1", 6)
        assert ok is False

    def test_add_review_update_existing(self, mgr: ReviewManager) -> None:
        existing = [{"user_id": "u1", "book_id": "b1", "rating": 3, "content": "old"}]
        mgr.storage.load_reviews.return_value = existing
        ok, _msg, rev = mgr.add_review("u1", "b1", 5, "Updated!")
        assert ok is True
        assert rev["rating"] == 5

    def test_add_review_spoiler_tag(self, mgr: ReviewManager) -> None:
        ok, _msg, rev = mgr.add_review("u1", "b1", 4, "Spoiler!", spoiler=True)
        assert ok is True
        assert rev.get("spoiler") is True


class TestGetReviews:
    def test_get_reviews_empty(self, mgr: ReviewManager) -> None:
        result = mgr.get_reviews("b1")
        assert result == []

    def test_get_reviews_filters_by_book(self, mgr: ReviewManager) -> None:
        mgr.storage.load_reviews.return_value = [
            {"book_id": "b1", "rating": 5},
            {"book_id": "b2", "rating": 3},
        ]
        result = mgr.get_reviews("b1")
        assert len(result) == 1

    def test_get_average_rating(self, mgr: ReviewManager) -> None:
        mgr.storage.load_reviews.return_value = [
            {"book_id": "b1", "rating": 4},
            {"book_id": "b1", "rating": 2},
        ]
        avg = mgr.get_average_rating("b1")
        assert avg == 3.0

    def test_get_average_rating_no_reviews(self, mgr: ReviewManager) -> None:
        avg = mgr.get_average_rating("b1")
        assert avg == 0.0
