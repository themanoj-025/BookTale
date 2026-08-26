"""
user_management_cli.py - User management CLI functions (register, view, block, renew, list).
"""

from app.core.utils import (
    colored,
    header,
    menu,
    pause,
    print_error,
    print_success,
    print_warning,
    validate_email,
)
from app.models.user import ROLES
from app.services.auth.auth import AuthManager, hash_password
from app.services.books.library import Library
from app.storage.storage import Storage


def user_management_menu(lib: Library, auth: AuthManager, storage: Storage) -> None:
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


def register_user_flow(lib: Library, auth: AuthManager) -> None:
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


def view_user_flow(storage: Storage) -> None:
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


def renew_membership_flow(lib: Library, auth: AuthManager) -> None:
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


def list_users(storage: Storage) -> None:
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
