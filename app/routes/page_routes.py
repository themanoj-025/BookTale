"""
page_routes.py - Page Routes Coordinator for BookTale v5.0

Delegates to focused route modules:
  - explore_routes:       /explore, /recommendations, notification API
  - reading_routes:       /shelves, /reading-calendar, /analytics
  - admin_page_routes:    /admin/users, /admin/audit, /admin/overdue, /reports
  - club_routes:          /clubs, /clubs/<id>, club API
  - dashboard_page_routes: /dashboard, /books, /gamification, /profile, book API
"""

import logging

from app.routes import page_state

logger = logging.getLogger(__name__)


def init_page_routes(
    app,
    storage,
    lib,
    auth,
    notif_mgr,
    social,
    review_mgr,
    recommender,
    book_lists,
    communities,
    gamification,
    series_mgr,
    challenge,
    reading_progress,
    wishlist,
    diary_mgr,
) -> None:
    """Initialize shared state and register all page route modules."""

    # Populate shared state used by all route modules
    page_state.init(
        storage,
        lib,
        auth,
        notif_mgr,
        social,
        review_mgr,
        recommender,
        book_lists,
        communities,
        gamification,
        series_mgr,
        challenge,
        reading_progress,
        wishlist,
        diary_mgr,
    )

    # Register route modules
    from app.routes.explore_routes import init_explore_routes
    from app.routes.reading_routes import init_reading_routes
    from app.routes.admin_page_routes import init_admin_page_routes
    from app.routes.club_routes import init_club_routes
    from app.routes.dashboard_page_routes import init_dashboard_page_routes

    init_explore_routes(app)
    init_reading_routes(app)
    init_admin_page_routes(app)
    init_club_routes(app)
    init_dashboard_page_routes(app)

    return app
