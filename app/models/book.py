"""
book.py - Book model and management
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

CATEGORIES: list = [
    "Fiction",
    "Non-Fiction",
    "Science",
    "CS",
    "Mathematics",
    "History",
    "Biography",
    "Philosophy",
    "Law",
    "Medicine",
    "Other",
]


@dataclass
class Book:
    book_id: str
    title: str
    author: str
    isbn: str
    category: str
    total_copies: int
    available_copies: int
    is_deleted: bool = False
    issue_count: int = 0
    added_on: str = field(default_factory=lambda: datetime.now().isoformat())
    # Enhanced metadata
    publisher: str = ""
    pages: int = 0
    language: str = "English"
    release_date: str = ""
    cover_image: str = ""
    description: str = ""
    series_name: str = ""
    series_order: int = 0
    # Cover fetch fields (BookTale)
    cover_url: str = ""  # Resolved cover image URL
    cover_fetched: bool = False  # Whether we've attempted a cover fetch
    cover_source: str = ""  # "openlibrary" | "googlebooks" | "placeholder" | ""
    dominant_color: str = ""  # "#rrggbb" extracted from cover image
    genres: list = field(default_factory=list)  # List of genre strings

    @property
    def cover_image_display(self) -> str:
        """Alias: returns cover_url if available, else legacy cover_image."""
        return self.cover_url or self.cover_image

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Book":
        # Handle missing new fields gracefully
        for fld in [
            "publisher",
            "pages",
            "language",
            "release_date",
            "cover_image",
            "description",
            "series_name",
        ]:
            if fld not in data:
                data[fld] = "" if fld not in ["pages", "series_order"] else 0
        if "series_order" not in data:
            data["series_order"] = 0
        if "language" not in data:
            data["language"] = "English"
        if "cover_url" not in data:
            data["cover_url"] = ""
        if "cover_fetched" not in data:
            data["cover_fetched"] = False
        if "cover_source" not in data:
            data["cover_source"] = ""
        if "dominant_color" not in data:
            data["dominant_color"] = ""
        if "genres" not in data:
            data["genres"] = []
        elif not isinstance(data["genres"], list):
            # Guard against null or non-list values from external data
            try:
                data["genres"] = list(data["genres"]) if data["genres"] else []
            except Exception:
                data["genres"] = []
        return cls(**data)

    def display(self) -> str:
        status = (
            "[DELETED]"
            if self.is_deleted
            else (f"Avail: {self.available_copies}/{self.total_copies}")
        )
        return (
            f"  ID       : {self.book_id}\n"
            f"  Title    : {self.title}\n"
            f"  Author   : {self.author}\n"
            f"  ISBN     : {self.isbn}\n"
            f"  Category : {self.category}\n"
            f"  Status   : {status}\n"
            f"  Issued   : {self.issue_count} times\n"
            f"  Publisher: {self.publisher}\n"
            f"  Pages    : {self.pages}\n"
            f"  Language : {self.language}\n"
            f"  Released : {self.release_date}"
            f"  Series   : {self.series_name or '—'} #{self.series_order if self.series_order else '—'}"
        )

    def __hash__(self) -> int:
        return hash(self.book_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Book):
            return NotImplemented
        return self.book_id == other.book_id
