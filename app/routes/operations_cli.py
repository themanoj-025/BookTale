"""
operations_cli.py - Issue/Return, Overdue, Fine Management, Reservations CLI.
"""

from app.core.utils import (
    console,
    create_table,
    header,
    menu,
    pause,
    print_error,
    print_success,
    print_warning,
)
from app.services.auth.auth import AuthManager
from app.services.books.library import Library
from app.storage.storage import Storage
import logging

logger = logging.getLogger(__name__)



def issue_return_menu(lib: Library, auth: AuthManager) -> None:
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


def return_book_flow(lib: Library, auth: AuthManager) -> None:
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


def overdue_menu(lib: Library) -> None:
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
        logger.info("%s", table)
    pause()


def fine_management_menu(lib: Library, auth: AuthManager) -> None:
    header("💳 FINE MANAGEMENT")
    uid = input("  User ID   : ").strip()
    user = lib.get_user(uid)
    if not user:
        print_error("User not found.")
        pause()
        return
    logger.info(f"\n  {user.name} — Unpaid Fine: ₹{user.unpaid_fine:.2f}")
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


def reservations_menu(lib: Library, storage: Storage) -> None:
    header("📌 RESERVATION QUEUE")
    res = storage.load_reservations()
    books = storage.load_books()
    users = storage.load_users()
    if not res:
        logger.info("  No active reservations.")
    for bid, queue in res.items():
        book = books.get(bid)
        title = book.title if book else bid
        avail = book.available_copies if book else 0
        logger.info(f"\n  📗 {title} (Available: {avail})")
        for i, uid in enumerate(queue, 1):
            u = users.get(uid)
            logger.info(f"     {i}. {u.name if u else uid} [{uid}]")
    pause()
