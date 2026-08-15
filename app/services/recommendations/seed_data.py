"""
seed_data.py - Goodreads Knowledge Base for Cold-Start Recommendations

Loads the Goodreads books.csv dataset and provides search, recommendation,
and category exploration methods that the Recommender can use as a fallback
when the library has insufficient data (cold-start scenario).

The seed data is indexed in memory on first access and provides:
- Popular/trending picks from the real world
- Similar book discovery by author, category, and rating
- Category-based exploration with real-world metadata
- ISBN lookup for auto-filling book details
"""

import csv
import math
import os
import re
from collections import defaultdict

# Global in-memory cache for the seed dataset
_SEED_BOOKS: list[dict] = []
_SEED_BY_AUTHOR: dict[str, list[dict]] = {}
_SEED_BY_TITLE: dict[str, list[dict]] = {}
_SEED_BY_ISBN: dict[str, dict] = {}
_SEED_BY_CATEGORY: dict[str, list[dict]] = {}
_SEED_CATEGORIES: list[str] = []
_SEED_LOADED = False


# ─

# Map Goodreads-like genres to our library categories
GOODREADS_CATEGORY_MAP: dict[str, str] = {
    # Auto-detected from author/genre signals
}

# ISBN prefixes that help determine genre/category
ISBN_CATEGORY_PREFIXES: dict[str, str] = {
    "0": "Fiction",
    "1": "Fiction",  # Fiction/Literature
    "2": "Other",  # Reference
    "3": "Education",  # Education/Academic
    "4": "Other",
    "5": "Reference",  # Reference/Guidance
    "6": "Self-Help",
    "7": "Education",
    "8": "Non-Fiction",
    "9": "Other",
}

# Author-based category heuristics
AUTHOR_CATEGORY_HINTS: dict[str, str] = {
    "rowling": "Fiction",
    "tolkien": "Fiction",
    "austen": "Fiction",
    "dickens": "Fiction",
    "hemingway": "Fiction",
    "twain": "Fiction",
    "shakespeare": "Drama",
    "steinbeck": "Fiction",
    "orwell": "Fiction",
    "fitzgerald": "Fiction",
    "lee": "Fiction",
    "salinger": "Fiction",
    "vonnegut": "Fiction",
    "asimov": "Science",
    "clarke": "Science",
    "heinlein": "Science",
    "bradbury": "Science",
    "herbert": "Science",
    "adams": "Science",
    "pratchett": "Fiction",
    "gaiman": "Fiction",
    "king": "Fiction",
    "grisham": "Fiction",
    "christie": "Fiction",
    "cohle": "Fiction",
    "martin": "Fiction",
    "roth": "Fiction",
    "didion": "Non-Fiction",
    "gladwell": "Non-Fiction",
    "bryson": "Non-Fiction",
    "diamond": "Non-Fiction",
    "krakauer": "Non-Fiction",
    "lewis": "Non-Fiction",
    "taleb": "Non-Fiction",
    "kahneman": "Non-Fiction",
    "harari": "History",
    "mccullough": "History",
    "goodwin": "History",
    "covey": "Self-Help",
    "hill": "Self-Help",
    "allen": "Self-Help",
    "carnegie": "Self-Help",
    "hawking": "Science",
    "greene": "Science",
    "sagan": "Science",
    "dawkins": "Science",
    "dennett": "Philosophy",
    "plato": "Philosophy",
    "aristotle": "Philosophy",
    "nietzsche": "Philosophy",
    "sartre": "Philosophy",
    "foucault": "Philosophy",
    "camus": "Philosophy",
    "rand": "Philosophy",
    "coelho": "Self-Help",
    "tolstoy": "Fiction",
    "dostoevsky": "Fiction",
    "garcia marquez": "Fiction",
    "brown": "Fiction",
    "murakami": "Fiction",
    "pullman": "Fiction",
    "snicket": "Children",
    "seuss": "Children",
    "dahl": "Children",
    "sen": "Non-Fiction",
    "chomsky": "Philosophy",
    "zinn": "History",
    "pollan": "Cooking",
    "bourdain": "Cooking",
    "oliver": "Cooking",
    "child": "Biography",
    "angelou": "Biography",
    "obama": "Biography",
    "mandela": "Biography",
    "franklin": "Biography",
    "geronimo": "Biography",
    "gandhi": "Biography",
    "monk": "Biography",
    "augustine": "Religion",
    "pagels": "Religion",
    "armstrong": "Religion",
    "aslan": "Religion",
    "karen": "Religion",
    "alcott": "Fiction",
    "montgomery": "Fiction",
    "wilde": "Drama",
    "iocscu": "Drama",
    "chekhov": "Drama",
    "sophocles": "Drama",
    "euripides": "Drama",
    "aeschylus": "Drama",
    "aristophanes": "Drama",
    "homr": "Poetry",
    "homer": "Poetry",
    "virgil": "Poetry",
    "dante": "Poetry",
    "chaucer": "Poetry",
    "milton": "Poetry",
    "blake": "Poetry",
    "wordsworth": "Poetry",
    "coleridge": "Poetry",
    "keats": "Poetry",
    "shelley": "Poetry",
    "byron": "Poetry",
    "poe": "Poetry",
    "whitman": "Poetry",
    "dickinson": "Poetry",
    "frost": "Poetry",
    "neruda": "Poetry",
    "lorde": "Poetry",
    "sharon": "Self-Help",
    "mehmet": "Self-Help",
    "deepak": "Self-Help",
    "ekhart": "Philosophy",
}


def _infer_category(title: str, authors: str, publisher: str) -> str:
    """Infer a library category from Goodreads book metadata using heuristics."""
    t = title.lower()
    a = authors.lower()
    p = publisher.lower()

    # Check author hints first
    for keyword, cat in AUTHOR_CATEGORY_HINTS.items():
        if keyword in a:
            return cat

    # Title-based heuristics
    title_keywords = {
        "cookbook": "Cooking",
        "cooking": "Cooking",
        "recipes": "Cooking",
        "baking": "Cooking",
        "food": "Cooking",
        "barbecue": "Cooking",
        "history": "History",
        "historical": "History",
        "biography": "Biography",
        "autobiography": "Biography",
        "memoir": "Biography",
        "life of": "Biography",
        "philosophy": "Philosophy",
        "philosophical": "Philosophy",
        "science": "Science",
        "physics": "Science",
        "biology": "Science",
        "chemistry": "Science",
        "astronomy": "Science",
        "evolution": "Science",
        "mathematics": "Science",
        "math": "Science",
        "poems": "Poetry",
        "poetry": "Poetry",
        "sonnets": "Poetry",
        "drama": "Drama",
        "plays": "Drama",
        "tragedy": "Drama",
        "comedy": "Drama",
        "self-help": "Self-Help",
        "self help": "Self-Help",
        "how to": "Self-Help",
        "happiness": "Self-Help",
        "success": "Self-Help",
        "motivation": "Self-Help",
        "education": "Education",
        "learning": "Education",
        "textbook": "Education",
        "guide to": "Education",
        "reference": "Reference",
        "dictionary": "Reference",
        "encyclopedia": "Reference",
        "children": "Children",
        "kids": "Children",
        "young": "Children",
        "baby": "Children",
        "travel": "Travel",
        "adventure": "Travel",
        "art": "Art",
        "music": "Music",
        "sport": "Sports",
        "baseball": "Sports",
        "football": "Sports",
        "basketball": "Sports",
        "comic": "Comics",
        "graphic novel": "Comics",
        "manga": "Comics",
    }
    for keyword, cat in title_keywords.items():
        if keyword in t:
            return cat

    # Publisher-based hints
    publisher_hints = {
        "cookbook": "Cooking",
        "cooking": "Cooking",
        "religion": "Religion",
        "theology": "Religion",
        "spiritual": "Religion",
        "academic": "Education",
        "textbook": "Education",
    }
    for keyword, cat in publisher_hints.items():
        if keyword in p:
            return cat

    return "Fiction"  # Default


def _parse_authors(authors_field: str) -> list[str]:
    """Parse the authors field (separated by /)."""
    if not authors_field:
        return ["Unknown"]
    return [a.strip() for a in authors_field.split("/")]


def _clean_title(title: str) -> str:
    """Clean and normalize a book title."""
    # Remove series info in parentheses
    title = re.sub(r"\s*\([^)]*\)\s*$", "", title)
    # Remove series info after #
    title = re.sub(r"\s*#\d+.*$", "", title)
    return title.strip()


# ─


def _load_seed_data(force: bool = False) -> None:
    """Load the Goodreads CSV into memory if not already loaded."""
    global _SEED_LOADED, _SEED_BOOKS, _SEED_BY_AUTHOR, _SEED_BY_TITLE
    global _SEED_BY_ISBN, _SEED_BY_CATEGORY, _SEED_CATEGORIES

    if _SEED_LOADED and not force:
        return

    csv_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "ml", "Dataset", "books.csv"
    )
    if not os.path.exists(csv_path):
        print(f"  [SEED DATA] CSV not found at: {csv_path}")
        _SEED_LOADED = True  # Mark as loaded so we don't retry every time
        return

    _SEED_BOOKS = []
    _SEED_BY_AUTHOR = defaultdict(list)
    _SEED_BY_TITLE = defaultdict(list)
    _SEED_BY_ISBN = {}
    _SEED_BY_CATEGORY = defaultdict(list)

    try:
        with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    title_raw = row.get("title", "").strip()
                    if not title_raw:
                        continue
                    authors_field = row.get("authors", "Unknown").strip()
                    isbn = (row.get("isbn", "") or "").strip()
                    isbn13 = (row.get("isbn13", "") or "").strip()
                    rating_str = (row.get("average_rating", "0") or "0").strip()
                    pages_str = (row.get("  num_pages", row.get("num_pages", "0")) or "0").strip()
                    ratings_str = (row.get("ratings_count", "0") or "0").strip()
                    pub_date = (row.get("publication_date", "") or "").strip()
                    publisher = (row.get("publisher", "") or "").strip()

                    try:
                        rating = float(rating_str)
                    except ValueError:
                        rating = 0.0
                    try:
                        pages = int(pages_str)
                    except ValueError:
                        pages = 0
                    try:
                        ratings_count = int(ratings_str)
                    except ValueError:
                        ratings_count = 0

                    title_clean = _clean_title(title_raw)
                    authors = _parse_authors(authors_field)
                    primary_author = authors[0]
                    category = _infer_category(title_clean, primary_author, publisher)

                    book = {
                        "seed_id": len(_SEED_BOOKS) + 1,
                        "title": title_clean,
                        "title_raw": title_raw,
                        "author": primary_author,
                        "authors": authors,
                        "isbn": isbn,
                        "isbn13": isbn13,
                        "category": category,
                        "average_rating": rating,
                        "ratings_count": ratings_count,
                        "pages": pages,
                        "publication_date": pub_date,
                        "publisher": publisher,
                        "relevance_score": round(rating * math.log10(max(ratings_count, 1) + 1), 2),
                    }

                    _SEED_BOOKS.append(book)
                    for a in authors:
                        _SEED_BY_AUTHOR[a.lower()].append(book)
                    _SEED_BY_TITLE[title_clean.lower()].append(book)
                    if isbn:
                        _SEED_BY_ISBN[isbn] = book
                    if isbn13:
                        _SEED_BY_ISBN[isbn13] = book
                    _SEED_BY_CATEGORY[category].append(book)

                except (ValueError, KeyError):
                    continue  # Skip malformed rows

        _SEED_CATEGORIES = list(_SEED_BY_CATEGORY.keys())
        _SEED_LOADED = True
        print(
            f"  [SEED DATA] Loaded {len(_SEED_BOOKS)} books from Goodreads dataset ({len(_SEED_CATEGORIES)} categories)"
        )
    except (FileNotFoundError, csv.Error) as e:
        print(f"  [SEED DATA ERROR] Could not load CSV: {e}")
        _SEED_LOADED = True


# ─


def is_seed_available() -> bool:
    """Check if the seed dataset has been loaded with data."""
    _load_seed_data()
    return len(_SEED_BOOKS) > 0


def get_seed_stats() -> dict:
    """Get statistics about the loaded seed dataset."""
    _load_seed_data()
    if not _SEED_BOOKS:
        return {"total": 0, "categories": [], "authors": 0, "avg_rating": 0}
    avg_rating = round(sum(b["average_rating"] for b in _SEED_BOOKS) / len(_SEED_BOOKS), 2)
    unique_authors = len(set(b["author"].lower() for b in _SEED_BOOKS))
    return {
        "total": len(_SEED_BOOKS),
        "categories": _SEED_CATEGORIES,
        "categories_count": len(_SEED_CATEGORIES),
        "authors": unique_authors,
        "avg_rating": avg_rating,
    }


def search_seed(query: str, top_n: int = 20) -> list[dict]:
    """Search the seed database by title, author, or ISBN."""
    _load_seed_data()
    if not _SEED_BOOKS:
        return []
    q = query.lower().strip()
    if not q:
        return []

    scored: list[tuple[float, dict]] = []
    for book in _SEED_BOOKS:
        score = 0.0
        if q in book["title"].lower():
            score += 5.0
            if book["title"].lower().startswith(q):
                score += 3.0
        if q in book["author"].lower():
            score += 4.0
        if book["isbn"] and q.replace("-", "") in book["isbn"].replace("-", ""):
            score += 10.0
        if book["isbn13"] and q in book["isbn13"]:
            score += 10.0
        if any(q in a.lower() for a in book["authors"]):
            score += 3.0
        if q in book["category"].lower():
            score += 2.0
        if score > 0:
            score += book["relevance_score"] * 0.1
            scored.append((score, book))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [dict(b, match_score=round(s, 2)) for s, b in scored[:top_n]]


def recommend_seed_trending(top_n: int = 10) -> list[dict]:
    """Get trending/highly-rated books from the seed dataset."""
    _load_seed_data()
    if not _SEED_BOOKS:
        return []
    ranked = sorted(_SEED_BOOKS, key=lambda b: b["relevance_score"], reverse=True)
    return ranked[:top_n]


def recommend_seed_by_category(category: str, top_n: int = 10) -> list[dict]:
    """Get top books in a category from the seed dataset."""
    _load_seed_data()
    books = _SEED_BY_CATEGORY.get(category, [])
    if not books:
        # Fuzzy match
        for cat_name, cat_books in _SEED_BY_CATEGORY.items():
            if category.lower() in cat_name.lower():
                books = cat_books
                break
    if not books:
        return []
    ranked = sorted(books, key=lambda b: b["relevance_score"], reverse=True)
    return ranked[:top_n]


def recommend_seed_similar(title: str, author: str = "", top_n: int = 5) -> list[dict]:
    """Find books similar to the given title/author from seed data."""
    _load_seed_data()
    if not _SEED_BOOKS:
        return []

    # Find the original book first
    candidates = []
    if author:
        candidates = _SEED_BY_AUTHOR.get(author.lower(), [])
    if not candidates:
        for b in _SEED_BOOKS:
            if b["title"].lower() == title.lower():
                candidates = [b]
                break
    if not candidates:
        for b in _SEED_BOOKS[:10]:
            if title.lower() in b["title"].lower():
                candidates.append(b)

    if not candidates:
        return recommend_seed_trending(top_n)

    target = candidates[0]
    scored: list[tuple[float, dict]] = []
    for book in _SEED_BOOKS:
        if book["seed_id"] == target["seed_id"]:
            continue
        score = 0.0

        # Same category
        if book["category"] == target["category"]:
            score += 3.0

        # Same author
        if book["author"].lower() == target["author"].lower():
            score += 5.0

        # Shared co-authors
        shared_authors = set(a.lower() for a in book["authors"]) & set(
            a.lower() for a in target["authors"]
        )
        score += len(shared_authors) * 5.0

        # Rating bonus
        score += book["average_rating"] * 0.5

        # Popularity bonus
        score += min(math.log10(book["ratings_count"] + 1), 3)

        scored.append((score, book))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [b for _s, b in scored[:top_n]]


def recommend_seed_for_user(
    fav_categories: list[str], fav_authors: list[str], top_n: int = 5
) -> list[dict]:
    """Get personalized recommendations from seed data based on user preferences."""
    _load_seed_data()
    if not _SEED_BOOKS:
        return []

    scored: list[tuple[float, dict]] = []
    for book in _SEED_BOOKS:
        score = 0.0

        # Category match
        for fc in fav_categories:
            if book["category"].lower() == fc.lower():
                score += 3.0

        # Author match
        for fa in fav_authors:
            if fa.lower() in book["author"].lower() or any(
                fa.lower() in a.lower() for a in book["authors"]
            ):
                score += 5.0

        if score == 0:
            continue

        # Rating bonus
        score += book["average_rating"] * 0.3
        score += min(math.log10(book["ratings_count"] + 1), 2)

        scored.append((score, book))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [b for _s, b in scored[:top_n]]


def search_seed_by_isbn(isbn: str) -> dict | None:
    """Look up a book by ISBN in the seed dataset."""
    _load_seed_data()
    isbn_clean = isbn.replace("-", "").strip()
    return _SEED_BY_ISBN.get(isbn_clean)


def get_seed_categories() -> list[str]:
    """Get list of all categories available in the seed dataset."""
    _load_seed_data()
    return list(_SEED_CATEGORIES)


def get_seed_category_counts() -> dict[str, int]:
    """Get count of books per category in the seed dataset."""
    _load_seed_data()
    return {cat: len(books) for cat, books in _SEED_BY_CATEGORY.items()}


def get_seed_author_books(author: str, top_n: int = 10) -> list[dict]:
    """Get books by a specific author from the seed dataset."""
    _load_seed_data()
    books = _SEED_BY_AUTHOR.get(author.lower(), [])
    if not books:
        # Fuzzy search
        for author_key, author_books in _SEED_BY_AUTHOR.items():
            if author.lower() in author_key:
                books = author_books
                break
    if not books:
        return []
    ranked = sorted(books, key=lambda b: b["relevance_score"], reverse=True)
    return ranked[:top_n]


# ─

COLD_START_THRESHOLD = 10  # If library has fewer than this many books, use seed data


def should_use_seed(storage_book_count: int) -> bool:
    """Determine if seed data should be used for recommendations."""
    return storage_book_count < COLD_START_THRESHOLD and is_seed_available()
