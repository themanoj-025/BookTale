"""
social_pages_routes.py — Backward-compatible re-exporter.

All social page routes (/feed, /search, /profile/edit, /author/<name>)
live in ``social_pages/`` as focused modules. Formerly mis-named
``gamification_routes.py`` — the real gamification page lives in
``app.routes.gamification``.
"""

from app.routes.social_pages import register_social_page_routes

__all__ = [
    "register_social_page_routes",
]
