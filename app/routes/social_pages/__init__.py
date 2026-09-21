"""social_pages — Focused page route modules for social pages.

Registers the /feed, /search, /profile/edit and /author/<name> pages.
Previously mis-housed under ``gamification_pkg/`` (the routes are social,
not gamification); the /gamification page itself lives in
``app.routes.gamification``.
"""

from app.routes.social_pages.core import register_social_page_routes

__all__ = ["register_social_page_routes"]
