"""
review_routes.py - Reviews, Shelves, Bookshelves, and Profile API.
Extracted from social_routes.py for focused maintenance.
"""

from flask import g, jsonify, request, session

from app.routes.social_shared import (
from flask import Response
    login_required,
    review_mgr,
    storage,
)


def register_review_routes(app, _rate_limit) -> None:
    """Register review, shelf, and profile API endpoints on *app*.

    Parameters
    ----------
    app : Flask
        The application instance.
    _rate_limit : callable
        A rate-limit decorator factory.
    """

    # ═══ REVIEWS ═══

    @app.route("/api/reviews/<book_id>", methods=["POST"])
    @login_required
    @_rate_limit("30 per minute")
    def api_add_review(book_id) -> Response:
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg, review = review_mgr.add_review(
            uid,
            book_id,
            int(data.get("rating", 5)),
            data.get("content", "").strip(),
            data.get("spoiler", False),
        )
        return jsonify({"success": ok, "message": msg, "review": review})

    @app.route("/api/reviews/<review_id>/helpful", methods=["POST"])
    @login_required
    @_rate_limit("60 per minute")
    def api_helpful_review(review_id) -> Response:
        uid = session["user_id"]
        ok, _msg, is_helpful = review_mgr.mark_helpful(review_id, uid)
        return jsonify({"success": ok, "is_helpful": is_helpful})

    @app.route("/api/reviews/<review_id>/comments", methods=["GET", "POST"])
    @login_required
    @_rate_limit("30 per minute", methods=["POST"])
    def api_review_comments(review_id) -> Response:
        uid = session["user_id"]
        if request.method == "GET":
            return jsonify({"comments": review_mgr.get_review_comments(review_id)})
        else:
            data = request.get_json() or {}
            content = data.get("content", "").strip()
            if not content:
                return jsonify({"success": False, "error": "Comment cannot be empty"})
            ok, msg, comment = review_mgr.add_review_comment(review_id, uid, content)
            return jsonify({"success": ok, "message": msg, "comment": comment})

    @app.route("/api/reviews/<book_id>/list")
    @login_required
    def api_reviews_list(book_id) -> Response:
        uid = session["user_id"]
        page = max(1, int(request.args.get("page", 1)))
        sort_by = request.args.get("sort", "recent")
        reviews, stats = review_mgr.get_book_reviews(book_id, uid, page=page, sort_by=sort_by)
        return jsonify({"reviews": reviews, "stats": stats})

    @app.route("/api/books/<book_id>/reviews")
    @login_required
    def api_book_reviews(book_id) -> Response:
        uid = session["user_id"]
        page = max(1, int(request.args.get("page", 1)))
        reviews, stats = review_mgr.get_book_reviews(book_id, uid, page=page)
        return jsonify({"reviews": reviews, "stats": stats})

    @app.route("/api/books/<book_id>/review", methods=["POST"])
    @login_required
    @_rate_limit("30 per minute")
    def api_submit_review(book_id) -> Response:
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg, review = review_mgr.add_review(
            uid,
            book_id,
            int(data.get("rating", 5)),
            data.get("content", ""),
            data.get("spoiler", False),
        )
        return jsonify({"success": ok, "message": msg, "review": review})

    # ═══ BOOKSHELVES ═══

    @app.route("/api/bookshelves/<book_id>", methods=["POST"])
    @login_required
    def api_add_to_shelf(book_id) -> Response:
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg = review_mgr.add_to_shelf(uid, book_id, data.get("shelf", "want_to_read"))
        return jsonify({"success": ok, "message": msg})

    @app.route("/api/bookshelves/status/<book_id>")
    @login_required
    def api_shelf_status(book_id) -> Response:
        uid = session["user_id"]
        shelf = review_mgr.is_on_shelf(uid, book_id)
        return jsonify({"shelf": shelf})

    @app.route("/api/bookshelves/<book_id>/remove", methods=["POST"])
    @login_required
    def api_remove_from_shelf(book_id) -> Response:
        uid = session["user_id"]
        ok, msg = review_mgr.remove_from_shelf(uid, book_id)
        return jsonify({"success": ok, "message": msg})

    # ═══ CUSTOM SHELVES ═══

    @app.route("/api/shelves/create", methods=["POST"])
    @login_required
    @_rate_limit("30 per minute")
    def api_create_shelf() -> Response:
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg = review_mgr.create_custom_shelf(
            uid,
            data.get("name", ""),
            data.get("description", ""),
            data.get("icon", "bookmark"),
        )
        return jsonify({"success": ok, "message": msg})

    @app.route("/api/shelves")
    @login_required
    def api_get_shelves() -> Response:
        uid = session["user_id"]
        return jsonify({"shelves": review_mgr.get_user_custom_shelves(uid)})

    @app.route("/api/shelves/<shelf_name>", methods=["DELETE"])
    @login_required
    def api_delete_shelf(shelf_name) -> Response:
        from urllib.parse import unquote

        shelf_name = unquote(shelf_name)
        ok, msg = review_mgr.delete_custom_shelf(session["user_id"], shelf_name)
        return jsonify({"success": ok, "message": msg})

    @app.route("/api/shelves/<shelf_name>/rename", methods=["POST"])
    @login_required
    def api_rename_shelf(shelf_name) -> Response:
        from urllib.parse import unquote

        shelf_name = unquote(shelf_name)
        data = request.get_json() or {}
        ok, msg = review_mgr.rename_custom_shelf(
            session["user_id"], shelf_name, data.get("new_name", "")
        )
        return jsonify({"success": ok, "message": msg})

    # ═══ PROFILE API ═══

    @app.route("/api/reviews/stats")
    @login_required
    def api_reviews_stats_overall() -> Response:
        """Get overall rating distribution stats for the profile chart."""
        all_reviews = storage.load_reviews()
        dist = {}
        for r in all_reviews:
            star = r.get("rating", 0)
            dist[star] = dist.get(star, 0) + 1
        labels = ["1 Star", "2 Stars", "3 Stars", "4 Stars", "5 Stars"]
        values = [dist.get(i, 0) for i in range(1, 6)]
        return jsonify({"labels": labels, "values": values, "total": len(all_reviews)})

    @app.route("/api/profile/favorites/remove", methods=["POST"])
    @login_required
    def api_profile_favorites_remove() -> Response:
        """Remove a book from the current user's favorite_books list."""
        uid = session["user_id"]
        data = request.get_json() or {}
        book_id = data.get("book_id", "")
        if not book_id:
            return jsonify({"success": False, "error": "No book_id provided"})
        users = storage.load_users()
        user = users.get(uid)
        if not user:
            return jsonify({"success": False, "error": "User not found"})
        if book_id in user.favorite_books:
            user.favorite_books.remove(book_id)
            storage.save_users(users)
            return jsonify({"success": True, "message": "Removed from favorites"})
        return jsonify({"success": False, "error": "Book not in favorites"})

    @app.route("/api/profile/favorites/reorder", methods=["POST"])
    @login_required
    def api_profile_favorites_reorder() -> Response:
        """Reorder the current user's favorite_books list."""
        uid = session["user_id"]
        data = request.get_json() or {}
        book_ids = data.get("book_ids", [])
        if not book_ids:
            return jsonify({"success": False, "error": "No book_ids provided"})
        users = storage.load_users()
        user = users.get(uid)
        if not user:
            return jsonify({"success": False, "error": "User not found"})
        all_books = storage.load_books()
        valid_ids = [bid for bid in book_ids if bid in all_books]
        user.favorite_books = valid_ids[:4]  # Max 4 favorites
        storage.save_users(users)
        return jsonify({"success": True, "message": "Favorites reordered"})

    @app.route("/api/profile/favorites/add", methods=["POST"])
    @login_required
    def api_profile_favorites_add() -> Response:
        """Add a book to the current user's favorite_books list (max 4)."""
        uid = session["user_id"]
        data = request.get_json() or {}
        book_id = data.get("book_id", "")
        if not book_id:
            return jsonify({"success": False, "error": "No book_id provided"})
        books = storage.load_books()
        if book_id not in books:
            return jsonify({"success": False, "error": "Book not found"})
        users = storage.load_users()
        user = users.get(uid)
        if not user:
            return jsonify({"success": False, "error": "User not found"})
        if len(user.favorite_books) >= 4:
            return jsonify(
                {
                    "success": False,
                    "error": "Maximum 4 favorites allowed. Remove one first.",
                }
            )
        if book_id in user.favorite_books:
            return jsonify({"success": False, "error": "Book already in favorites"})
        user.favorite_books.append(book_id)
        storage.save_users(users)
        return jsonify(
            {
                "success": True,
                "message": "Added to favorites",
                "favorites": user.favorite_books,
            }
        )

    @app.route("/api/profile/update", methods=["POST"])
    @login_required
    @_rate_limit(
        "10 per minute",
        deduct_when=lambda response: getattr(g, "_profile_email_changed", False),
    )
    def api_profile_update() -> Response:
        """Update the current user's profile fields."""
        uid = session["user_id"]
        data = request.get_json() or {}
        users = storage.load_users()
        user = users.get(uid)
        if not user:
            return jsonify({"success": False, "error": "User not found"})
        if "email" in data:
            g._profile_email_changed = True
        allowed = {
            "name",
            "email",
            "phone",
            "bio",
            "website",
            "location",
            "profile_picture",
        }
        for key in allowed:
            if key in data:
                setattr(user, key, data[key])
        storage.save_users(users)
        if "name" in data:
            session["user_name"] = data["name"]
        return jsonify({"success": True, "message": "Profile updated"})
