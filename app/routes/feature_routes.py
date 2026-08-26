"""
feature_routes.py - Feature Routes Coordinator

Thin coordinator that initialises shared state and delegates route
registration to the focused sub-modules:

- feature_shared.py   – shared state, helpers, dashboard widgets, HTML templates
- series_routes.py    – book series pages + API
- challenge_routes.py  – reading challenge pages + API
- progress_routes.py  – reading progress + bookmarks API
- wishlist_routes.py  – wishlist/suggestions pages + API
- diary_routes.py     – reading diary pages + API
"""

from flask import Flask

from app.routes.feature_shared import init_shared_state
from app.routes.series_routes import register_series_routes
from app.routes.challenge_routes import register_challenge_routes
from app.routes.progress_routes import register_progress_routes
from app.routes.wishlist_routes import register_wishlist_routes
from app.routes.diary_routes import register_diary_routes


def init_feature_routes(
    app: Flask,
    storage,
    lib,
    auth,
    notif_mgr,
    series,
    challenge,
    progress,
    wishlist,
    diary,
) -> dict:
    """Populate shared state and register all feature routes on *app*."""
    init_shared_state(
        app, storage, lib, auth, notif_mgr, series, challenge, progress, wishlist, diary
    )

    # Build shared helpers that need Flask context
    import html
    from functools import wraps

    from flask import jsonify, redirect, render_template, session, url_for

    def h(text):
        return html.escape(str(text))

    def _js_str(value):
        return str(value).replace("\\", "\\\\").replace("'", "\\'").replace('"', "&quot;")

    def get_current_user():
        if "user_id" not in session:
            return None
        return storage.load_users().get(session["user_id"])

    def render_page(title, content, **kw):
        user = get_current_user()
        return render_template(
            "base.html",
            title=title,
            content=content,
            session=session,
            notif_count=notif_mgr.get_unread_count(user.user_id) if user else 0,
            **kw,
        )

    def login_required(f):
        @wraps(f)
        def d(*a, **k):
            if "user_id" not in session:
                return redirect(url_for("login_page"))
            return f(*a, **k)
        return d

    def admin_required(f):
        @wraps(f)
        def d(*a, **k):
            if "user_id" not in session:
                return redirect(url_for("login_page"))
            if session.get("role") != "admin":
                return jsonify({"error": "Admin access required"}), 403
            return f(*a, **k)
        return d

    def _rate_limit(limit_value, **kwargs):
        _lim = app.extensions.get("booktale_limiter")
        if _lim is None:
            return lambda f: f
        return _lim.limit(limit_value, **kwargs)

    # Register each route group
    register_series_routes(app, login_required, admin_required, render_page, _rate_limit)
    register_challenge_routes(app, login_required, render_page, _rate_limit)
    register_progress_routes(app, login_required, render_page, _rate_limit)
    register_wishlist_routes(app, login_required, admin_required, render_page, _rate_limit)
    register_diary_routes(app, login_required, render_page, _rate_limit)

    return {}
