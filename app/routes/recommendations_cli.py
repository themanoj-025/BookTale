"""
recommendations_cli.py - Recommendations and Goodreads Seed Data CLI.
"""

from app.core.utils import (
    create_table,
    header,
    menu,
    pause,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from app.services.auth.auth import AuthManager
from app.services.books.library import Library
from app.services.recommendations.recommender import Recommender


def recommendations_menu(lib: Library, recommender: Recommender, auth) -> None:
    """Admin/Librarian recommendation menu."""
    while True:
        choice = menu(
            "📚 RECOMMENDATIONS",
            [
                "Trending Books (Last 30 Days)",
                "All-Time Bestsellers",
                "Recommend Similar Books",
                "Users Who Borrowed X Also Borrowed Y",
                "Browse by Category",
                "Back",
            ],
        )
        if choice == "1":
            _show_trending(recommender)
        elif choice == "2":
            _show_bestsellers(recommender)
        elif choice == "3":
            _show_similar_books(recommender)
        elif choice == "4":
            _show_frequently_bought(recommender)
        elif choice == "5":
            _browse_by_category(recommender, lib)
        elif choice == "6":
            break


def user_recommendations_menu(lib: Library, recommender: Recommender, auth) -> None:
    """User-specific recommendation menu."""
    while True:
        choice = menu(
            f"🌟 FOR YOU — {auth.current_user.name}",
            [
                "Personalized Recommendations",
                "Trending Books",
                "All-Time Bestsellers",
                "Browse by Category",
                "Back",
            ],
        )
        if choice == "1":
            _show_personalized(recommender, auth.current_user.user_id)
        elif choice == "2":
            _show_trending(recommender)
        elif choice == "3":
            _show_bestsellers(recommender)
        elif choice == "4":
            _browse_by_category(recommender, lib)
        elif choice == "5":
            break


def _show_personalized(recommender: Recommender, user_id: str) -> None:
    """Show personalized recommendations for a user."""
    header("🌟 Personalized Recommendations")
    recs = recommender.recommend_for_user(user_id, top_n=10)
    if not recs:
        print_info("Borrow some books first to get personalized recommendations!")
        print_info("Showing trending books instead:")
        recs = recommender.recommend_trending(top_n=10)
    for r in recs[:5]:
        avail = "✅ Available" if r["available"] > 0 else "❌ Unavailable"
        logger.info(f"\n  📖 [bold]{r['title']}[/bold] — {r['author']}")
        logger.info(f"     Category: {r['category']} | {avail}")
        if "reason" in r:
            logger.info(f"     💡 {r['reason']}")
    pause()


def _show_trending(recommender: Recommender) -> None:
    """Show trending books."""
    header("🔥 Trending Books (Last 30 Days)")
    trending = recommender.recommend_trending(top_n=10)
    for i, r in enumerate(trending, 1):
        avail = "✅" if r["available"] > 0 else "❌"
        logger.info(f"  {i:2}. [{r['book_id']}] {r['title']} — {r['author']} "
            f"({r['category']}) {avail} Issued: {r['issue_count']}×")
    pause()


def _show_bestsellers(recommender: Recommender) -> None:
    """Show all-time bestsellers."""
    header("🏆 All-Time Bestsellers")
    best = recommender.recommend_all_time_best(top_n=10)
    for i, r in enumerate(best, 1):
        avail = "✅" if r["available"] > 0 else "❌"
        logger.info(f"  {i:2}. [{r['book_id']}] {r['title']} — {r['author']} "
            f"({r['category']}) {avail} Issued: {r['issue_count']}×")
    pause()


def _show_similar_books(recommender: Recommender) -> None:
    """Show similar books to a given book."""
    header("🔍 Find Similar Books")
    book_id = input("  Book ID: ").strip()
    recs = recommender.recommend_similar_books(book_id, top_n=5)
    if not recs:
        print_info("No recommendations found for this book.")
    else:
        logger.info(f"\n  Similar books to [bold]{recs[0]['title']}[/bold] (score based):\n")
        for r in recs:
            avail = "✅ Available" if r["available"] > 0 else "❌ Unavailable"
            logger.info(f"  📖 {r['title']} — {r['author']} ({r['category']}) "
                f"Score: {r['score']} | {avail}")
    pause()


def _show_frequently_bought(recommender: Recommender) -> None:
    """Show frequently co-borrowed books."""
    header("🔄 Users Who Borrowed X Also Borrowed Y")
    book_id = input("  Book ID: ").strip()
    recs = recommender.recommend_frequently_bought_together(book_id, top_n=5)
    if not recs:
        print_info("No co-borrowing data available for this book yet.")
    else:
        logger.info(f"\n  Users who borrowed [bold]{recs[0]['title']}[/bold] also borrowed:\n")
        for r in recs:
            avail = "✅" if r["available"] > 0 else "❌"
            logger.info(f"  📖 {r['title']} — {r['author']} "
                f"(borrowed together {r['co_borrow_count']}×) {avail}")
    pause()


def _browse_by_category(recommender: Recommender, lib: Library) -> None:
    """Browse top books by category."""
    header("🗂  Browse by Category")
    cats = recommender.get_all_categories_with_counts()
    for i, c in enumerate(cats, 1):
        logger.info(f"  {i}. {c['category']} ({c['count']} books, {c['total_issues']} issues)")
    logger.info("\n  0. Back")
    try:
        idx = int(input("  Choose category: ").strip())
        if idx <= 0 or idx > len(cats):
            return
        cat = cats[idx - 1]["category"]
        logger.info(f"\n  Top books in [bold]{cat}[/bold]:")
        books = recommender.recommend_by_category(cat)
        for j, b in enumerate(books, 1):
            avail = "✅" if b["available"] > 0 else "❌"
            logger.info(f"  {j}. [{b['book_id']}] {b['title']} — {b['author']} "
                f"({b['issue_count']} issues) {avail}")
    except (ValueError, IndexError):
        pass
    pause()


# ── Seed Data / Goodreads Knowledge Base ──


def seed_recommendations_menu(lib: Library, recommender: Recommender, auth: AuthManager) -> None:
    """Browse recommendations from the Goodreads seed knowledge base."""
    while True:
        choice = menu(
            "📖 GOODREADS KNOWLEDGE BASE",
            [
                "🌐 Seed Data Overview",
                "🔥 Trending (Highest Rated)",
                "🗂  Explore by Category",
                "🔍 Search Seed Dataset",
                "✍️  Books by Author",
                "📋 Seed Category Explorer",
                "Back",
            ],
        )
        if choice == "1":
            _show_seed_stats(recommender)
        elif choice == "2":
            _show_seed_trending(recommender)
        elif choice == "3":
            _show_seed_category(recommender)
        elif choice == "4":
            _show_seed_search(recommender)
        elif choice == "5":
            _show_seed_author_books(recommender)
        elif choice == "6":
            _show_seed_category_explorer(recommender)
        elif choice == "7":
            break


def _show_seed_stats(recommender: Recommender) -> None:
    """Show overview of the Goodreads seed dataset."""
    header("🌐 Goodreads Knowledge Base — Overview")
    stats = recommender.seed_stats()
    if not stats or stats.get("total", 0) == 0:
        print_warning(
            "Seed dataset not available. Ensure books.csv exists in app/services/recommendations/ml/Dataset/"
        )
    else:
        table = create_table(
            "Seed Dataset Statistics",
            ["Metric", "Value"],
            [
                ["Total Books", str(stats["total"])],
                ["Categories", f"{stats['categories_count']}"],
                ["Unique Authors", f"{stats['authors']:,}"],
                ["Average Rating", f"⭐ {stats['avg_rating']}"],
                [
                    "Categories",
                    ", ".join(stats.get("categories", [])[:10])
                    + (
                        f"... and {stats['categories_count'] - 10} more"
                        if stats["categories_count"] > 10
                        else ""
                    ),
                ],
            ],
        )
        logger.info("%s", table)
        print_info(
            "💡 This seed data powers cold-start recommendations when the library has < 10 books."
        )
        print_info(
            "📖 Use 'Import Books from Seed' in admin menu to add select books to the library."
        )
    pause()


def _show_seed_trending(recommender: Recommender) -> None:
    """Show trending/highest-rated books from seed data."""
    header("🔥 Seed Data — Trending (Highest Rated)")
    recs = recommender.recommend_from_seed("trending", top_n=20)
    if not recs:
        print_warning("No seed data available.")
    else:
        for i, r in enumerate(recs, 1):
            logger.info(f"  {i:2}. 📖 {r['title']} — {r['author']} "
                f"({r['category']}) "
                f"⭐ {r.get('average_rating', '?')} "
                f"({r.get('ratings_count', 0):,} ratings)")
    pause()


def _show_seed_category(recommender: Recommender) -> None:
    """Browse seed data by category."""
    cats = recommender.explore_seed_categories()
    header("🗂  Seed Data — Browse by Category")
    if not cats:
        print_warning("No seed data available.")
        pause()
        return
    for i, c in enumerate(cats, 1):
        logger.info(f"  {i:2}. {c['category']:<18} : {c['count']} books")
    logger.info("\n  0. Back")
    try:
        idx = int(input("  Choose category: ").strip())
        if idx <= 0 or idx > len(cats):
            return
        cat = cats[idx - 1]["category"]
        recs = recommender.recommend_from_seed("category", category=cat, top_n=15)
        if recs:
            logger.info(f"\n  📚 Top books in [bold]{cat}[/bold] (from Goodreads):\n")
            for i, r in enumerate(recs, 1):
                logger.info(f"  {i:2}. {r['title']} — {r['author']} "
                    f"(⭐ {r.get('average_rating', '?')}, {r.get('ratings_count', 0):,} ratings)")
    except (ValueError, IndexError):
        pass
    pause()


def _show_seed_search(recommender: Recommender) -> None:
    """Search the Goodreads seed dataset."""
    header("🔍 Seed Data — Search")
    query = input("  Search query: ").strip()
    if not query:
        return
    recs = recommender.search_seed(query, top_n=15)
    if not recs:
        print_info("No results found in seed dataset.")
    else:
        logger.info(f"\n  Found {len(recs)} result(s):\n")
        for i, r in enumerate(recs, 1):
            logger.info(f"  {i:2}. 📖 {r['title']}")
            logger.info(f"      by {r['author']} | {r['category']} | "
                f"⭐ {r.get('average_rating', '?')} "
                f"({r.get('ratings_count', 0):,} ratings)")
    pause()


def _show_seed_author_books(recommender: Recommender) -> None:
    """Look up books by an author in the seed dataset."""
    header("✍️  Seed Data — Books by Author")
    author = input("  Author name: ").strip()
    if not author:
        return
    recs = recommender.recommend_from_seed("author", author=author, top_n=15)
    if not recs:
        print_info(f"No books found for '{author}' in seed dataset.")
    else:
        logger.info(f"\n  Books by [bold]{author}[/bold] in Goodreads dataset:")
        for i, r in enumerate(recs, 1):
            logger.info(f"  {i:2}. {r['title']} ({r['category']}) "
                f"⭐ {r.get('average_rating', '?')} "
                f"({r.get('ratings_count', 0):,} ratings)")
    pause()


def _show_seed_category_explorer(recommender: Recommender) -> None:
    """Explore all categories in the seed dataset with counts."""
    header("📋 Seed Data — Category Explorer")
    cats = recommender.explore_seed_categories()
    if not cats:
        print_warning("No seed data available.")
        pause()
        return
    table = create_table(
        "Categories in Goodreads Knowledge Base",
        ["Category", "Books", "% of Total"],
        [
            [
                c["category"],
                str(c["count"]),
                f"{round(c['count'] / sum(x['count'] for x in cats) * 100, 1)}%",
            ]
            for c in cats
        ],
    )
    logger.info("%s", table)
    pause()


def seed_import_menu(lib: Library, auth: AuthManager) -> None:
    """Import books from the Goodreads seed dataset into the library."""
    header("📥 Import Books from Goodreads Seed")
    try:
        import app.services.recommendations.seed_data as _sd

        _sd_available = True
    except ImportError:
        _sd_available = False

    if not _sd_available:
        print_error("Seed data module not available.")
        pause()
        return

    try:
        from app.models.book import CATEGORIES as _BOOK_CATS
    except ImportError:
        _BOOK_CATS = ["Fiction", "Non-Fiction", "Science", "Other"]

    stats = _sd.get_seed_stats()
    if stats["total"] == 0:
        print_warning("Seed dataset is empty. Make sure books.csv exists.")
        pause()
        return

    logger.info(f"  [cyan]Seed dataset: {stats['total']:,} books across {stats['categories_count']} categories[/cyan]")

    logger.info("\n  Options:")
    logger.info("    1. Import by Category (pick a category)")
    logger.info("    2. Import Trending (top 50 highest rated)")
    logger.info("    3. Import by Author")
    logger.info("    4. Search and Import Specific")
    choice = input("  Choice: ").strip()

    books_to_import = []

    if choice == "1":
        cats = _sd.get_seed_category_counts()
        for i, (c, cnt) in enumerate(
            sorted(cats.items(), key=lambda x: x[1], reverse=True)[:20], 1
        ):
            logger.info(f"  {i:2}. {c:<18} : {cnt} books")
        try:
            idx = int(input("  Choose category: ").strip()) - 1
            cat = sorted(cats.items(), key=lambda x: x[1], reverse=True)[idx][0]
            count_str = input("  How many to import [10]: ").strip()
            count = int(count_str) if count_str.isdigit() else 10
            books_to_import = _sd.recommend_seed_by_category(cat, top_n=count)
        except (ValueError, IndexError):
            print_error("Invalid choice.")
            pause()
            return
    elif choice == "2":
        count_str = input("  How many to import [50]: ").strip()
        count = int(count_str) if count_str.isdigit() else 50
        books_to_import = _sd.recommend_seed_trending(top_n=count)
    elif choice == "3":
        author = input("  Author name: ").strip()
        count_str = input("  How many [10]: ").strip()
        count = int(count_str) if count_str.isdigit() else 10
        books_to_import = _sd.get_seed_author_books(author, top_n=count)
        if not books_to_import:
            print_error(f"No books found for '{author}'.")
            pause()
            return
    elif choice == "4":
        query = input("  Search: ").strip()
        count_str = input("  Max results [10]: ").strip()
        count = int(count_str) if count_str.isdigit() else 10
        books_to_import = _sd.search_seed(query, top_n=count)
        if not books_to_import:
            print_error("No results found.")
            pause()
            return

    if not books_to_import:
        print_warning("No books selected.")
        pause()
        return

    logger.info(f"\n  Found {len(books_to_import)} seed book(s):")
    for i, b in enumerate(books_to_import[:10], 1):
        logger.info(f"  {i:2}. {b['title']} — {b['author']} ({b['category']}) "
            f"⭐ {b.get('average_rating', '?')}")
    if len(books_to_import) > 10:
        logger.info(f"      ... and {len(books_to_import) - 10} more")

    if confirm("\n  Import these books into the library?"):
        imported = 0
        skipped = 0
        for book in books_to_import:
            isbn = book.get("isbn", "") or book.get("isbn13", "")
            cat = book["category"] if book["category"] in _BOOK_CATS else "Other"
            ok, _result = lib.add_book(
                title=book["title"],
                author=book["author"],
                isbn=isbn,
                category=cat,
                total_copies=1,
                actor=auth.current_user.user_id,
            )
            if ok:
                imported += 1
            else:
                skipped += 1
        print_success(f"✅ Imported {imported} book(s) from Goodreads seed data.")
        if skipped > 0:
            print_warning(f"⏭️  Skipped {skipped} (duplicates or errors).")
        from app.core.logger import log

        log(
            f"Imported {imported} books from Goodreads seed data",
            auth.current_user.user_id,
        )
    else:
        print_info("Import cancelled.")
    pause()


# Needed by seed_import_menu
from app.core.utils import confirm
import logging

logger = logging.getLogger(__name__)

