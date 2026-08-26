"""
api_routes.py - JSON API endpoints (trending, random, suggested, seed stats,
AI chat, reading streak, analytics, books search, settings save).

Extracted from web_app.py to reduce file size and improve maintainability.
"""

import contextlib
import os
import random as _random
from datetime import datetime
from functools import wraps

from flask import g, jsonify, redirect, request, session, url_for


def init_api_routes(app, storage, lib, auth, notif_mgr, recommender, social, diary_mgr) -> None:
    """Register API routes on the Flask app."""

    def _rate_limit(limit_value: str, **kwargs: Any) -> Any:
        """Rate-limit decorator; no-op fallback if flask-limiter is missing."""
        _lim = app.extensions.get("booktale_limiter")
        if _lim is None:
            return lambda f: f
        return _lim.limit(limit_value, **kwargs)

    def _user_key() -> dict[str, str]:
        uid = session.get("user_id")
        if uid:
            return f"user:{uid}"
        return f"ip:{request.remote_addr}"

    def login_required(f: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(f)
        def d(*a: Any, **k: Any) -> Any:
            if "user_id" not in session:
                return redirect(url_for("login_page"))
            return f(*a, **k)
        return d

    def api_key_required(f: Callable[..., Any]) -> Callable[..., Any]:
        """Protect API endpoints with Bearer token auth."""
        import secrets as _secrets

        @wraps(f)
        def d(*a: Any, **k: Any) -> Any:
            api_key = os.environ.get("BOOKTALE_API_KEY", "")
            if not api_key:
                return f(*a, **k)
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return jsonify({"error": "Missing Authorization header"}), 401
            token = auth_header[7:]
            if not _secrets.compare_digest(token, api_key):
                return jsonify({"error": "Invalid API key"}), 403
            return f(*a, **k)
        return d

    # ── Settings Save API ───────────────────────────────────────────────────

    @app.route("/api/settings/save", methods=["POST"])
    @login_required
    @_rate_limit(
        "10 per minute",
        key_func=_user_key,
        deduct_when=lambda response: getattr(g, "_pw_change_failed", False),
    )
    def api_save_settings() -> dict[str, str]:
        """Save user settings."""
        uid = session["user_id"]
        data = request.get_json() or {}
        users = storage.load_users()
        user = users.get(uid)
        if not user:
            return jsonify({"success": False, "error": "User not found"})

        for key in ["name", "email", "phone", "bio", "website", "location"]:
            if key in data:
                setattr(user, key, data[key])
                if key == "name":
                    session["user_name"] = data[key]

        for key in [
            "email_notifications",
            "push_notifications",
            "notify_on_comment",
            "notify_on_like",
            "notify_on_follow",
            "notify_on_issue_return",
            "notify_on_overdue",
            "notify_on_due_reminder",
            "privacy_show_activity",
            "privacy_show_wishlist",
            "privacy_show_bookmarks",
            "privacy_show_email",
        ]:
            if key in data:
                setattr(user, key, bool(data[key]))

        for key in [
            "theme",
            "font_size",
            "privacy_profile_visibility",
            "reading_default_rating",
            "reading_goal_type",
        ]:
            if key in data:
                setattr(user, key, str(data[key]))

        if "reading_default_goal" in data:
            with contextlib.suppress(ValueError, TypeError):
                user.reading_default_goal = int(data["reading_default_goal"])

        if data.get("new_password"):
            from app.services.auth.auth import hash_password as _hp
            from app.services.auth.auth import verify_password as _vp

            cur = data.get("current_password", "")
            if not cur or not _vp(cur, user.password_hash):
                g._pw_change_failed = True
                return jsonify({"success": False, "error": "Current password is incorrect"})
            if len(data["new_password"]) < 12:
                return jsonify({"success": False, "error": "Password must be at least 12 characters"})
            user.password_hash = _hp(data["new_password"])
            from app.core.logger import log
            log("Password changed via settings", uid)

        storage.save_users(users)
        return jsonify({"success": True, "message": "Settings saved"})

    # ── Trending Books API ──────────────────────────────────────────────────

    @app.route("/api/books/trending")
    @login_required
    def api_books_trending() -> dict[str, Any]:
        """Get trending books based on issue count or seed data."""
        limit = min(int(request.args.get("limit", 10)), 30)
        if recommender:
            try:
                recs = recommender.recommend_trending(top_n=limit)
                return jsonify(recs)
            except (OSError, ValueError, KeyError):
                pass
        books = storage.load_books()
        all_books = [b for b in books.values() if not b.is_deleted]
        sorted_books = sorted(
            all_books, key=lambda b: b.issue_count or b.average_rating or 0, reverse=True
        )[:limit]
        return jsonify(
            [
                {
                    "book_id": b.book_id,
                    "title": b.title,
                    "author": b.author,
                    "category": b.category,
                    "issue_count": b.issue_count,
                    "available": b.available_copies,
                }
                for b in sorted_books
            ]
        )

    # ── Random Book API ─────────────────────────────────────────────────────

    @app.route("/api/books/random")
    @login_required
    def api_book_random() -> dict[str, Any]:
        """Get a random book for the dashboard spotlight."""
        books = storage.load_books()
        all_books = [b for b in books.values() if not b.is_deleted]
        if not all_books:
            return jsonify({"error": "No books available"}), 404
        b = _random.choice(all_books)  # nosec B311
        return jsonify(
            {
                "book_id": b.book_id,
                "title": b.title,
                "author": b.author,
                "category": b.category,
                "available_copies": b.available_copies,
                "issue_count": b.issue_count,
                "description": getattr(b, "description", ""),
            }
        )

    # ── Suggested Users API ─────────────────────────────────────────────────

    @app.route("/api/users/suggested")
    @login_required
    def api_users_suggested() -> dict[str, Any]:
        """Get suggested users to follow."""
        uid = session["user_id"]
        users = storage.load_users()
        following_set = set()
        if social:
            with contextlib.suppress(Exception):
                following_set = set(social.get_following(uid))
        suggested = []
        for u in users.values():
            if u.user_id != uid and u.user_id not in following_set:
                suggested.append({"user_id": u.user_id, "name": u.name, "role": u.role})
                if len(suggested) >= 6:
                    break
        return jsonify(suggested)

    # ── Seed Stats API ──────────────────────────────────────────────────────

    @app.route("/api/seed/stats")
    @api_key_required
    def api_seed_stats() -> dict[str, Any]:
        """Get stats including Goodreads seed dataset counts."""
        s = _library_stats(storage)
        try:
            from app.services.recommendations.seed_data import get_seed_stats

            seed = get_seed_stats()
            total_books = seed.get("total_books", s.get("total_books", 0))
            total_users = max(s.get("total_users", 0), 10000)
            return jsonify(
                {
                    "total_books": total_books,
                    "total_users": total_users,
                    "total_ratings": seed.get("total_ratings", 0),
                }
            )
        except (OSError, ValueError, KeyError):
            return jsonify(
                {
                    "total_books": s.get("total_books", 0),
                    "total_users": s.get("total_users", 0),
                    "total_ratings": 0,
                }
            )

    # ── AI Chat API ─────────────────────────────────────────────────────────

    @app.route("/api/ai/chat", methods=["POST"])
    @login_required
    @_rate_limit("30 per minute")
    def api_ai_chat() -> dict[str, Any]:
        """AI Reading Companion - TF-IDF based book recommendations and Q&A."""
        data = request.get_json() or {}
        message = data.get("message", "").strip()
        if not message:
            return jsonify(
                {
                    "error": "No message provided",
                    "response": "Please ask me a question about books!",
                }
            )

        msg_lower = message.lower()

        if "recommend" in msg_lower or "suggest" in msg_lower or "read next" in msg_lower:
            uid = session["user_id"]
            try:
                recs = recommender.recommend_for_user(uid, top_n=3) if recommender else []
                if recs:
                    titles = [r.get("title", "Unknown") for r in recs]
                    response = (
                        "Based on your reading history, I recommend: "
                        + ", ".join(titles)
                        + ". Happy reading!"
                    )
                else:
                    trending = recommender.recommend_trending(top_n=3) if recommender else []
                    if trending:
                        titles = [r.get("title", "Unknown") for r in trending]
                        response = (
                            "Here are some trending books you might enjoy: " + ", ".join(titles) + "."
                        )
                    else:
                        response = "I'd recommend checking out our Explore page for trending books!"
            except (OSError, ValueError, KeyError, TypeError):
                response = "I'm having trouble finding recommendations right now. Try browsing the Explore page!"
        elif "similar" in msg_lower or "like" in msg_lower:
            response = (
                "Try searching for a book and checking the 'Similar Books' section on its detail page!"
            )
        elif "summary" in msg_lower or "summarize" in msg_lower:
            response = "To get a summary, go to a book's detail page and check the description section!"
        elif "genre" in msg_lower or "category" in msg_lower:
            response = "We have many genres! Browse by category on the Books or Recommendations page."
        elif "hello" in msg_lower or "hi " in msg_lower or msg_lower == "hi":
            response = "Hello! I'm your AI Reading Companion. Ask me for book recommendations, or about specific books!"
        elif "thank" in msg_lower:
            response = "You're welcome! Happy reading! 📚"
        else:
            response = "That's a great question! I can help with book recommendations, finding similar books, or exploring genres. What would you like to know?"

        return jsonify({"response": response, "message": message})

    # ── Reading Streak API ──────────────────────────────────────────────────

    @app.route("/api/reading-streak")
    @login_required
    def api_reading_streak() -> dict[str, Any]:
        """Calculate reading streak based on diary entries."""
        uid = session["user_id"]
        try:
            entries, _ = diary_mgr.get_user_diary(uid, page=1, per_page=500) if diary_mgr else ([], 0)
            dates = sorted(
                {e.get("date_read", "")[:10] for e in entries if e.get("date_read")},
                reverse=True,
            )
            streak = 0
            from datetime import date as dt_date
            from datetime import timedelta

            today = dt_date.today()
            check_date = today
            for d in dates:
                try:
                    d_date = dt_date.fromisoformat(d)
                    if d_date == check_date or d_date == check_date - timedelta(days=1):
                        streak += 1
                        check_date = d_date
                    elif d_date < check_date - timedelta(days=1):
                        break
                except (ValueError, TypeError):
                    pass
            return jsonify({"streak": streak, "total_days": len(dates)})
        except (OSError, ValueError, KeyError, TypeError):
            return jsonify({"streak": 0, "total_days": 0})

    # ── Analytics APIs ──────────────────────────────────────────────────────

    @app.route("/api/analytics/monthly")
    @api_key_required
    def api_analytics_monthly() -> dict[str, Any]:
        """Get monthly analytics data for charts."""
        books = storage.load_books()
        all_books = [b for b in books.values() if not b.is_deleted]
        months = [
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        ]
        monthly = [0] * 12
        for b in all_books:
            try:
                dt = datetime.fromisoformat(b.added_on)
                monthly[dt.month - 1] += 1
            except (ValueError, TypeError):
                pass
        return jsonify({"labels": months, "values": monthly})

    @app.route("/api/analytics/categories")
    @api_key_required
    def api_analytics_categories() -> dict[str, Any]:
        """Get category distribution for charts."""
        books = storage.load_books()
        from collections import Counter

        counts = Counter(b.category for b in books.values() if not b.is_deleted)
        return jsonify({"labels": list(counts.keys()), "values": list(counts.values())})

    @app.route("/api/analytics/activity")
    @api_key_required
    def api_analytics_activity() -> dict:
        """Get recent activity for 'Who to Follow' sidebar."""
        txns = storage.load_transactions()
        from collections import Counter

        user_counts = Counter(t.get("user_id", "") for t in txns if t.get("type") == "issue")
        return jsonify([{"user": uid, "count": cnt} for uid, cnt in user_counts.most_common(10)])

    # ── Book Search API ─────────────────────────────────────────────────────

    @app.route("/api/books")
    @login_required
    def api_books_search() -> dict[str, Any]:
        """Search books API - for autocomplete and search overlays."""
        q = request.args.get("q", "").strip()
        sort = request.args.get("sort", "title")
        books = storage.load_books()
        all_books = [b for b in books.values() if not b.is_deleted]
        if q:
            ql = q.lower()
            all_books = [
                b
                for b in all_books
                if ql in b.title.lower() or ql in b.author.lower() or ql in (b.isbn or "").lower()
            ]
        if sort == "popular":
            all_books.sort(key=lambda b: b.issue_count, reverse=True)
        elif sort == "new":
            all_books.sort(key=lambda b: b.added_on, reverse=True)
        else:
            all_books.sort(key=lambda b: b.title.lower())
        return jsonify(
            [
                {
                    "book_id": b.book_id,
                    "title": b.title,
                    "author": b.author,
                    "category": b.category,
                    "available_copies": b.available_copies,
                    "pages": b.pages,
                    "isbn": b.isbn,
                }
                for b in all_books[:24]
            ]
        )


def _library_stats(storage: Any) -> dict[str, Any]:
    """Compute library statistics for analytics."""
    books, users, txns = (
        storage.load_books(),
        storage.load_users(),
        storage.load_transactions(),
    )
    all_books = [b for b in books.values() if not b.is_deleted]
    now = datetime.now()
    tms = datetime(now.year, now.month, 1)
    total_books = len(all_books)
    total_copies = sum(b.total_copies for b in all_books)
    avail_copies = sum(b.available_copies for b in all_books)
    total_users = len(users)
    new_books_month = sum(1 for b in all_books if datetime.fromisoformat(b.added_on) >= tms)
    active_users = sum(1 for u in users.values() if u.membership_status == "Active")
    return {
        "total_books": total_books,
        "total_copies": total_copies,
        "avail_copies": avail_copies,
        "total_users": total_users,
        "active_users": active_users,
        "new_books_month": new_books_month,
    }
