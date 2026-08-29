"""
dashboard_page_routes.py — Thin orchestrator for dashboard-related routes.

Delegates to focused modules:
- dashboard.py    — /dashboard page
- books.py        — /books, /books/<id>, /api/books/<id>/issue|return
- gamification.py — /gamification page
- profile.py      — /profile/<uid>, /profile/<uid>/export/pdf
"""

import logging

from app.routes.dashboard import register_dashboard_routes
from app.routes.books import register_book_routes
from app.routes.gamification import register_gamification_routes
from app.routes.profile import register_profile_routes

logger = logging.getLogger(__name__)


def init_dashboard_page_routes(app) -> None:
    """Register all dashboard-related routes on the Flask app."""
    register_book_routes(app)
    register_dashboard_routes(app)
    register_gamification_routes(app)
    register_profile_routes(app)
    return app
