"""
social_routes.py - Social Platform Routes Coordinator

Thin coordinator that initialises shared state and delegates route
registration to the focused sub-modules:

- social_shared.py   – shared state, helpers, image verification, renderers
- social_api.py      – feed, post CRUD, upload, follow, hashtags, search, lists API
- review_routes.py   – reviews, shelves, bookshelves, profile API
- gamification_routes.py – feed/search/profile/author pages + gamification renderers
"""

from flask import Flask

from app.routes.social_shared import init_shared_state
from app.routes.social_api import register_social_api_routes
from app.routes.review_routes import register_review_routes
from app.routes.gamification_routes import register_gamification_routes


def init_social_routes(
    app: Flask,
    _storage,
    _lib,
    _auth,
    _social,
    _review_mgr,
    _recommender,
    _notif_mgr,
    _book_lists=None,
    _communities=None,
    _gamification=None,
) -> dict:
    """Populate shared state and register all social routes on *app*."""
    init_shared_state(
        _storage,
        _lib,
        _auth,
        _social,
        _review_mgr,
        _recommender,
        _notif_mgr,
        _book_lists=_book_lists,
        _communities=_communities,
        _gamification=_gamification,
    )

    # Build a rate-limit decorator (no-op fallback when flask-limiter is absent).
    def _rate_limit(limit_value, **kwargs) -> Callable:
        _lim = app.extensions.get("booktale_limiter")
        if _lim is None:
            return lambda f: f
        return _lim.limit(limit_value, **kwargs)

    # Register each route group.
    register_social_api_routes(app, _rate_limit)
    register_review_routes(app, _rate_limit)
    register_gamification_routes(app, _rate_limit)

    return {}
