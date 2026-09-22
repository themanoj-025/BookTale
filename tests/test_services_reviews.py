"""Tests for Book-Tale ReviewManager.

Rewritten against the real app.services.books.reviews API:
- add_review(user_id, book_id, rating, content="", spoiler=False)
  -> (ok, msg, review_dict); rating must be 1..5 (int)
- get_book_reviews(book_id, ...) -> (enriched_reviews, stats)
  where stats = {total, average, distribution, page, total_pages}
"""

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
        ok, msg, _ = mgr.add_review("u1", "b1", 0)
        assert ok is False
        assert "1 and 5" in msg

    def test_add_review_invalid_rating_high(self, mgr: ReviewManager) -> None:
        ok, _msg, _ = mgr.add_review("u1", "b1", 6)
        assert ok is False

    def test_add_review_update_existing(self, mgr: ReviewManager) -> None:
        existing = [
            {
                "review_id": "R1",
                "user_id": "u1",
                "book_id": "b1",
                "rating": 3,
                "content": "old",
                "created_at": "2024-01-01T00:00:00",
            }
        ]
        mgr.storage.load_reviews.return_value = existing
        ok, _msg, rev = mgr.add_review("u1", "b1", 5, "Updated!")
        assert ok is True
        assert rev["rating"] == 5

    def test_add_review_spoiler_tag(self, mgr: ReviewManager) -> None:
        ok, _msg, rev = mgr.add_review("u1", "b1", 4, "Spoiler!", spoiler=True)
        assert ok is True
        assert rev.get("spoiler") is True


class TestGetBookReviews:
    def test_get_book_reviews_empty(self, mgr: ReviewManager) -> None:
        reviews, stats = mgr.get_book_reviews("b1")
        assert reviews == []
        assert stats["total"] == 0
        assert stats["average"] == 0

    def test_get_book_reviews_filters_by_book(self, mgr: ReviewManager) -> None:
        mgr.storage.load_reviews.return_value = [
            {
                "review_id": "R1",
                "book_id": "b1",
                "user_id": "u1",
                "rating": 5,
                "created_at": "2024-01-01T00:00:00",
            },
            {
                "review_id": "R2",
                "book_id": "b2",
                "user_id": "u1",
                "rating": 3,
                "created_at": "2024-01-01T00:00:00",
            },
        ]
        reviews, stats = mgr.get_book_reviews("b1")
        assert len(reviews) == 1
        assert stats["total"] == 1
        assert reviews[0]["book_id"] == "b1"

    def test_get_book_reviews_average(self, mgr: ReviewManager) -> None:
        mgr.storage.load_reviews.return_value = [
            {
                "review_id": "R1",
                "book_id": "b1",
                "user_id": "u1",
                "rating": 4,
                "created_at": "2024-01-01T00:00:00",
            },
            {
                "review_id": "R2",
                "book_id": "b1",
                "user_id": "u2",
                "rating": 2,
                "created_at": "2024-01-02T00:00:00",
            },
        ]
        _reviews, stats = mgr.get_book_reviews("b1")
        assert stats["average"] == 3.0
        assert stats["distribution"] == {4: 1, 2: 1}

    def test_get_book_reviews_enriches_author(self, mgr: ReviewManager) -> None:
        reviewer = MagicMock()
        reviewer.name = "Alice"
        mgr.storage.load_reviews.return_value = [
            {
                "review_id": "R1",
                "book_id": "b1",
                "user_id": "alice-id",
                "rating": 5,
                "created_at": "2024-01-01T00:00:00",
            },
        ]
        mgr.storage.load_users.return_value = {"alice-id": reviewer}
        reviews, _stats = mgr.get_book_reviews("b1")
        assert reviews[0]["author_name"] == "Alice"
        assert reviews[0]["helpful_count"] == 0

    def test_get_book_reviews_pagination(self, mgr: ReviewManager) -> None:
        mgr.storage.load_reviews.return_value = [
            {
                "review_id": f"R{i}",
                "book_id": "b1",
                "user_id": "u1",
                "rating": 5,
                "created_at": f"2024-01-{i:02d}T00:00:00",
            }
            for i in range(1, 16)
        ]
        _reviews, stats = mgr.get_book_reviews("b1", page=2, per_page=10)
        assert stats["total"] == 15
        assert stats["total_pages"] == 2
