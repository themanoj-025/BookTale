"""
main.py - Library Management System CLI (Enhanced)

Thin entry point: menu routing, login, bootstrap.
All domain logic lives in focused modules:
  - book_management_cli.py   (book CRUD, search, ISBN lookup)
  - user_management_cli.py   (user registration, block, renew)
  - operations_cli.py        (issue/return, overdue, fines, reservations)
  - reports_cli.py           (reports, analytics, CSV export)
  - recommendations_cli.py   (recommendations + seed data)
  - notifications_cli.py     (in-app + email notifications)
  - backup_cli.py            (backup, restore, logs)
"""

import os
import sys
from datetime import datetime


from app.config.settings import Config
from app.core.logger import log
from app.core.utils import (
    console,
    header,
    menu,
    pause,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from app.db.storage_adapter import create_storage
from app.services.auth.auth import AuthManager, hash_password
from app.services.books.backup import create_backup
from app.services.books.library import Library
from app.services.notifications.notifications import NotificationManager
from app.services.recommendations.recommender import Recommender
from app.storage.storage import Storage

# ── CLI module imports ──
from app.routes.book_management_cli import (
    book_management_menu,
    search_books_menu,
)
from app.routes.user_management_cli import (
    user_management_menu,
)
from app.routes.operations_cli import (
    issue_return_menu,
    issue_book_flow,
    return_book_flow,
    overdue_menu,
    fine_management_menu,
    reservations_menu,
)
from app.routes.reports_cli import (
    reports_menu,
    export_reports_menu,
)
from app.routes.recommendations_cli import (
    recommendations_menu,
    user_recommendations_menu,
    seed_recommendations_menu,
    seed_import_menu,
)
from app.routes.notifications_cli import (
    show_notification_badge,
    notifications_menu,
    email_overdue_alerts,
)
from app.routes.backup_cli import (
    backup_restore_menu,
    logs_menu,
)
import logging

logger = logging.getLogger(__name__)



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
        from app.core.exceptions import AuthenticationError

        user = auth.login(uid, pwd)
        if not user:
            return False
        print_success(f"Welcome, {user.name}! [{user.role.upper()}]")
        log("Login", user.user_id)
        return True
    except AuthenticationError:
        print_error("Invalid credentials.")
        return False


# ── Admin / Librarian / User menus ──


def admin_menu(lib: Library, auth: AuthManager, storage: Storage) -> None:
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


def librarian_menu(lib: Library, auth: AuthManager, storage: Storage) -> None:
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


def user_menu(lib: Library, auth: AuthManager) -> None:
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


# ── User self-service ──


def my_books(lib: Library, auth: AuthManager) -> None:
    from app.core.utils import colored

    header("📚 MY ISSUED BOOKS")
    user = auth.current_user
    books_store = lib.storage.load_books()
    txns = lib.storage.load_transactions()
    now = datetime.now()

    if not user.books_issued:
        logger.info("  You have no books currently issued.")
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
                logger.info(f"  📖 {title}")
                logger.info(f"     Due: {due.strftime('%d %b %Y')} | {status}")
    pause()


def my_fine(auth: AuthManager) -> None:
    header("💰 MY FINE STATUS")
    user = auth.current_user
    if user.unpaid_fine > 0:
        print_warning(f"Outstanding fine: ₹{user.unpaid_fine:.2f}")
    else:
        print_success("No outstanding fines!")
    pause()


# ── Main ──


def main() -> None:
    storage = create_storage()
    lib = Library(storage)
    auth = AuthManager(storage)

    bootstrap(storage, auth)

    logger.info("""
[cyan]
  ╔══════════════════════════════════════════╗
  ║   📚 Library Management System v2.0     ║
  ║   Built with Python | All Features      ║
  ║   + Recommendations Engine              ║
  ╚══════════════════════════════════════════╝
[/cyan]
    """)

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
        logger.info("[cyan]  Goodbye! 👋\n[/cyan]")


if __name__ == "__main__":
    main()
