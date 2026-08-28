"""
gamification_pkg — Focused page route modules for gamification pages.

Split from the monolithic ``gamification_routes.py`` for maintainability.
The original ``gamification_routes.py`` re-exports the registration function.
"""

from app.routes.gamification_pkg.gamification_core import register_gamification_routes

__all__ = ["register_gamification_routes"]
