"""Books routes — /books, /books/<id>, /api/books/<id>/issue|return."""

import logging
from urllib.parse import quote

from flask import jsonify, redirect, render_template, request, session, url_for

from app.routes.helpers import cat_color
from app.routes.page_state import (
    lib,
    login_required,
    notif_mgr,
    recommender,
    render_page,
    storage,
)

logger = logging.getLogger(__name__)


def register_book_routes(app) -> None:
    """Register books list, detail, and issue/return API routes."""

    # ════════════════════════════════════════════════════════════════
    # 1. PROFILE SELF REDIRECT (/profile)
    # ════════════════════════════════════════════════════════════════

    @app.route("/profile")
    @login_required
    def profile_self_redirect():
        uid = session["user_id"]
        return redirect(url_for("profile_page", user_id=uid))

    # ════════════════════════════════════════════════════════════════
    # 2. BOOKS PAGE (/books)
    # ════════════════════════════════════════════════════════════════

    @app.route("/books")
    @login_required
    def books_page() -> str:
        books_data = storage.load_books()
        all_books = [b for b in books_data.values() if not b.is_deleted]
        q = request.args.get("q", "").strip()
        cat_filter = request.args.get("cat", "")

        if q:
            ql = q.lower()
            all_books = [b for b in all_books if ql in b.title.lower() or ql in b.author.lower()]
        if cat_filter:
            all_books = [b for b in all_books if b.category == cat_filter]

        total = len(all_books)
        available = sum(1 for b in all_books if b.available_copies > 0)
        checked_out = total - available
        cats = len({b.category for b in all_books})
        categories = sorted({b.category for b in books_data.values() if not b.is_deleted})

        return render_template(
            "books.html",
            title="Books",
            session=session,
            notif_count=(
                notif_mgr.get_unread_count(session.get("user_id")) if session.get("user_id") else 0
            ),
            books=all_books[:24],
            categories=categories,
            q=q,
            cat_filter=cat_filter,
            total=total,
            available=available,
            checked_out=checked_out,
            cats=cats,
        )

    # ════════════════════════════════════════════════════════════════
    # 3. BOOK DETAIL PAGE (/books/<book_id>)
    # ════════════════════════════════════════════════════════════════

    @app.route("/books/<book_id>")
    @login_required
    def book_detail_page(book_id) -> str:
        books_data = storage.load_books()
        book = books_data.get(book_id)
        if not book or book.is_deleted:
            return render_page(
                "Not Found",
                '<div class="empty-state py-5"><div class="empty-icon">📚</div><h5>Book not found</h5><p class="text-muted">This book may have been removed.</p><a href="/books" class="btn btn-primary btn-sm"><i class="bi bi-arrow-left"></i> Browse Books</a></div>',
            )

        cc = cat_color(book.category)
        avail_text = "Available" if book.available_copies > 0 else "Checked Out"
        avail_cls = "success" if book.available_copies > 0 else "danger"

        uid = session.get("user_id")
        is_issued_to_me = False
        if uid:
            _me = storage.load_users().get(uid)
            is_issued_to_me = bool(_me and book_id in (_me.books_issued or []))

        # Reviews
        reviews = []
        try:
            all_reviews = storage.load_reviews() if hasattr(storage, "load_reviews") else []
            book_reviews = [r for r in all_reviews if r.get("book_id") == book_id][:5]
            users_data = storage.load_users()
            for r in book_reviews:
                ru = users_data.get(r.get("user_id", ""))
                reviews.append(
                    {
                        "user_name": ru.name if ru else "?",
                        "rating": int(r.get("rating", 0) or 0),
                        "content": r.get("content", "") or "",
                        "created_at": r.get("created_at", "") or "",
                    }
                )
        except (AttributeError, TypeError, KeyError) as exc:
            logger.warning("book detail %s: reviews unavailable: %s", book_id, exc)
            reviews = []

        # Similar books
        similar = []
        try:
            sim = recommender.recommend_similar_books(book_id, top_n=4) if recommender else []
            similar = [
                {
                    "book_id": r.get("book_id"),
                    "title": r.get("title", ""),
                    "category": r.get("category", ""),
                }
                for r in sim
                if r and r.get("book_id")
            ]
        except (AttributeError, TypeError, KeyError) as exc:
            logger.warning("book detail %s: similar books unavailable: %s", book_id, exc)
            similar = []

        return render_template(
            "book_detail.html",
            title=book.title,
            session=session,
            notif_count=(
                notif_mgr.get_unread_count(session.get("user_id")) if session.get("user_id") else 0
            ),
            author_url=quote(book.author or ""),
            book=book,
            cc=cc,
            avail_text=avail_text,
            avail_cls=avail_cls,
            reviews=reviews,
            similar=similar,
            cat_color=cat_color,
            is_issued_to_me=is_issued_to_me,
            description=getattr(book, "description", "") or "No description available.",
        )

    # ════════════════════════════════════════════════════════════════
    # 4. BORROW / RETURN API
    # ════════════════════════════════════════════════════════════════

    @app.route("/api/books/<book_id>/issue", methods=["POST"])
    @login_required
    def api_book_issue(book_id):
        target = request.json.get("user_id") if request.is_json else None
        if not target:
            target = session.get("user_id")
        ok, msg, due = lib.issue_book(target, book_id, actor=session.get("user_id"))
        return jsonify({"success": ok, "message": msg, "due_date": due}), 200 if ok else 409

    @app.route("/api/books/<book_id>/return", methods=["POST"])
    @login_required
    def api_book_return(book_id):
        target = request.json.get("user_id") if request.is_json else None
        if not target:
            target = session.get("user_id")
        ok, msg, fine = lib.return_book(target, book_id, actor=session.get("user_id"))
        return jsonify({"success": ok, "message": msg, "fine": fine}), 200 if ok else 409
