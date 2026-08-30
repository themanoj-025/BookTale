"""
page_state.py - Shared module-level state for page route modules.

Holds service references and helper functions used across
explore_routes, reading_routes, admin_page_routes, club_routes, and
dashboard_page_routes. Initialized once by init_page_routes in page_routes.py.
"""

import html as _html
import logging
from functools import wraps

from flask import redirect, render_template, session, url_for
from typing import Any
from collections.abc import Callable
from flask import Flask

logger = logging.getLogger(__name__)

# ── Service references (set by init_page_routes) ───────────────────────

storage = None
lib = None
auth = None
notif_mgr = None
social = None
review_mgr = None
recommender = None
book_lists = None
communities = None
gamification = None
series_mgr = None
challenge = None
reading_progress = None
wishlist = None
diary_mgr = None


def init(
    _storage,
    _lib,
    _auth,
    _notif_mgr,
    _social,
    _review_mgr,
    _recommender,
    _book_lists,
    _communities,
    _gamification,
    _series_mgr,
    _challenge,
    _reading_progress,
    _wishlist,
    _diary_mgr,
) -> None:
    """Populate module-level service references."""
    global storage, lib, auth, notif_mgr, social, review_mgr, recommender
    global book_lists, communities, gamification, series_mgr, challenge
    global reading_progress, wishlist, diary_mgr

    storage = _storage
    lib = _lib
    auth = _auth
    notif_mgr = _notif_mgr
    social = _social
    review_mgr = _review_mgr
    recommender = _recommender
    book_lists = _book_lists
    communities = _communities
    gamification = _gamification
    series_mgr = _series_mgr
    challenge = _challenge
    reading_progress = _reading_progress
    wishlist = _wishlist
    diary_mgr = _diary_mgr


# ── Shared helpers ─────────────────────────────────────────────────────


def h(text: object) -> str:
    """HTML-escape text."""
    return _html.escape(str(text))


def get_current_user() -> Any:
    """Return current user from session, or None."""
    if "user_id" not in session:
        return None
    return storage.load_users().get(session["user_id"])


def library_stats() -> dict[str, Any]:
    """Calculate library-wide statistics (delegates to helpers.library_stats)."""
    from app.routes.helpers import library_stats as _ls

    return _ls(storage)


def render_page(title: str, content: str, **kw: Any) -> str:
    """Render a page using base.html with notification count."""
    user = get_current_user()
    return render_template(
        "base.html",
        title=title,
        content=content,
        notif_count=notif_mgr.get_unread_count(user.user_id) if user else 0,
        **kw,
    )


def login_required(f: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: redirect to login if not authenticated."""

    @wraps(f)
    def d(*a: Any, **k: Any) -> Any:
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        return f(*a, **k)

    return d


def admin_required(f: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: 403 if not admin."""

    @wraps(f)
    def d(*a: Any, **k: Any) -> Any:
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        if session.get("role") != "admin":
            return {"error": "Admin access required"}, 403
        return f(*a, **k)

    return d


def make_rate_limit(app: Flask) -> Callable[..., Any]:
    """Return a rate-limit decorator using the app's booktale_limiter."""

    def _rate_limit(limit_value: str, **kwargs: Any) -> Any:
        _lim = app.extensions.get("booktale_limiter")
        if _lim is None:
            return lambda f: f
        return _lim.limit(limit_value, **kwargs)

    return _rate_limit
