"""
helpers.py - Shared utilities for BookTale route modules.

Extracted from page_routes.py to eliminate duplication across
page_routes.py, social_routes.py, and site_pages.py.
"""

import html
import logging
import zlib
from datetime import datetime
from functools import wraps

from flask import redirect, render_template, session, url_for

logger = logging.getLogger(__name__)

# Module-level storage references — set by init_helpers()
_storage = None
_notif_mgr = None


def init_helpers(storage, notif_mgr) -> None:
    """Initialize shared dependencies. Called once at app startup."""
    global _storage, _notif_mgr
    _storage = storage
    _notif_mgr = notif_mgr


def h(text) -> str:
    """HTML-escape text for safe rendering in templates."""
    return html.escape(str(text))


def cat_color(c) -> str:
    """Return a hex color for a book category."""
    colors = {
        "Fiction": "#4f46e5",
        "Non-Fiction": "#059669",
        "Science": "#0891b2",
        "Technology": "#7c3aed",
        "History": "#d97706",
        "Philosophy": "#be185d",
        "Art": "#db2777",
        "Biography": "#ca8a04",
        "Children": "#16a34a",
        "Comics": "#e11d48",
        "Poetry": "#9333ea",
        "Drama": "#ea580c",
        "Education": "#2563eb",
        "Reference": "#64748b",
        "Religion": "#78716c",
        "Self-Help": "#0d9488",
        "Cooking": "#f97316",
        "Travel": "#0ea5e9",
        "Music": "#8b5cf6",
        "Sports": "#22c55e",
        "Other": "#6b7280",
    }
    return colors.get(c, colors["Other"])


def avatar_html(name, size=32) -> str:
    """Generate an avatar div with initials and a deterministic color."""
    parts = name.strip().split()
    if not parts:
        initials = "?"
    elif len(parts) >= 2:
        initials = (parts[0][0] + parts[-1][0]).upper()
    else:
        initials = parts[0][:2].upper()
    clrs = [
        "#4f46e5", "#059669", "#d97706", "#dc2626",
        "#0891b2", "#7c3aed", "#db2777", "#ca8a04",
    ]
    c = clrs[zlib.crc32(str(name).encode("utf-8")) % len(clrs)]
    return (
        '<div class="avatar" style="width:%dpx;height:%dpx;background:%s20;'
        'color:%s;font-size:%dpx;font-weight:700;border-radius:50%%;'
        'display:inline-flex;align-items:center;justify-content:center;'
        'flex-shrink:0;" title="%s">%s</div>'
        % (size, size, c, c, size // 2, h(name), h(initials))
    )


def time_ago(iso_str) -> str:
    """Convert an ISO datetime string to a human-readable relative time."""
    try:
        dt = datetime.fromisoformat(iso_str)
        now = datetime.now()
        diff = now - dt
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return "just now"
        minutes = seconds // 60
        if minutes < 60:
            return "%dm ago" % minutes
        hours = minutes // 60
        if hours < 24:
            return "%dh ago" % hours
        days = hours // 24
        if days < 7:
            return "%dd ago" % days
        weeks = days // 7
        if weeks < 4:
            return "%dw ago" % weeks
        months = days // 30
        if months < 12:
            return "%dmo ago" % months
        years = days // 365
        return "%dy ago" % years
    except (ValueError, TypeError):
        return iso_str[:10] if iso_str else ""


def render_page(title, content, **kw) -> str:
    """Render a page with the base template, injecting notification count."""
    user = get_current_user()
    return render_template(
        "base.html",
        title=title,
        content=content,
        session=session,
        notif_count=_notif_mgr.get_unread_count(user.user_id) if user else 0,
        **kw,
    )


def get_current_user() -> dict | None:
    """Return the current user object from the session, or None."""
    if "user_id" not in session:
        return None
    return _storage.load_users().get(session["user_id"])


def login_required(f) -> dict:
    """Decorator: redirect to login if user is not authenticated."""
    @wraps(f)
    def d(*a, **k) -> Any:
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        return f(*a, **k)
    return d


def admin_required(f) -> None:
    """Decorator: require admin role, show forbidden page if not."""
    @wraps(f)
    def d(*a, **k) -> dict:
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        if session.get("role") != "admin":
            return render_page(
                "Forbidden",
                '<div class="text-center py-5"><div style="font-size:4rem;'
                'margin-bottom:1rem;">🔒</div><h3>Admin Access Required</h3>'
                '<p class="text-muted">This page requires admin privileges.</p></div>',
            )
        return f(*a, **k)
    return d


def library_stats(storage) -> dict:
    """Calculate library-wide statistics for dashboard, reports, and admin pages."""
    if not storage:
        return {}
    books = storage.load_books()
    users = storage.load_users()
    txns = storage.load_transactions()
    all_books = [b for b in books.values() if not b.is_deleted]
    now = datetime.now()
    tms = datetime(now.year, now.month, 1)
    total_books = len(all_books)
    total_copies = sum(b.total_copies for b in all_books)
    avail_copies = sum(b.available_copies for b in all_books)
    avail_rate = (avail_copies / total_copies * 100) if total_copies else 0
    new_books_month = sum(1 for b in all_books if datetime.fromisoformat(b.added_on) >= tms)
    total_users = len(users)
    active_users = sum(1 for u in users.values() if u.membership_status == "Active")
    blocked_users = sum(1 for u in users.values() if u.membership_status == "Blocked")
    new_users_month = sum(
        1
        for u in users.values()
        if hasattr(u, "added_on") and u.added_on and datetime.fromisoformat(u.added_on) >= tms
    )
    issues = [t for t in txns if t["type"] == "issue"]
    active_issues = [t for t in issues if t.get("return_date") is None]
    total_txns = len(txns)
    month_txns = sum(1 for t in txns if datetime.fromisoformat(t.get("issue_date", "")) >= tms)
    unique_borrowers = len({t["user_id"] for t in issues})
    fines = storage.load_fines()
    total_fines = sum(f.get("amount", 0) for f in fines)
    paid_fines = sum(f.get("amount", 0) for f in fines if f.get("paid"))
    pending_fines = total_fines - paid_fines
    avg_bpu = round(len(issues) / total_users, 1) if total_users else 0
    return {
        "total_books": total_books,
        "total_copies": total_copies,
        "avail_copies": avail_copies,
        "active_issues": len(active_issues),
        "total_issues": len(issues),
        "avail_rate": round(avail_rate, 1),
        "new_books_month": new_books_month,
        "total_users": total_users,
        "active_users": active_users,
        "blocked_users": blocked_users,
        "new_users_month": new_users_month,
        "total_txns": total_txns,
        "month_txns": month_txns,
        "unique_borrowers": unique_borrowers,
        "avg_books_per_user": avg_bpu,
        "total_fines": round(total_fines, 2),
        "paid_fines": round(paid_fines, 2),
        "pending_fines": round(pending_fines, 2),
    }
