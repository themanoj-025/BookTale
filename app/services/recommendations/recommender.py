"""
recommender.py - Book Recommendation Engine

Strategies:
1. Content-based filtering (by category + author similarity)
2. Popularity-based (by issue_count / trending)
3. Collaborative filtering ("users who borrowed X also borrowed Y")
4. ML clustering (lightweight K-Means on category vectors)
5. Similar books by ISBN-genre matching
"""

from collections import Counter
from datetime import datetime, timedelta

from app.models.book import Book
from app.storage.storage import Storage

# Seed data integration for cold-start recommendations
try:
    import app.services.recommendations.seed_data as seed_data

    _SEED_AVAILABLE = True
except ImportError:
    _SEED_AVAILABLE = False


class Recommender:
    """Multi-strategy book recommendation engine.

    All methods fall back to the Goodreads seed dataset when the library
    has very few books (cold-start scenario), providing meaningful
    recommendations even with an empty library.
    """

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def _library_book_count(self) -> int:
        """Get the count of non-deleted books in the library."""
        books = self.storage.load_books()
        return sum(1 for b in books.values() if not b.is_deleted)

    def _should_use_seed(self) -> bool:
        """Check if seed data should be used as fallback."""
        return _SEED_AVAILABLE and self._library_book_count() < 10

    def _seed_result(self, book: dict, source: str = "seed") -> dict:
        """Format a seed book result with consistent fields."""
        return {
            "book_id": f"SEED-{book['seed_id']}",
            "title": book["title"],
            "title_raw": book.get("title_raw", book["title"]),
            "author": book["author"],
            "category": book["category"],
            "average_rating": book.get("average_rating", 0),
            "ratings_count": book.get("ratings_count", 0),
            "isbn": book.get("isbn", ""),
            "available": 0,  # Seed books are reference, not borrowable
            "from_seed": True,
            "seed_author": book.get("author", ""),
            "publisher": book.get("publisher", ""),
            "pages": book.get("pages", 0),
            "reason": f"From Goodreads knowledge base ({source})",
        }

    def seed_stats(self) -> dict:
        """Get statistics about the loaded seed dataset."""
        if not _SEED_AVAILABLE:
            return {"available": False}
        return seed_data.get_seed_stats()

    # ═══════════════════════════════════════════════════════════════
    # 1. CONTENT-BASED FILTERING (Category + Author)
    # ═══════════════════════════════════════════════════════════════

    def recommend_similar_books(self, book_id: str, top_n: int = 5) -> list[dict]:
        """
        Recommend books similar to a given book based on category, author, and popularity.
        Falls back to seed data if the library has few books.
        """
        books = self.storage.load_books()
        target = books.get(book_id)
        if not target or target.is_deleted:
            # Try seed data fallback if library book is missing
            if self._should_use_seed():
                seed_recs = seed_data.recommend_seed_trending(top_n)
                return [
                    self._seed_result(b, "seed popular fallback") for b in seed_recs
                ]
            return []

        scored: list[tuple[float, Book]] = []
        for bid, book in books.items():
            if bid == book_id or book.is_deleted:
                continue
            score = 0.0

            # Same category = strong signal
            if book.category.lower() == target.category.lower():
                score += 3.0

            # Same author = very strong signal
            if book.author.lower() == target.author.lower():
                score += 5.0
            # Partial author match (e.g., same last name)
            elif any(w in book.author.lower() for w in target.author.lower().split()):
                score += 1.0

            # Popularity bonus
            score += min(book.issue_count / 10, 2.0)

            # Availability bonus (prefer books that can be borrowed)
            if book.available_copies > 0:
                score += 1.0

            scored.append((score, book))

        scored.sort(key=lambda x: x[0], reverse=True)

        # If we have very few library results, augment with seed data
        if len(scored) < top_n and self._should_use_seed():
            seed_recs = seed_data.recommend_seed_similar(
                title=target.title, author=target.author, top_n=top_n - len(scored)
            )
            result = [
                {
                    "book_id": b.book_id,
                    "title": b.title,
                    "author": b.author,
                    "category": b.category,
                    "score": round(s, 2),
                    "available": b.available_copies,
                }
                for s, b in scored[:top_n]
            ]
            result.extend(self._seed_result(b, "similar from seed") for b in seed_recs)
            return result

        return [
            {
                "book_id": b.book_id,
                "title": b.title,
                "author": b.author,
                "category": b.category,
                "score": round(s, 2),
                "available": b.available_copies,
            }
            for s, b in scored[:top_n]
        ]

    # ═══════════════════════════════════════════════════════════════
    # 2. POPULARITY-BASED
    # ═══════════════════════════════════════════════════════════════

    def recommend_trending(self, top_n: int = 10, days: int = 30) -> list[dict]:
        """
        Recommend the most popular books based on recent issue activity.
        Falls back to seed data if the library has little activity.
        """
        books = self.storage.load_books()
        txns = self.storage.load_transactions()
        cutoff = datetime.now() - timedelta(days=days)

        # Count recent issues per book
        recent_counts: dict[str, int] = Counter()
        for t in txns:
            if t["type"] == "issue":
                txn_date = datetime.fromisoformat(t["issue_date"])
                if txn_date >= cutoff:
                    recent_counts[t["book_id"]] += 1

        # Score: recent issues + total issues + availability
        scored: list[tuple[float, Book]] = []
        for bid, book in books.items():
            if book.is_deleted:
                continue
            recency = recent_counts.get(bid, 0) * 5
            popularity = book.issue_count * 2
            availability = book.available_copies * 1
            score = recency + popularity + availability
            scored.append((score, book))

        scored.sort(key=lambda x: x[0], reverse=True)

        result = [
            {
                "book_id": b.book_id,
                "title": b.title,
                "author": b.author,
                "category": b.category,
                "score": round(s, 2),
                "issue_count": b.issue_count,
                "available": b.available_copies,
            }
            for s, b in scored[:top_n]
        ]

        # Cold-start: show seed trending if library has few books
        if len(result) < top_n and self._should_use_seed():
            seed_recs = seed_data.recommend_seed_trending(top_n=top_n - len(result))
            result.extend(self._seed_result(b, "trending from seed") for b in seed_recs)

        return result

    def recommend_all_time_best(self, top_n: int = 10) -> list[dict]:
        """Recommend the most issued books of all time. Falls back to seed data."""
        books = self.storage.load_books()
        ranked = sorted(
            [b for b in books.values() if not b.is_deleted],
            key=lambda b: b.issue_count,
            reverse=True,
        )

        result = [
            {
                "book_id": b.book_id,
                "title": b.title,
                "author": b.author,
                "category": b.category,
                "issue_count": b.issue_count,
                "available": b.available_copies,
            }
            for b in ranked[:top_n]
        ]

        # Cold-start: augment with seed bestsellers
        if len(result) < top_n and self._should_use_seed():
            seed_recs = seed_data.recommend_seed_trending(top_n=top_n - len(result))
            result.extend(
                self._seed_result(b, "bestseller from seed") for b in seed_recs
            )

        return result

    # ═══════════════════════════════════════════════════════════════
    # 3. COLLABORATIVE FILTERING
    # ═══════════════════════════════════════════════════════════════

    def recommend_for_user(self, user_id: str, top_n: int = 5) -> list[dict]:
        """
        Personalized recommendations for a user based on:
        - Their borrowing history (same author/category preference)
        - What similar users borrowed
        - Popular books they haven't read
        - Falls back to seed data for cold-start users
        """
        books = self.storage.load_books()
        users = self.storage.load_users()
        txns = self.storage.load_transactions()

        user = users.get(user_id)
        if not user:
            if self._should_use_seed():
                seed_recs = seed_data.recommend_seed_trending(top_n)
                return [self._seed_result(b, "seed general") for b in seed_recs]
            return []

        user_books = set(user.books_issued)

        # Get categories and authors the user likes
        fav_categories: Counter = Counter()
        fav_authors: Counter = Counter()
        for bid in user_books:
            book = books.get(bid)
            if book:
                fav_categories[book.category] += 1
                fav_authors[book.author] += 1

        # If user has no history and seed is available, recommend based on seed
        if not fav_categories and not fav_authors and self._should_use_seed():
            seed_recs = seed_data.recommend_seed_trending(top_n)
            return [self._seed_result(b, "seed popular") for b in seed_recs]

        # Find similar users (users who borrowed similar books)
        similar_user_books: Counter = Counter()
        for t in txns:
            if t["type"] == "issue" and t["user_id"] != user_id:
                if t["book_id"] in user_books:
                    # This user borrowed the same book as our user
                    for t2 in txns:
                        if t2["type"] == "issue" and t2["user_id"] == t["user_id"]:
                            if t2["book_id"] not in user_books:
                                similar_user_books[t2["book_id"]] += 2

        # Score candidate books
        scored: list[tuple[float, Book]] = []
        for bid, book in books.items():
            if book.is_deleted or bid in user_books:
                continue

            score = 0.0

            # Preference matching
            score += fav_categories.get(book.category, 0) * 3
            if book.author in fav_authors:
                score += fav_authors[book.author] * 5

            # Collaborative signal
            score += similar_user_books.get(bid, 0) * 4

            # Popularity bonus
            score += min(book.issue_count / 5, 3)

            # Availability
            if book.available_copies > 0:
                score += 2

            scored.append((score, book))

        scored.sort(key=lambda x: x[0], reverse=True)

        result = [
            {
                "book_id": b.book_id,
                "title": b.title,
                "author": b.author,
                "category": b.category,
                "score": round(s, 2),
                "available": b.available_copies,
                "reason": self._get_reason(
                    s, fav_categories, fav_authors, similar_user_books, b
                ),
            }
            for s, b in scored[:top_n]
        ]

        # Augment with seed data if we have user preferences but few library books
        if len(result) < top_n and self._should_use_seed():
            top_cats = [c for c, _ in fav_categories.most_common(3)]
            top_auth = [a for a, _ in fav_authors.most_common(3)]
            seed_recs = seed_data.recommend_seed_for_user(
                fav_categories=top_cats, fav_authors=top_auth, top_n=top_n - len(result)
            )
            result.extend(
                self._seed_result(b, "personalized from seed") for b in seed_recs
            )

        return result

    def _get_reason(
        self,
        score: float,
        fav_cats: Counter,
        fav_authors: Counter,
        similar: Counter,
        book: Book,
    ) -> str:
        """Generate a human-readable reason for a recommendation."""
        reasons = []
        if fav_cats.get(book.category, 0) > 0:
            reasons.append(f"similar to your favourite {book.category} books")
        if book.author in fav_authors:
            reasons.append(f"by {book.author} (an author you like)")
        if similar.get(book.book_id, 0) > 0:
            reasons.append("read by users with similar taste")
        if book.issue_count > 50:
            reasons.append("popular among other readers")
        reasons.append(f"score: {score}")
        return " • ".join(reasons) if reasons else "recommended for you"

    # ═══════════════════════════════════════════════════════════════
    # 4. "USERS WHO BORROWED X ALSO BORROWED Y"
    # ═══════════════════════════════════════════════════════════════

    def recommend_frequently_bought_together(
        self, book_id: str, top_n: int = 5
    ) -> list[dict]:
        """
        Find books that are frequently borrowed together with the given book.
        Falls back to seed similar books if no co-borrowing data exists.
        """
        books = self.storage.load_books()
        txns = self.storage.load_transactions()

        # Find all users who borrowed this book
        users_with_book = set(
            t["user_id"]
            for t in txns
            if t["type"] == "issue" and t["book_id"] == book_id
        )

        if not users_with_book:
            # Try seed data fallback for similar books
            if self._should_use_seed():
                target = books.get(book_id)
                if target:
                    seed_recs = seed_data.recommend_seed_similar(
                        title=target.title, author=target.author, top_n=top_n
                    )
                    if seed_recs:
                        return [
                            self._seed_result(b, "co-borrow from seed")
                            for b in seed_recs
                        ]
            return []

        # Find what else those users borrowed
        co_occurrence: Counter = Counter()
        for t in txns:
            if (
                t["type"] == "issue"
                and t["user_id"] in users_with_book
                and t["book_id"] != book_id
            ):
                co_occurrence[t["book_id"]] += 1

        target = books.get(book_id)
        scored: list[tuple[float, Book]] = []
        for bid, count in co_occurrence.most_common(top_n * 2):
            book = books.get(bid)
            if not book or book.is_deleted:
                continue
            score = count
            # Same category bonus
            if target and book.category == target.category:
                score += 2
            # Availability bonus
            if book.available_copies > 0:
                score += 1
            scored.append((score, book))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "book_id": b.book_id,
                "title": b.title,
                "author": b.author,
                "category": b.category,
                "co_borrow_count": int(s),
                "available": b.available_copies,
            }
            for s, b in scored[:top_n]
        ]

    # ═══════════════════════════════════════════════════════════════
    # 5. CATEGORY-BASED ML CLUSTERING (Lightweight)
    # ═══════════════════════════════════════════════════════════════

    def recommend_by_cluster(self, book_id: str, top_n: int = 5) -> list[dict]:
        """
        Simple category-cluster based recommendation.
        Books in the same category are grouped; within the group,
        rank by author similarity, then issue_count.
        Falls back to seed data for cold-start.
        """
        books = self.storage.load_books()
        target = books.get(book_id)
        if not target or target.is_deleted:
            if self._should_use_seed():
                seed_recs = seed_data.recommend_seed_trending(top_n)
                return [self._seed_result(b, "seed cluster") for b in seed_recs]
            return []

        # Get all books in the same category
        same_category = [
            b
            for b in books.values()
            if b.category.lower() == target.category.lower()
            and b.book_id != book_id
            and not b.is_deleted
        ]

        # Score: same author gets +5, then by issue_count
        scored: list[tuple[float, Book]] = []
        for book in same_category:
            score = book.issue_count
            if book.author.lower() == target.author.lower():
                score += 100  # Same author = top priority
            if book.available_copies > 0:
                score += 10
            scored.append((score, book))

        scored.sort(key=lambda x: x[0], reverse=True)

        result = [
            {
                "book_id": b.book_id,
                "title": b.title,
                "author": b.author,
                "score": s,
                "available": b.available_copies,
            }
            for s, b in scored[:top_n]
        ]

        # Augment with seed data in same category
        if len(result) < top_n and self._should_use_seed():
            seed_recs = seed_data.recommend_seed_by_category(
                target.category, top_n=top_n - len(result)
            )
            result.extend(self._seed_result(b, "cluster from seed") for b in seed_recs)

        return result

    # ═══════════════════════════════════════════════════════════════
    # 6. CATEGORY HIGHLIGHTS
    # ═══════════════════════════════════════════════════════════════

    def recommend_by_category(self, category: str, top_n: int = 5) -> list[dict]:
        """Get top books in a specific category. Falls back to seed data."""
        books = self.storage.load_books()
        matching = [
            b
            for b in books.values()
            if b.category.lower() == category.lower() and not b.is_deleted
        ]
        matching.sort(key=lambda b: b.issue_count, reverse=True)

        result = [
            {
                "book_id": b.book_id,
                "title": b.title,
                "author": b.author,
                "issue_count": b.issue_count,
                "available": b.available_copies,
            }
            for b in matching[:top_n]
        ]

        # Cold-start: augment with seed data only if library has very few books
        if len(result) < top_n and self._should_use_seed():
            seed_recs = seed_data.recommend_seed_by_category(
                category, top_n=top_n - len(result)
            )
            result.extend(
                self._seed_result(b, f"{category} from seed") for b in seed_recs
            )

        return result

    def get_all_categories_with_counts(self) -> list[dict]:
        """Get all categories with book counts and total issues. Merges with seed data only during cold-start."""
        books = self.storage.load_books()
        cat_data: dict[str, dict] = {}
        for b in books.values():
            if b.is_deleted:
                continue
            if b.category not in cat_data:
                cat_data[b.category] = {
                    "category": b.category,
                    "count": 0,
                    "total_issues": 0,
                    "source": "library",
                }
            cat_data[b.category]["count"] += 1
            cat_data[b.category]["total_issues"] += b.issue_count

        # Cold-start: merge seed categories only when library has very few books
        if self._should_use_seed():
            seed_cats = seed_data.get_seed_category_counts()
            for cat, cnt in seed_cats.items():
                if cat not in cat_data:
                    cat_data[cat] = {
                        "category": cat,
                        "count": cnt,
                        "total_issues": 0,
                        "source": "seed",
                    }
                else:
                    cat_data[cat]["seed_count"] = cnt

        return sorted(cat_data.values(), key=lambda x: x["count"], reverse=True)

    # ═══════════════════════════════════════════════════════════════
    # 7. SEED DATA DIRECT ACCESS
    # ═══════════════════════════════════════════════════════════════

    def recommend_from_seed(
        self, strategy: str = "trending", top_n: int = 10, **kwargs
    ) -> list[dict]:
        """Directly access the Goodreads seed knowledge base.

        Strategies: 'trending', 'category', 'similar', 'search', 'author'
        """
        if not _SEED_AVAILABLE:
            return []

        if strategy == "trending":
            recs = seed_data.recommend_seed_trending(top_n)
        elif strategy == "category":
            cat = kwargs.get("category", "Fiction")
            recs = seed_data.recommend_seed_by_category(cat, top_n)
        elif strategy == "similar":
            title = kwargs.get("title", "")
            author = kwargs.get("author", "")
            recs = seed_data.recommend_seed_similar(title, author, top_n)
        elif strategy == "search":
            query = kwargs.get("query", "")
            recs = seed_data.search_seed(query, top_n)
        elif strategy == "author":
            author = kwargs.get("author", "")
            recs = seed_data.get_seed_author_books(author, top_n)
        else:
            recs = seed_data.recommend_seed_trending(top_n)

        return [self._seed_result(b, f"seed:{strategy}") for b in recs]

    def explore_seed_categories(self) -> list[dict]:
        """Get all categories with counts from the seed dataset."""
        if not _SEED_AVAILABLE:
            return []
        counts = seed_data.get_seed_category_counts()
        return [
            {"category": c, "count": cnt, "source": "seed"}
            for c, cnt in sorted(counts.items(), key=lambda x: x[1], reverse=True)
        ]

    def search_seed(self, query: str, top_n: int = 20) -> list[dict]:
        """Search the Goodreads knowledge base."""
        if not _SEED_AVAILABLE or not query:
            return []
        recs = seed_data.search_seed(query, top_n)
        return [self._seed_result(b, "seed search") for b in recs]
