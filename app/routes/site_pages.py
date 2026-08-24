"""
site_pages.py - Landing page, features showcase, and welcome page for the full website
Registers routes on the Flask app for the public-facing marketing pages.

Phase 3: pages now render real Jinja2 templates (templates/landing.html,
templates/features.html, templates/welcome.html) with autoescaping ON — the old
render_template_string + str.replace machinery is gone.
"""

from datetime import datetime

from flask import redirect, render_template, session, url_for

from app.config.settings import Config
from app.models.book import CATEGORIES as BOOK_CATEGORIES
from app.routes.helpers import cat_color


def init_site_pages(app, storage, lib, recommender, social, review_mgr, notif_mgr):
    """Register site pages on the Flask app."""

    def get_current_user():
        if "user_id" not in session:
            return None
        return storage.load_users().get(session["user_id"])

    def _library_stats():
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
        total_users = len(users)
        active_users = sum(1 for u in users.values() if u.membership_status == "Active")
        blocked_users = sum(1 for u in users.values() if u.membership_status == "Blocked")
        new_users_month = sum(
            1
            for u in users.values()
            if hasattr(u, "registered_on")
            and u.registered_on
            and datetime.fromisoformat(u.registered_on) >= tms
        )
        new_books_month = sum(1 for b in all_books if datetime.fromisoformat(b.added_on) >= tms)
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

    # ═══════════════════════════════════════════════════════════
    # LANDING PAGE
    # ═══════════════════════════════════════════════════════════

    @app.route("/landing")
    @app.route("/")
    def landing_page():
        """Spectacular landing page — works for both guests and logged-in users."""
        uid = session.get("user_id")
        user = get_current_user() if uid else None

        # Logged-in users go to feed
        if user:
            return redirect(url_for("feed_page"))

        # ── Guest landing page ──
        s = _library_stats()
        books = storage.load_books()
        all_books = [b for b in books.values() if not b.is_deleted]
        featured_books = sorted(all_books, key=lambda b: b.issue_count, reverse=True)[:6]
        posts = storage.load_posts() if hasattr(storage, "load_posts") else []

        cat_counts = {}
        for b in all_books:
            cat_counts[b.category] = cat_counts.get(b.category, 0) + 1
        top_cats = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)[:4]

        # Phase 3: all interpolation happens in the Jinja template (autoescape ON).
        return render_template(
            "landing.html",
            title="BookTale — Your Reading Companion",
            s=s,
            featured_books=featured_books,
            top_cats=top_cats,
            posts_count=len(posts),
            categories_count=len(BOOK_CATEGORIES),
            cat_color=cat_color,
        )

    # ═══════════════════════════════════════════════════════════
    # FEATURES PAGE
    # ═══════════════════════════════════════════════════════════

    @app.route("/features")
    def features_page():
        """Showcase all platform features."""
        books = storage.load_books()
        all_books = [b for b in books.values() if not b.is_deleted]
        posts = storage.load_posts() if hasattr(storage, "load_posts") else []

        return render_template(
            "features.html",
            title="Features",
            books_count=len(all_books),
            users_count=len(storage.load_users()),
            categories_count=len(BOOK_CATEGORIES),
            posts_count=len(posts),
            fine_per_day=Config.FINE_PER_DAY,
        )

    # ═══════════════════════════════════════════════════════════
    # WELCOME / BOOKSOCIAL ONBOARDING
    # ═══════════════════════════════════════════════════════════

    @app.route("/welcome")
    def welcome_page():
        """BookSocial welcome/onboarding page."""
        uid = session.get("user_id")
        user = get_current_user() if uid else None

        posts = storage.load_posts() if hasattr(storage, "load_posts") else []
        reviews_data = storage.load_reviews() if hasattr(storage, "load_reviews") else []
        following_count = 0
        follower_count = 0
        if user and social:
            try:
                following_count = social.get_following_count(uid)
                follower_count = social.get_follower_count(uid)
            except (AttributeError, TypeError):
                pass

        greeting = "Welcome to BookSocial!" + (", " + user.name if user else "")
        profile_link = "/profile/" + uid if uid else "/login"
        feed_link = "/feed" if uid else "/login"

        return render_template(
            "welcome.html",
            title="Welcome to BookSocial",
            user=user,
            greeting=greeting,
            profile_link=profile_link,
            feed_link=feed_link,
            posts_count=len(posts),
            reviews_count=len(reviews_data),
            following_count=following_count,
            follower_count=follower_count,
        )

    return app
