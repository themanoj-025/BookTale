"""
gamification_core.py — Registration function, feed page, and search page.

Extracted from gamification_routes.py for focused maintenance.
"""


from app.routes.social_shared import (
    login_required,
    render_page,
)


def register_gamification_routes(app, _rate_limit) -> None:
    """Register page routes on *app*.

    Parameters
    ----------
    app : Flask
        The application instance.
    _rate_limit : callable
        A rate-limit decorator factory.
    """

    # ═══ FEED PAGE ═══

    @app.route("/feed")
    @login_required
    def feed_page() -> str:
        from app.routes.gamification_pkg.feed_page import render_feed_page

        return render_feed_page()

    # ═══ SEARCH PAGE ═══

    @app.route("/search")
    @login_required
    def search_page() -> str:
        return render_page(
            "Search",
            '<div class="empty-state empty-state-variant py-5"><div class="empty-icon"><i class="bi bi-search" style="font-size:3rem;"></i></div><div class="empty-title">Search Books &amp; People</div><div class="empty-desc">Use the search overlay (Ctrl+K) to find books, users, and more.</div><button class="empty-cta" onclick="openSearchOverlay()"><i class="bi bi-search me-2"></i>Open Search</button></div>',
        )

    # ═══ PROFILE EDIT PAGE ═══

    @app.route("/profile/edit")
    @login_required
    def profile_edit_page() -> str:
        from app.routes.gamification_pkg.profile_edit_page import render_profile_edit_page

        return render_profile_edit_page()

    # ═══ AUTHOR PAGE ═══

    @app.route("/author/<author_name>")
    @login_required
    def author_page(author_name) -> str:
        from app.routes.gamification_pkg.author_page import render_author_page

        return render_author_page(author_name)
