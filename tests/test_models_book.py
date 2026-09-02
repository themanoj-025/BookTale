import pytest

pytestmark = pytest.mark.integration

"""Tests for Book model (app/models/book.py)."""

from app.models.book import CATEGORIES, Book


class TestBookCreation:
    """Test Book instantiation with various parameters."""

    def test_minimal_book(self) -> None:
        b = Book(
            book_id="B001", title="Test", author="Author",
            isbn="1234567890", category="Fiction",
            total_copies=5, available_copies=5,
        )
        assert b.book_id == "B001"
        assert b.title == "Test"
        assert b.available_copies == 5
        assert b.is_deleted is False
        assert b.issue_count == 0
        assert b.genres == []

    def test_full_book(self) -> None:
        b = Book(
            book_id="B002", title="Full", author="Writer",
            isbn="9781234567890", category="Science",
            total_copies=10, available_copies=8,
            publisher="Pub", pages=300, language="Hindi",
            release_date="2024-01-01", description="A book",
            series_name="Series", series_order=1,
            genres=["sci-fi", "thriller"],
        )
        assert b.publisher == "Pub"
        assert b.pages == 300
        assert b.language == "Hindi"
        assert b.genres == ["sci-fi", "thriller"]

    def test_categories_constant(self) -> None:
        assert "Fiction" in CATEGORIES
        assert "CS" in CATEGORIES
        assert len(CATEGORIES) == 11


class TestBookSerialization:
    """Test to_dict and from_dict round-trip."""

    def test_to_dict(self) -> None:
        b = Book(
            book_id="B001", title="T", author="A",
            isbn="111", category="Fiction",
            total_copies=1, available_copies=1,
        )
        d = b.to_dict()
        assert d["book_id"] == "B001"
        assert d["title"] == "T"
        assert isinstance(d, dict)

    def test_from_dict_minimal(self) -> None:
        data = {
            "book_id": "B001", "title": "T", "author": "A",
            "isbn": "111", "category": "Fiction",
            "total_copies": 1, "available_copies": 1,
        }
        b = Book.from_dict(data)
        assert b.book_id == "B001"
        assert b.publisher == ""
        assert b.pages == 0
        assert b.cover_url == ""
        assert b.genres == []

    def test_from_dict_full(self) -> None:
        data = {
            "book_id": "B002", "title": "Full", "author": "W",
            "isbn": "222", "category": "Science",
            "total_copies": 5, "available_copies": 3,
            "publisher": "Pub", "pages": 200, "genres": ["a", "b"],
        }
        b = Book.from_dict(data)
        assert b.genres == ["a", "b"]
        assert b.publisher == "Pub"

    def test_from_dict_null_genres(self) -> None:
        data = {
            "book_id": "B003", "title": "X", "author": "Y",
            "isbn": "333", "category": "CS",
            "total_copies": 1, "available_copies": 1,
            "genres": None,
        }
        b = Book.from_dict(data)
        assert b.genres == []

    def test_from_dict_string_genres(self) -> None:
        data = {
            "book_id": "B004", "title": "X", "author": "Y",
            "isbn": "444", "category": "CS",
            "total_copies": 1, "available_copies": 1,
            "genres": "fiction",
        }
        b = Book.from_dict(data)
        assert b.genres == ["f", "i", "c", "t", "i", "o", "n"]

    def test_roundtrip(self) -> None:
        b1 = Book(
            book_id="B005", title="RT", author="A",
            isbn="555", category="History",
            total_copies=2, available_copies=1,
            genres=["history"],
        )
        b2 = Book.from_dict(b1.to_dict())
        assert b1 == b2


class TestBookEquality:
    """Test __eq__ and __hash__."""

    def test_equal_books(self) -> None:
        b1 = Book("B001", "T", "A", "111", "F", 1, 1)
        b2 = Book("B001", "Other", "Other", "222", "S", 5, 5)
        assert b1 == b2

    def test_different_books(self) -> None:
        b1 = Book("B001", "T", "A", "111", "F", 1, 1)
        b2 = Book("B002", "T", "A", "111", "F", 1, 1)
        assert b1 != b2

    def test_not_equal_to_non_book(self) -> None:
        b = Book("B001", "T", "A", "111", "F", 1, 1)
        assert b != "not a book"

    def test_hash_consistent(self) -> None:
        b = Book("B001", "T", "A", "111", "F", 1, 1)
        assert hash(b) == hash("B001")

    def test_hash_in_set(self) -> None:
        s = {Book("B001", "T", "A", "111", "F", 1, 1)}
        assert Book("B001", "X", "Y", "222", "S", 5, 5) in s


class TestBookDisplay:
    """Test display output."""

    def test_display_active(self) -> None:
        b = Book("B001", "Test", "Author", "111", "Fiction", 5, 3)
        d = b.display()
        assert "B001" in d
        assert "Test" in d
        assert "3/5" in d

    def test_display_deleted(self) -> None:
        b = Book("B001", "Test", "Author", "111", "Fiction", 5, 0, is_deleted=True)
        d = b.display()
        assert "[DELETED]" in d

    def test_cover_image_display_with_url(self) -> None:
        b = Book("B001", "T", "A", "111", "F", 1, 1, cover_url="http://x.com/img.jpg")
        assert b.cover_image_display == "http://x.com/img.jpg"

    def test_cover_image_display_fallback(self) -> None:
        b = Book("B001", "T", "A", "111", "F", 1, 1, cover_image="local.png")
        assert b.cover_image_display == "local.png"
