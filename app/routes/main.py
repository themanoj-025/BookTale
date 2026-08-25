"""
main.py - Library Management System CLI (Enhanced)
"""

import csv
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests

from app.config.settings import Config
from app.core.exceptions import AuthenticationError
from app.core.logger import get_logs, log
from app.core.utils import (
    colored,
    confirm,
    console,
    create_table,
    format_date,
    header,
    menu,
    pause,
    print_error,
    print_info,
    print_success,
    print_warning,
    validate_email,
    validate_isbn,
)
from app.db.storage_adapter import create_storage
from app.models.book import CATEGORIES
from app.models.user import ROLES
from app.services.auth.auth import AuthManager, hash_password
from app.services.books.backup import create_backup, list_backups, restore_backup
from app.services.books.library import Library
from app.services.notifications.notifications import NotificationManager
from app.services.recommendations.recommender import Recommender
from app.storage.storage import Storage

# ─


def bootstrap(storage: Storage, auth: AuthManager) -> None:
    """Create default admin if no users exist."""
    users = storage.load_users()
    if not users:
        import secrets

        admin_password = Config.DEFAULT_ADMIN_PASSWORD
        if not admin_password:
            admin_password = secrets.token_urlsafe(16)
            print_warning("⚠  DEFAULT_ADMIN_PASSWORD not set! Using a randomly generated password.")
            print_warning(f"   Admin ID: {Config.DEFAULT_ADMIN_ID}")
            print_warning(f"   Admin Password: {admin_password}")
            print_warning(
                "   ⚠  Set DEFAULT_ADMIN_PASSWORD in your .env file to use a custom password."
            )
        lib = Library(storage)
        lib.register_user(
            user_id=Config.DEFAULT_ADMIN_ID,
            name="System Admin",
            email="admin@library.com",
            phone="0000000000",
            role="admin",
            password_hash=hash_password(admin_password),
            actor="Bootstrap",
        )
        print_success(
            f"Default admin created. ID: {Config.DEFAULT_ADMIN_ID} | Password: {admin_password}"
        )
        print_warning("Change the default password after first login!")


# ─


def login_screen(auth: AuthManager) -> bool:
    header("🔐 Library Management System — Login")
    uid = console.input("  [cyan]User ID[/cyan]   : ").strip()
    pwd = console.input("  [cyan]Password[/cyan]  : ").strip()
    try:
        user = auth.login(uid, pwd)
        if not user:
            return False
        print_success(f"Welcome, {user.name}! [{user.role.upper()}]")
        log("Login", user.user_id)
        return True
    except AuthenticationError:
        print_error("Invalid credentials.")
        return False


def show_notification_badge(notif_mgr: NotificationManager, user_id: str) -> None:
    """Show notification badge if there are unread notifications."""
    count = notif_mgr.get_unread_count(user_id)
    if count > 0:
        print_info(f"You have {count} unread notification{'s' if count > 1 else ''}!")


# ADMIN MENUS


def admin_menu(lib: Library, auth: AuthManager, storage: Storage):
    notif_mgr = NotificationManager(storage)
    recommender = Recommender(storage)
    show_notification_badge(notif_mgr, auth.current_user.user_id)
    while True:
        choice = menu(
            f"🛠  ADMIN PANEL — {auth.current_user.name}",
            [
                "Book Management",
                "User Management",
                "Issue / Return",
                "Reports & Analytics",
                "Overdue Tracking",
                "Fine Management",
                "Reservations",
                "📚 Recommendations",
                "🔔 Notifications",
                "📧 Send Overdue Email Alerts",
                "📖 Goodreads Seed Recommendations",
                "📥 Import Books from Seed",
                "Backup & Restore",
                "View Activity Logs",
                "Export Reports (CSV)",
                "Logout",
            ],
        )
        if choice == "1":
            book_management_menu(lib, auth)
        elif choice == "2":
            user_management_menu(lib, auth, storage)
        elif choice == "3":
            issue_return_menu(lib, auth)
        elif choice == "4":
            reports_menu(lib)
        elif choice == "5":
            overdue_menu(lib)
        elif choice == "6":
            fine_management_menu(lib, auth)
        elif choice == "7":
            reservations_menu(lib, storage)
        elif choice == "8":
            recommendations_menu(lib, recommender, auth)
        elif choice == "9":
            notifications_menu(notif_mgr, auth.current_user.user_id)
        elif choice == "10":
            email_overdue_alerts(lib)
        elif choice == "11":
            seed_recommendations_menu(lib, recommender, auth)
        elif choice == "12":
            seed_import_menu(lib, auth)
        elif choice == "13":
            backup_restore_menu(auth)
        elif choice == "14":
            logs_menu()
        elif choice == "15":
            export_reports_menu(lib)
        elif choice == "16":
            auth.logout()
            log("Logout", auth.current_user.user_id if auth.current_user else "?")
            break


def librarian_menu(lib: Library, auth: AuthManager, storage: Storage):
    notif_mgr = NotificationManager(storage)
    recommender = Recommender(storage)
    show_notification_badge(notif_mgr, auth.current_user.user_id)
    while True:
        choice = menu(
            f"📚 LIBRARIAN PANEL — {auth.current_user.name}",
            [
                "Issue Book",
                "Return Book",
                "Search Books",
                "View Overdue",
                "Reservations",
                "📚 Recommendations",
                "🔔 Notifications",
                "Logout",
            ],
        )
        if choice == "1":
            issue_book_flow(lib, auth)
        elif choice == "2":
            return_book_flow(lib, auth)
        elif choice == "3":
            search_books_menu(lib)
        elif choice == "4":
            overdue_menu(lib)
        elif choice == "5":
            reservations_menu(lib, storage)
        elif choice == "6":
            recommendations_menu(lib, recommender, auth)
        elif choice == "7":
            notifications_menu(notif_mgr, auth.current_user.user_id)
        elif choice == "8":
            auth.logout()
            break


def user_menu(lib: Library, auth: AuthManager):
    notif_mgr = NotificationManager(lib.storage)
    recommender = Recommender(lib.storage)
    show_notification_badge(notif_mgr, auth.current_user.user_id)
    while True:
        choice = menu(
            f"👤 USER PANEL — {auth.current_user.name}",
            [
                "Search Books",
                "My Issued Books",
                "My Fine Status",
                "📚 For You (Recommendations)",
                "🔔 Notifications",
                "Logout",
            ],
        )
        if choice == "1":
            search_books_menu(lib)
        elif choice == "2":
            my_books(lib, auth)
        elif choice == "3":
            my_fine(auth)
        elif choice == "4":
            user_recommendations_menu(lib, recommender, auth)
        elif choice == "5":
            notifications_menu(notif_mgr, auth.current_user.user_id)
        elif choice == "6":
            auth.logout()
            break


# BOOK MANAGEMENT


def book_management_menu(lib: Library, auth: AuthManager):
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


def add_book_flow(lib: Library, auth: AuthManager):
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

    print("  Categories:", ", ".join(CATEGORIES))
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


def search_books_menu(lib: Library):
    header("🔍 ADVANCED SEARCH")
    print("  Search by: 1.All  2.Title  3.Author  4.ISBN  5.Category  6.Advanced Filters")
    by_map = {"1": "all", "2": "title", "3": "author", "4": "isbn"}
    by_choice = input("  Choice [1]: ").strip() or "1"

    available_only = False
    min_issues = 0
    query = ""
    category = ""
    search_by = "all"

    if by_choice == "5":
        print("  Categories:", ", ".join(CATEGORIES))
        category = input("  Category  : ").strip()
    elif by_choice == "6":
        query = input("  Query     : ").strip()
        print("  Filter by: 1.All  2.Title  3.Author  4.ISBN")
        fb = input("  [1]: ").strip() or "1"
        search_by = {"1": "all", "2": "title", "3": "author", "4": "isbn"}.get(fb, "all")
        print("  Categories:", ", ".join(CATEGORIES))
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

    print(f"\n  Found {len(results)} book(s):\n")
    for b in results:
        print(b.display())
        print()
    pause()


def update_book_flow(lib: Library, auth: AuthManager):
    header("✏  UPDATE BOOK")
    book_id = input("  Book ID   : ").strip()
    book = lib.get_book(book_id)
    if not book:
        print_error("Book not found.")
        pause()
        return
    print("\n" + book.display())
    print("\n  Leave blank to keep current value.")
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
        print("  No changes made.")
    pause()


def delete_book_flow(lib: Library, auth: AuthManager):
    header("🗑  DELETE BOOK")
    book_id = input("  Book ID   : ").strip()
    book = lib.get_book(book_id)
    if not book:
        print_error("Book not found.")
        pause()
        return
    print("\n" + book.display())
    if confirm("\n  Soft-delete this book?"):
        ok, msg = lib.delete_book(book_id, actor=auth.current_user.user_id)
        if ok:
            print_success(msg)
        else:
            print_error(msg)
    pause()


# USER MANAGEMENT


def user_management_menu(lib: Library, auth: AuthManager, storage: Storage):
    while True:
        choice = menu(
            "👥 USER MANAGEMENT",
            [
                "Register User",
                "View User Details",
                "Block / Unblock User",
                "Renew Membership",
                "List All Users",
                "Back",
            ],
        )
        if choice == "1":
            register_user_flow(lib, auth)
        elif choice == "2":
            view_user_flow(storage)
        elif choice == "3":
            block_unblock_user_flow(lib, auth)
        elif choice == "4":
            renew_membership_flow(lib, auth)
        elif choice == "5":
            list_users(storage)
        elif choice == "6":
            break


def register_user_flow(lib: Library, auth: AuthManager):
    header("➕ REGISTER USER")
    uid = input("  User ID   : ").strip()
    name = input("  Name      : ").strip()
    email = input("  Email     : ").strip()
    if not validate_email(email):
        print_warning("Invalid email.")
    phone = input("  Phone     : ").strip()
    print("  Roles:", ", ".join(ROLES))
    role = input("  Role [user]: ").strip() or "user"
    if role not in ROLES:
        print_error("Invalid role.")
        pause()
        return
    pwd = input("  Password  : ").strip()
    # Phase 4 (P1): policy aligned with the web layer (>=12 chars).
    if len(pwd) < 12:
        print_warning("Password should be at least 12 characters.")

    ok, msg = lib.register_user(
        uid,
        name,
        email,
        phone,
        role,
        hash_password(pwd),
        actor=auth.current_user.user_id,
    )
    if ok:
        print_success(msg)
    else:
        print_error(msg)
    pause()


def view_user_flow(storage: Storage):
    header("👤 VIEW USER")
    uid = input("  User ID   : ").strip()
    user = storage.load_users().get(uid)
    if user:
        print("\n" + user.display())
    else:
        print_error("User not found.")
    pause()


def block_unblock_user_flow(lib: Library, auth: AuthManager) -> dict:
    header("🔒 BLOCK / UNBLOCK USER")
    uid = input("  User ID   : ").strip()
    user = lib.get_user(uid)
    if not user:
        print_error("User not found.")
        pause()
        return
    print(f"\n  {user.name} — Status: {user.membership_status}")
    action = input("  [b]lock / [u]nblock: ").strip().lower()
    if action == "b":
        ok, msg = lib.block_user(uid, auth.current_user.user_id)
    elif action == "u":
        ok, msg = lib.unblock_user(uid, auth.current_user.user_id)
    else:
        msg, ok = "Cancelled.", False
    if ok:
        print_success(msg)
    else:
        print_error(msg)
    pause()


def renew_membership_flow(lib: Library, auth: AuthManager):
    header("🔄 RENEW MEMBERSHIP")
    uid = input("  User ID   : ").strip()
    days_str = input("  Days [365]: ").strip() or "365"
    try:
        days = int(days_str)
    except ValueError:
        days = 365
    ok, msg = lib.renew_membership(uid, days, auth.current_user.user_id)
    if ok:
        print_success(msg)
    else:
        print_error(msg)
    pause()


def list_users(storage: Storage):
    header("📋 ALL USERS")
    users = storage.load_users()
    for u in users.values():
        status_color = "green" if u.membership_status == "Active" else "red"
        print(
            f"  [{u.user_id}] {u.name} | {u.role.upper()} | "
            f"{colored(u.membership_status, status_color)} | "
            f"Books: {len(u.books_issued)} | Fine: ₹{u.unpaid_fine:.2f}"
        )
    pause()


# ISSUE / RETURN


def issue_return_menu(lib: Library, auth: AuthManager):
    while True:
        choice = menu("📤 ISSUE / RETURN", ["Issue Book", "Return Book", "Back"])
        if choice == "1":
            issue_book_flow(lib, auth)
        elif choice == "2":
            return_book_flow(lib, auth)
        elif choice == "3":
            break


def issue_book_flow(lib: Library, auth: AuthManager) -> dict:
    header("📤 ISSUE BOOK")
    uid = input("  User ID   : ").strip()
    bid = input("  Book ID   : ").strip()
    ok, msg = lib.issue_book(uid, bid, actor=auth.current_user.user_id)
    if ok:
        print_success(msg)
    else:
        print_error(msg)
    pause()


def return_book_flow(lib: Library, auth: AuthManager):
    header("📥 RETURN BOOK")
    uid = input("  User ID   : ").strip()
    bid = input("  Book ID   : ").strip()
    ok, msg, fine = lib.return_book(uid, bid, actor=auth.current_user.user_id)
    if ok:
        print_success(msg)
    else:
        print_error(msg)
    if fine > 0:
        print_warning(f"Fine of ₹{fine:.2f} added to user account.")
    pause()


# REPORTS


def reports_menu(lib: Library):
    while True:
        choice = menu(
            "📊 REPORTS & ANALYTICS",
            [
                "Most Issued Books",
                "Active Users",
                "Issued Today / This Month",
                "Fine Collection Report",
                "Category-wise Book Count",
                "Back",
            ],
        )
        if choice == "1":
            data = lib.report_most_issued()
            header("📚 Most Issued Books")
            for i, r in enumerate(data, 1):
                print(
                    f"  {i:2}. [{r['id']}] {r['title']} — {r['author']} " f"| Issued {r['count']}×"
                )
        elif choice == "2":
            data = lib.report_active_users()
            header("🏆 Most Active Users")
            for i, r in enumerate(data, 1):
                print(f"  {i:2}. [{r['user_id']}] {r['name']} — {r['total_issues']} issues")
        elif choice == "3":
            header("📅 Issue Counts")
            print(f"  Today         : {lib.report_issued_today()} books")
            print(f"  This Month    : {lib.report_issued_this_month()} books")
        elif choice == "4":
            r = lib.report_fine_collection()
            header("💰 Fine Collection Report")
            print(f"  Total Fines   : ₹{r['total']:.2f}")
            print(f"  Collected     : ₹{r['collected']:.2f}")
            print(f"  Pending       : ₹{r['pending']:.2f}")
            print(f"  Transactions  : {r['count']}")
        elif choice == "5":
            data = lib.report_category_count()
            header("🗂  Category-wise Book Count")
            for cat, cnt in data.items():
                print(f"  {cat:<20} : {cnt} book(s)")
        elif choice == "6":
            break
        pause()


# EXPORT REPORTS


def export_reports_menu(lib: Library):
    """Export various reports to CSV."""
    header("📤 EXPORT REPORTS TO CSV")
    print("  1. Export Most Issued Books")
    print("  2. Export All Books Inventory")
    print("  3. Export Active Users")
    print("  4. Export All Transactions")
    choice = input("  Choice: ").strip()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(Config.DATA_DIR, exist_ok=True)

    if choice == "1":
        data = lib.report_most_issued(50)
        path = os.path.join(Config.DATA_DIR, f"most_issued_{timestamp}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["id", "title", "author", "count"])
            w.writeheader()
            w.writerows(data)
        print_success(f"Exported to: {path}")
    elif choice == "2":
        books = [b for b in lib.storage.load_books().values() if not b.is_deleted]
        path = os.path.join(Config.DATA_DIR, f"inventory_{timestamp}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "book_id",
                    "title",
                    "author",
                    "isbn",
                    "category",
                    "total_copies",
                    "available_copies",
                    "issue_count",
                ],
            )
            w.writeheader()
            for b in books:
                w.writerow(b.to_dict())
        print_success(f"Exported to: {path}")
    elif choice == "3":
        data = lib.report_active_users(50)
        path = os.path.join(Config.DATA_DIR, f"active_users_{timestamp}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["user_id", "name", "total_issues"])
            w.writeheader()
            w.writerows(data)
        print_success(f"Exported to: {path}")
    elif choice == "4":
        txns = lib.storage.load_transactions()
        path = os.path.join(Config.DATA_DIR, f"transactions_{timestamp}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "txn_id",
                    "type",
                    "user_id",
                    "book_id",
                    "issue_date",
                    "due_date",
                    "return_date",
                    "fine",
                ],
            )
            w.writeheader()
            w.writerows(txns)
        print_success(f"Exported to: {path}")
    pause()


# OVERDUE


def overdue_menu(lib: Library):
    header("⏰ OVERDUE BOOKS")
    records = lib.get_overdue_list()
    if not records:
        print_success("No overdue books!")
    else:
        table = create_table(
            "Overdue Books",
            ["User", "Book", "Due Date", "Days Late", "Fine"],
            [
                [
                    r["user"],
                    r["book"],
                    r["due_date"],
                    str(r["days_overdue"]),
                    f"₹{r['accrued_fine']:.2f}",
                ]
                for r in records
            ],
        )
        console.print(table)
    pause()


# FINE MANAGEMENT


def fine_management_menu(lib: Library, auth: AuthManager):
    header("💳 FINE MANAGEMENT")
    uid = input("  User ID   : ").strip()
    user = lib.get_user(uid)
    if not user:
        print_error("User not found.")
        pause()
        return
    print(f"\n  {user.name} — Unpaid Fine: ₹{user.unpaid_fine:.2f}")
    if user.unpaid_fine > 0:
        try:
            amount = float(input("  Amount to collect (0 = full): ").strip() or "0")
        except ValueError:
            amount = 0
        if amount == 0:
            amount = user.unpaid_fine
        ok, msg = lib.pay_fine(uid, amount, actor=auth.current_user.user_id)
        if ok:
            print_success(msg)
        else:
            print_error(msg)
    pause()


# RESERVATIONS


def reservations_menu(lib: Library, storage: Storage):
    header("📌 RESERVATION QUEUE")
    res = storage.load_reservations()
    books = storage.load_books()
    users = storage.load_users()
    if not res:
        print("  No active reservations.")
    for bid, queue in res.items():
        book = books.get(bid)
        title = book.title if book else bid
        avail = book.available_copies if book else 0
        print(f"\n  📗 {title} (Available: {avail})")
        for i, uid in enumerate(queue, 1):
            u = users.get(uid)
            print(f"     {i}. {u.name if u else uid} [{uid}]")
    pause()


# RECOMMENDATIONS


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
        print(f"\n  📖 [bold]{r['title']}[/bold] — {r['author']}")
        print(f"     Category: {r['category']} | {avail}")
        if "reason" in r:
            print(f"     💡 {r['reason']}")
    pause()


def _show_trending(recommender: Recommender) -> None:
    """Show trending books."""
    header("🔥 Trending Books (Last 30 Days)")
    trending = recommender.recommend_trending(top_n=10)
    for i, r in enumerate(trending, 1):
        avail = "✅" if r["available"] > 0 else "❌"
        print(
            f"  {i:2}. [{r['book_id']}] {r['title']} — {r['author']} "
            f"({r['category']}) {avail} Issued: {r['issue_count']}×"
        )
    pause()


def _show_bestsellers(recommender: Recommender) -> None:
    """Show all-time bestsellers."""
    header("🏆 All-Time Bestsellers")
    best = recommender.recommend_all_time_best(top_n=10)
    for i, r in enumerate(best, 1):
        avail = "✅" if r["available"] > 0 else "❌"
        print(
            f"  {i:2}. [{r['book_id']}] {r['title']} — {r['author']} "
            f"({r['category']}) {avail} Issued: {r['issue_count']}×"
        )
    pause()


def _show_similar_books(recommender: Recommender) -> None:
    """Show similar books to a given book."""
    header("🔍 Find Similar Books")
    book_id = input("  Book ID: ").strip()
    recs = recommender.recommend_similar_books(book_id, top_n=5)
    if not recs:
        print_info("No recommendations found for this book.")
    else:
        print(f"\n  Similar books to [bold]{recs[0]['title']}[/bold] (score based):\n")
        for r in recs:
            avail = "✅ Available" if r["available"] > 0 else "❌ Unavailable"
            print(
                f"  📖 {r['title']} — {r['author']} ({r['category']}) "
                f"Score: {r['score']} | {avail}"
            )
    pause()


def _show_frequently_bought(recommender: Recommender) -> None:
    """Show frequently co-borrowed books."""
    header("🔄 Users Who Borrowed X Also Borrowed Y")
    book_id = input("  Book ID: ").strip()
    recs = recommender.recommend_frequently_bought_together(book_id, top_n=5)
    if not recs:
        print_info("No co-borrowing data available for this book yet.")
    else:
        print(f"\n  Users who borrowed [bold]{recs[0]['title']}[/bold] also borrowed:\n")
        for r in recs:
            avail = "✅" if r["available"] > 0 else "❌"
            print(
                f"  📖 {r['title']} — {r['author']} "
                f"(borrowed together {r['co_borrow_count']}×) {avail}"
            )
    pause()


def _browse_by_category(recommender: Recommender, lib: Library) -> None:
    """Browse top books by category."""
    header("🗂  Browse by Category")
    cats = recommender.get_all_categories_with_counts()
    for i, c in enumerate(cats, 1):
        print(f"  {i}. {c['category']} ({c['count']} books, {c['total_issues']} issues)")
    print("\n  0. Back")
    try:
        idx = int(input("  Choose category: ").strip())
        if idx <= 0 or idx > len(cats):
            return
        cat = cats[idx - 1]["category"]
        print(f"\n  Top books in [bold]{cat}[/bold]:")
        books = recommender.recommend_by_category(cat)
        for j, b in enumerate(books, 1):
            avail = "✅" if b["available"] > 0 else "❌"
            print(
                f"  {j}. [{b['book_id']}] {b['title']} — {b['author']} "
                f"({b['issue_count']} issues) {avail}"
            )
    except (ValueError, IndexError):
        pass
    pause()


# NOTIFICATIONS


def notifications_menu(notif_mgr: NotificationManager, user_id: str) -> None:
    """View and manage in-app notifications."""
    while True:
        count = notif_mgr.get_unread_count(user_id)
        choice = menu(
            f"🔔 NOTIFICATIONS ({count} unread)",
            ["View All Notifications", "View Unread Only", "Mark All as Read", "Back"],
        )
        if choice == "1":
            _show_notifications(notif_mgr, user_id, unread_only=False)
        elif choice == "2":
            _show_notifications(notif_mgr, user_id, unread_only=True)
        elif choice == "3":
            notif_mgr.mark_all_read(user_id)
            print_success("All notifications marked as read.")
            pause()
        elif choice == "4":
            break


def _show_notifications(notif_mgr: NotificationManager, user_id: str, unread_only: bool) -> None:
    """Display notifications for a user."""
    notifs = notif_mgr.get_notifications(user_id, unread_only=unread_only)
    if not notifs:
        print_info("No notifications.")
        pause()
        return
    for n in notifs:
        read_status = "[bold]NEW[/bold]" if not n["read"] else "  "
        ts = format_date(n["created_at"])
        type_icons = {"overdue": "⏰", "reservation_available": "📢", "fine": "💰"}
        icon = type_icons.get(n["type"], "📌")
        print(f"  {read_status} {icon} {n['message']}")
        print(f"              {ts}")
        print()
    if not unread_only and confirm("Mark all as read?"):
        notif_mgr.mark_all_read(user_id)
        print_success("Marked as read.")
    pause()


# BACKUP & RESTORE


def backup_restore_menu(auth: AuthManager):
    while True:
        choice = menu(
            "💾 BACKUP & RESTORE",
            ["Create Backup Now", "List Backups", "Restore Backup", "Back"],
        )
        if choice == "1":
            path = create_backup(triggered_by=auth.current_user.user_id)
            log("Manual backup created", auth.current_user.user_id, path)
            print_success(f"Backup saved to: {path}")
            pause()
        elif choice == "2":
            backups = list_backups()
            header("📂 AVAILABLE BACKUPS")
            if not backups:
                print("  No backups found.")
            for i, b in enumerate(backups, 1):
                ts = b.get("timestamp", b["name"])
                by = b.get("triggered_by", "?")
                print(f"  {i}. {ts}  (by: {by})")
            pause()
        elif choice == "3":
            backups = list_backups()
            if not backups:
                print_warning("No backups to restore.")
                pause()
                continue
            for i, b in enumerate(backups, 1):
                print(f"  {i}. {b.get('timestamp', b['name'])}")
            try:
                idx = int(input("  Restore backup #: ").strip()) - 1
                bk = backups[idx]
            except (ValueError, IndexError):
                print_error("Invalid choice.")
                pause()
                continue
            if confirm(f"Restore '{bk['name']}'? Current data will be archived."):
                ok = restore_backup(bk["path"])
                if ok:
                    print_success("Restore successful.")
                else:
                    print_error("Restore failed.")
                log("Backup restored", auth.current_user.user_id, bk["name"])
            pause()
        elif choice == "4":
            break


# LOGS


def logs_menu() -> None:
    header("📜 ACTIVITY LOGS (Last 50 entries)")
    lines = get_logs(50)
    if not lines:
        print("  No logs yet.")
    for line in lines:
        print(f"  {line}")
    pause()


# EMAIL NOTIFICATIONS


def email_overdue_alerts(lib: Library) -> None:
    """Send email notifications for all overdue books."""
    try:
        from app.services.email.email_notifier import send_overdue_batch

        _EMAIL_ENABLED = True
    except ImportError:
        _EMAIL_ENABLED = False

    header("📧 SEND OVERDUE EMAIL ALERTS")
    if not _EMAIL_ENABLED:
        print_warning("❌ email_notifier module not available.")
        print_info(
            "   The email_notifier.py module is required. Make sure it exists in the project directory."
        )
        pause()
        return

    # Check SMTP config (Config already imported at top of file)
    if not Config.SMTP_HOST or not Config.SMTP_USER or not Config.SMTP_PASSWORD:
        print_warning("❌ SMTP is not configured.")
        print_info(
            "   Set SMTP_HOST, SMTP_USER, and SMTP_PASSWORD in your .env file or environment."
        )
        if not confirm("Continue anyway (shows what would be sent)?"):
            pause()
            return

    overdue = lib.get_overdue_list()
    if not overdue:
        print_success("🎉 No overdue books — nothing to send!")
        pause()
        return

    print_info(f"Found {len(overdue)} overdue book(s).")
    if confirm(f"Send email alerts for {len(overdue)} overdue book(s)?"):
        print_info("Sending email notifications...")
        result = send_overdue_batch(overdue)
        print()
        print_success(f"✅ Sent: {result['sent']}")
        if result["failed"] > 0:
            print_error(f"❌ Failed: {result['failed']}")
        if result["skipped"] > 0:
            print_warning(f"⏭️ Skipped: {result['skipped']} (no email on file or user not found)")
        print_info(f"📊 Total processed: {result['total']}")
        log(
            f"Overdue email alerts sent: {result['sent']} sent, {result['failed']} failed, {result['skipped']} skipped",
            "Admin",
        )
    else:
        print_info("Cancelled.")
    pause()


# SEED DATA / GOODREADS KNOWLEDGE BASE


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
        console.print(table)
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
            print(
                f"  {i:2}. 📖 {r['title']} — {r['author']} "
                f"({r['category']}) "
                f"⭐ {r.get('average_rating', '?')} "
                f"({r.get('ratings_count', 0):,} ratings)"
            )
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
        print(f"  {i:2}. {c['category']:<18} : {c['count']} books")
    print("\n  0. Back")
    try:
        idx = int(input("  Choose category: ").strip())
        if idx <= 0 or idx > len(cats):
            return
        cat = cats[idx - 1]["category"]
        recs = recommender.recommend_from_seed("category", category=cat, top_n=15)
        if recs:
            print(f"\n  📚 Top books in [bold]{cat}[/bold] (from Goodreads):\n")
            for i, r in enumerate(recs, 1):
                print(
                    f"  {i:2}. {r['title']} — {r['author']} "
                    f"(⭐ {r.get('average_rating', '?')}, {r.get('ratings_count', 0):,} ratings)"
                )
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
        print(f"\n  Found {len(recs)} result(s):\n")
        for i, r in enumerate(recs, 1):
            print(f"  {i:2}. 📖 {r['title']}")
            print(
                f"      by {r['author']} | {r['category']} | "
                f"⭐ {r.get('average_rating', '?')} "
                f"({r.get('ratings_count', 0):,} ratings)"
            )
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
        print(f"\n  Books by [bold]{author}[/bold] in Goodreads dataset:")
        for i, r in enumerate(recs, 1):
            print(
                f"  {i:2}. {r['title']} ({r['category']}) "
                f"⭐ {r.get('average_rating', '?')} "
                f"({r.get('ratings_count', 0):,} ratings)"
            )
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
    console.print(table)
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

    console.print(
        f"  [cyan]Seed dataset: {stats['total']:,} books across {stats['categories_count']} categories[/cyan]"
    )

    print("\n  Options:")
    print("    1. Import by Category (pick a category)")
    print("    2. Import Trending (top 50 highest rated)")
    print("    3. Import by Author")
    print("    4. Search and Import Specific")
    choice = input("  Choice: ").strip()

    books_to_import = []

    if choice == "1":
        cats = _sd.get_seed_category_counts()
        for i, (c, cnt) in enumerate(
            sorted(cats.items(), key=lambda x: x[1], reverse=True)[:20], 1
        ):
            print(f"  {i:2}. {c:<18} : {cnt} books")
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

    print(f"\n  Found {len(books_to_import)} seed book(s):")
    for i, b in enumerate(books_to_import[:10], 1):
        print(
            f"  {i:2}. {b['title']} — {b['author']} ({b['category']}) "
            f"⭐ {b.get('average_rating', '?')}"
        )
    if len(books_to_import) > 10:
        print(f"      ... and {len(books_to_import) - 10} more")

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
        log(
            f"Imported {imported} books from Goodreads seed data",
            auth.current_user.user_id,
        )
    else:
        print_info("Import cancelled.")
    pause()


# USER SELF-SERVICE


def my_books(lib: Library, auth: AuthManager) -> None:
    header("📚 MY ISSUED BOOKS")
    user = auth.current_user
    books_store = lib.storage.load_books()
    txns = lib.storage.load_transactions()
    now = datetime.now()

    if not user.books_issued:
        print("  You have no books currently issued.")
    else:
        for bid in user.books_issued:
            book = books_store.get(bid)
            txn = None
            for t in reversed(txns):
                if (
                    t["user_id"] == user.user_id
                    and t["book_id"] == bid
                    and t["return_date"] is None
                ):
                    txn = t
                    break
            title = book.title if book else bid
            if txn:
                due = datetime.fromisoformat(txn["due_date"])
                overdue_days = max(0, (now - due).days)
                status = (
                    colored(f"OVERDUE by {overdue_days} day(s)", "red")
                    if now > due
                    else colored("On time", "green")
                )
                print(f"  📖 {title}")
                print(f"     Due: {due.strftime('%d %b %Y')} | {status}")
    pause()


def my_fine(auth: AuthManager) -> None:
    header("💰 MY FINE STATUS")
    user = auth.current_user
    if user.unpaid_fine > 0:
        print_warning(f"Outstanding fine: ₹{user.unpaid_fine:.2f}")
    else:
        print_success("No outstanding fines!")
    pause()


# MAIN


def main() -> None:
    storage = create_storage()
    lib = Library(storage)
    auth = AuthManager(storage)

    bootstrap(storage, auth)

    console.print(
        """
[cyan]
  ╔══════════════════════════════════════════╗
  ║   📚 Library Management System v2.0     ║
  ║   Built with Python | All Features      ║
  ║   + Recommendations Engine              ║
  ╚══════════════════════════════════════════╝
[/cyan]
    """
    )

    try:
        while True:
            if not auth.is_logged_in():
                ok = login_screen(auth)
                if not ok:
                    retry = input("  Retry? (y/n): ").strip().lower()
                    if retry != "y":
                        break
                    continue

            user = auth.current_user
            if user.role == "admin":
                admin_menu(lib, auth, storage)
            elif user.role == "librarian":
                librarian_menu(lib, auth, storage)
            else:
                user_menu(lib, auth)

            if not auth.is_logged_in():
                again = input("\n  Login again? (y/n): ").strip().lower()
                if again != "y":
                    break

    finally:
        # Auto-backup on exit
        print_info("Auto-backup on exit...")
        path = create_backup(triggered_by="auto-exit")
        log("Auto-backup on program exit", "System", path)
        print_success(f"Backup saved: {os.path.basename(path)}")
        console.print("[cyan]  Goodbye! 👋\n[/cyan]")


if __name__ == "__main__":
    main()
