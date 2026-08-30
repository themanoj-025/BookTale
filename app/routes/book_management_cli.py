"""
book_management_cli.py - Book management CLI functions (add, search, update, delete).
"""

import json
import os

import requests

from app.config.settings import Config
from app.core.utils import (
    confirm,
    header,
    menu,
    pause,
    print_error,
    print_info,
    print_success,
    print_warning,
    validate_isbn,
)
from app.models.book import CATEGORIES
from app.services.auth.auth import AuthManager
from app.services.books.library import Library
import logging

logger = logging.getLogger(__name__)



def book_management_menu(lib: Library, auth: AuthManager) -> None:
    while True:
        choice = menu(
            "📖 BOOK MANAGEMENT",
            [
                "Add Book",
                "Search / View Books",
                "Update Book",
                "Delete Book (Soft)",
                "Back",
            ],
        )
        if choice == "1":
            add_book_flow(lib, auth)
        elif choice == "2":
            search_books_menu(lib)
        elif choice == "3":
            update_book_flow(lib, auth)
        elif choice == "4":
            delete_book_flow(lib, auth)
        elif choice == "5":
            break


def lookup_isbn(isbn: str) -> dict | None:
    """Look up book details from OpenLibrary API by ISBN."""
    try:
        url = f"{Config.OPENLIBRARY_BASE_URL}/api/books"
        params = {"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"}
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            key = f"ISBN:{isbn}"
            if key in data:
                info = data[key]
                title = info.get("title", "")
                authors = ", ".join(a.get("name", "") for a in info.get("authors", []))
                pages = info.get("number_of_pages", 0)
                return {"title": title, "author": authors, "pages": pages}
    except (requests.RequestException, json.JSONDecodeError):
        pass
    return None


def add_book_flow(lib: Library, auth: AuthManager) -> None:
    header("➕ ADD NEW BOOK")
    title = input("  Title     : ").strip()
    author = input("  Author    : ").strip()
    isbn = input("  ISBN      : ").strip()

    # ISBN auto-lookup
    if isbn and confirm("Auto-fetch book details from OpenLibrary?"):
        info = lookup_isbn(isbn)
        if info:
            if not title and info["title"]:
                title = info["title"]
                print_info(f"Title auto-filled: {title}")
            if not author and info["author"]:
                author = info["author"]
                print_info(f"Author auto-filled: {author}")
            print_success(f"Found: {info['title']} by {info['author']} ({info['pages']} pages)")
        else:
            print_warning("Could not fetch details. Please enter manually.")

    if not validate_isbn(isbn):
        print_warning("Invalid ISBN format.")
        if not confirm("Continue anyway?"):
            return

    logger.info("  Categories:", ", ".join(CATEGORIES))
    category = input("  Category  : ").strip() or "Other"
    if category not in CATEGORIES:
        print_warning(f"'{category}' not in standard list. Using as-is.")

    try:
        copies = int(input("  Copies    : ").strip())
    except ValueError:
        copies = 1

    ok, result = lib.add_book(
        title, author, isbn, category, copies, actor=auth.current_user.user_id
    )
    if ok:
        print_success(f"Book added! ID: {result}")
        _generate_barcode(result, isbn)
    else:
        print_error(result)
    pause()


def _generate_barcode(book_id: str, isbn: str) -> None:
    """Generate a QR code for the book."""
    try:
        import pyqrcode

        qr = pyqrcode.create(isbn or book_id)
        qr_path = os.path.join(Config.DATA_DIR, "barcodes")
        os.makedirs(qr_path, exist_ok=True)
        qr.png(os.path.join(qr_path, f"{book_id}.png"), scale=6)
        print_info(f"QR code saved: {qr_path}\\{book_id}.png")
    except ImportError:
        pass  # QR generation is optional


def search_books_menu(lib: Library) -> None:
    header("🔍 ADVANCED SEARCH")
    logger.info("  Search by: 1.All  2.Title  3.Author  4.ISBN  5.Category  6.Advanced Filters")
    by_map = {"1": "all", "2": "title", "3": "author", "4": "isbn"}
    by_choice = input("  Choice [1]: ").strip() or "1"

    available_only = False
    min_issues = 0
    query = ""
    category = ""
    search_by = "all"

    if by_choice == "5":
        logger.info("  Categories:", ", ".join(CATEGORIES))
        category = input("  Category  : ").strip()
    elif by_choice == "6":
        query = input("  Query     : ").strip()
        logger.info("  Filter by: 1.All  2.Title  3.Author  4.ISBN")
        fb = input("  [1]: ").strip() or "1"
        search_by = {"1": "all", "2": "title", "3": "author", "4": "isbn"}.get(fb, "all")
        logger.info("  Categories:", ", ".join(CATEGORIES))
        cat_str = input("  Category (optional): ").strip()
        if cat_str in CATEGORIES:
            category = cat_str
        avail = input("  Available only? (y/n): ").strip().lower()
        available_only = avail == "y"
        try:
            min_str = input("  Min issues count (0): ").strip()
            if min_str:
                min_issues = int(min_str)
        except ValueError:
            pass
        results = lib.search_books(
            query=query,
            category=category,
            search_by=search_by,
            available_only=available_only,
            min_issues=min_issues,
        )
    else:
        search_by = by_map.get(by_choice, "all")
        query = input("  Query     : ").strip()
        results = lib.search_books(query=query, search_by=search_by)

    logger.info(f"\n  Found {len(results)} book(s):\n")
    for b in results:
        logger.info("%s", b.display())
        print()
    pause()


def update_book_flow(lib: Library, auth: AuthManager) -> None:
    header("✏  UPDATE BOOK")
    book_id = input("  Book ID   : ").strip()
    book = lib.get_book(book_id)
    if not book:
        print_error("Book not found.")
        pause()
        return
    logger.info("\n" + book.display())
    logger.info("\n  Leave blank to keep current value.")
    updates = {}
    for field_name, label in [
        ("title", "Title"),
        ("author", "Author"),
        ("isbn", "ISBN"),
        ("category", "Category"),
    ]:
        val = input(f"  {label} [{getattr(book, field_name)}]: ").strip()
        if val:
            updates[field_name] = val
    copies_str = input(f"  Total Copies [{book.total_copies}]: ").strip()
    if copies_str.isdigit():
        updates["total_copies"] = int(copies_str)

    if updates:
        ok, msg = lib.update_book(book_id, **updates)
        if ok:
            print_success(msg)
        else:
            print_error(msg)
    else:
        logger.info("  No changes made.")
    pause()


def delete_book_flow(lib: Library, auth: AuthManager) -> None:
    header("🗑  DELETE BOOK")
    book_id = input("  Book ID   : ").strip()
    book = lib.get_book(book_id)
    if not book:
        print_error("Book not found.")
        pause()
        return
    logger.info("\n" + book.display())
    if confirm("\n  Soft-delete this book?"):
        ok, msg = lib.delete_book(book_id, actor=auth.current_user.user_id)
        if ok:
            print_success(msg)
        else:
            print_error(msg)
    pause()
