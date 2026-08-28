"""
dashboard_page_routes.py - Dashboard, books, gamification, and profile routes.

Routes: /dashboard, /books, /books/<book_id>, /gamification, /profile,
        /profile/<uid>, /profile/<uid>/export/pdf,
        /api/books/<id>/issue, /api/books/<id>/return
"""

import contextlib
from datetime import datetime
from urllib.parse import quote

from flask import jsonify, redirect, render_template, request, session, url_for

from app.routes.helpers import avatar_html, cat_color, get_current_user
from app.routes.page_state import (
    challenge,
    diary_mgr,
    gamification,
    h,
    login_required,
    notif_mgr,
    recommender,
    render_page,
    review_mgr,
    storage,
    lib,
    make_rate_limit,
    library_stats,
)


def init_dashboard_page_routes(app) -> None:
    """Register dashboard, books, gamification, and profile routes."""

    _rate_limit = make_rate_limit(app)

    # ════════════════════════════════════════════════════════════════
    # 1. PROFILE SELF REDIRECT (/profile)
    # ════════════════════════════════════════════════════════════════

    @app.route("/profile")
    @login_required
    def profile_self_redirect() -> Response:
        uid = session["user_id"]
        return redirect(url_for("profile_page", user_id=uid))

    # ════════════════════════════════════════════════════════════════
    # 2. DASHBOARD PAGE (/dashboard)
    # ════════════════════════════════════════════════════════════════

    @app.route("/dashboard")
    @login_required
    def dashboard_page() -> str:
        uid = session["user_id"]
        user = get_current_user()
        s = library_stats()

        # Fetch user gamification data
        gd = gamification.get_user_gamification(uid) if gamification else {}
        points = gd.get("points", 0)
        level = gd.get("level", "New Reader")
        next_level = gd.get("next_level", "")
        next_lvl_pts = gd.get("next_level_points", 0) or 1
        streak = gd.get("streak_days", 0)
        longest_streak = gd.get("longest_streak", 0)
        unlocked_ach = gd.get("unlocked_achievements", 0)
        total_ach = gd.get("total_achievements", 15)

        # Leaderboard position
        leaderboard = gamification.get_leaderboard(top_n=50) if gamification else []
        user_rank = 0
        for entry in leaderboard:
            if entry.get("user_id") == uid:
                user_rank = entry.get("rank", 0)
                break

        # Reading stats from diary
        diary_stats = diary_mgr.get_stats(uid) if diary_mgr else {}
        books_read = diary_stats.get("total_books", 0)
        pages_read = diary_stats.get("total_pages_read", 0)

        # Challenge progress
        challenge_data = challenge.get_goal(uid, datetime.now().year) if challenge else {}
        challenge_progress = challenge_data.get("progress", 0)
        challenge_goal = challenge_data.get("goal", 0)
        challenge_pct = challenge_data.get("percentage", 0)

        # Next level progress percentage
        level_pct = 0
        if next_lvl_pts > 0:
            cur_lvl_min = 0
            for lvl in [
                {"name": "New Reader", "min_points": 0},
                {"name": "Bronze Reader", "min_points": 50},
                {"name": "Silver Reader", "min_points": 200},
                {"name": "Gold Reader", "min_points": 500},
                {"name": "Platinum Reader", "min_points": 1000},
                {"name": "Diamond Reader", "min_points": 2500},
                {"name": "Legendary Reader", "min_points": 5000},
            ]:
                if lvl["name"] == level:
                    cur_lvl_min = lvl["min_points"]
                    break
            level_pct = min(100, int((points - cur_lvl_min) / max(1, next_lvl_pts) * 100))

        level_icons = {
            "New Reader": "seedling",
            "Bronze Reader": "award",
            "Silver Reader": "star",
            "Gold Reader": "trophy",
            "Platinum Reader": "gem",
            "Diamond Reader": "diamond",
            "Legendary Reader": "lightning",
        }
        lvl_icon = level_icons.get(level, "star")

        av = avatar_html(user.name if user else "?", 56)

        # User Profile Card
        PROFILE_CARD = (
            '<div class="glass-card p-4 mb-3 animate-in" style="position:relative;overflow:hidden;">'
            '<div style="position:absolute;top:-40px;right:-40px;width:160px;height:160px;border-radius:50%;background:linear-gradient(135deg,var(--color-primary),var(--color-accent));opacity:.08;"></div>'
            '<div class="row g-3 align-items-center">'
            '<div class="col-auto">' + av + "</div>"
            '<div class="col">'
            '<h4 class="fw-bold mb-0">' + h(user.name if user else "Admin") + "</h4>"
            '<small class="text-muted">@' + h(uid) + "</small>"
            '<div class="d-flex gap-2 mt-1 flex-wrap">'
            '<span class="badge" style="background:linear-gradient(135deg,var(--color-primary),var(--color-accent));color:white;font-size:.75rem;padding:.35rem .8rem;">'
            '<i class="bi bi-' + lvl_icon + ' me-1"></i> ' + h(level) + "</span>"
            '<span class="badge bg-warning text-dark" style="font-size:.75rem;padding:.35rem .8rem;">'
            '<i class="bi bi-fire me-1"></i> ' + str(streak) + " day streak</span>"
            "</div></div>"
            '<div class="col-auto text-end">'
            '<div style="font-size:2rem;font-weight:800;color:var(--color-primary);font-variant-numeric:tabular-nums;">'
            + str(points)
            + "</div>"
            '<small class="text-muted">points</small>'
            "</div></div></div>"
        )

        # Level Progress Bar
        LEVEL_BAR = ""
        if next_level:
            LEVEL_BAR = (
                '<div class="glass-card p-3 mb-3 animate-d1">'
                '<div class="d-flex justify-content-between align-items-center mb-2">'
                '<span class="section-title mb-0"><i class="bi bi-bar-chart-fill me-1"></i> Level Progress</span>'
                '<small class="text-muted">'
                + str(points)
                + " pts → "
                + h(next_level)
                + " ("
                + str(next_lvl_pts)
                + " pts needed)</small>"
                "</div>"
                '<div class="progress-thin" style="height:10px;background:var(--surface-2);">'
                '<div class="bar" style="width:'
                + str(level_pct)
                + '%;background:linear-gradient(90deg,var(--color-primary),var(--color-accent));height:10px;border-radius:5px;"></div>'
                "</div>"
                '<div class="d-flex justify-content-between mt-1"><small class="text-muted">'
                + str(level_pct)
                + "% complete</small></div>"
                "</div>"
            )

        # User Stats Row
        USER_STATS = (
            '<div class="stats-grid mb-3 animate-d1">'
            '<div class="stat-card">'
            '<span class="stat-number" style="color:var(--color-primary);">'
            + str(points)
            + "</span>"
            '<span class="stat-label">Points</span>'
            '<span class="stat-sub">' + h(level) + "</span></div>"
            '<div class="stat-card">'
            '<span class="stat-number" style="color:var(--success);">'
            + str(books_read)
            + "</span>"
            '<span class="stat-label">Books Read</span>'
            '<span class="stat-sub">' + str(pages_read) + " pages</span></div>"
            '<div class="stat-card">'
            '<span class="stat-number" style="color:var(--color-warning);"><i class="bi bi-fire"></i> '
            + str(streak)
            + "</span>"
            '<span class="stat-label">Day Streak</span>'
            '<span class="stat-sub">Best: ' + str(longest_streak) + " days</span></div>"
            '<div class="stat-card">'
            '<span class="stat-number" style="color:var(--color-danger);">#'
            + str(user_rank if user_rank > 0 else "-")
            + "</span>"
            '<span class="stat-label">Leaderboard</span>'
            '<span class="stat-sub">of ' + str(max(len(leaderboard), 0)) + " readers</span></div>"
            "</div>"
        )

        # Achievements Strip
        ACH_HTML = ""
        achievements = gd.get("achievements", [])
        unlocked_ids = set()
        for ach in achievements:
            if isinstance(ach, dict) and ach.get("unlocked"):
                unlocked_ids.add(ach.get("id", ""))
        for ach in achievements[:8]:
            if isinstance(ach, dict):
                aid = ach.get("id", "")
                unlocked = aid in unlocked_ids
                aname = ach.get("name", "")
                aicon = ach.get("icon", "star")
                opacity = "1" if unlocked else ".25"
                bg_grad = (
                    "linear-gradient(135deg,var(--color-primary),var(--color-accent))"
                    if unlocked
                    else "var(--surface-2)"
                )
                icon_color = "white" if unlocked else "var(--text-muted)"
                ACH_HTML += (
                    '<div style="text-align:center;padding:.3rem .5rem;opacity:'
                    + opacity
                    + ';" title="'
                    + h(aname)
                    + '">'
                    '<div style="width:36px;height:36px;border-radius:8px;background:'
                    + bg_grad
                    + ';display:flex;align-items:center;justify-content:center;margin:0 auto .2rem;">'
                    '<i class="bi bi-'
                    + aicon
                    + '" style="color:'
                    + icon_color
                    + ';font-size:.9rem;"></i></div>'
                    '<div style="font-size:.5rem;color:var(--text-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:50px;">'
                    + h(aname[:12])
                    + "</div></div>"
                )
        if not ACH_HTML:
            ACH_HTML = '<div class="text-center text-muted small py-3">Keep reading to unlock achievements!</div>'

        # Challenge mini-widget
        CHALLENGE_WIDGET = ""
        if challenge_goal > 0:
            CHALLENGE_WIDGET = (
                '<div class="glass-card p-3 animate-d1">'
                '<div class="section-title"><i class="bi bi-trophy-fill text-warning"></i> Reading Challenge '
                + str(datetime.now().year)
                + "</div>"
                '<div class="d-flex align-items-center gap-3">'
                '<div class="progress-thin flex-grow-1" style="height:10px;background:var(--surface-2);">'
                '<div class="bar" style="width:'
                + str(challenge_pct)
                + '%;background:linear-gradient(90deg,var(--color-warning),var(--color-danger));height:10px;border-radius:5px;"></div></div>'
                '<span class="fw-bold" style="font-size:1.2rem;">'
                + str(challenge_pct)
                + "%</span></div>"
                '<div class="d-flex justify-content-between mt-1">'
                '<small class="text-muted">'
                + str(challenge_progress)
                + " / "
                + str(challenge_goal)
                + " books</small>"
                '<a href="/reading-challenge" class="btn btn-primary btn-sm"><i class="bi bi-arrow-right"></i></a></div></div>'
            )

        # Stats grid (library-wide)
        STATS_GRID = (
            '<div class="stats-grid mb-3 animate-d2">'
            '<div class="stat-card"><span class="stat-number">%d</span><span class="stat-label">Total Books</span><span class="stat-sub trend-up">+%d this month</span></div>'
            '<div class="stat-card"><span class="stat-number">%d</span><span class="stat-label">Total Users</span><span class="stat-sub trend-up">+%d this month</span></div>'
            '<div class="stat-card"><span class="stat-number" style="color:var(--color-success);">%d</span><span class="stat-label">Available Copies</span><span class="stat-sub trend-up">%s%% avail</span></div>'
            '<div class="stat-card"><span class="stat-number" style="color:var(--color-warning);">%d</span><span class="stat-label">Active Issues</span><span class="stat-sub">%d unique borrowers</span></div>'
            '<div class="stat-card"><span class="stat-number">%d</span><span class="stat-label">Transactions</span><span class="stat-sub trend-up">+%d this month</span></div>'
            '<div class="stat-card"><span class="stat-number" style="color:var(--color-danger);">%d</span><span class="stat-label">Pending Fines</span><span class="stat-sub">&#8377;%.2f total</span></div>'
            "</div>"
        ) % (
            s["total_books"],
            s["new_books_month"],
            s["total_users"],
            s["new_users_month"],
            s["avail_copies"],
            s["avail_rate"],
            s["active_issues"],
            s["unique_borrowers"],
            s["total_txns"],
            s["month_txns"],
            s["blocked_users"],
            s["pending_fines"],
        )

        # Quick actions grid
        QUICK_ACTIONS = (
            '<h5 class="fw-bold mb-2"><i class="bi bi-lightning-fill me-1 text-warning"></i> Quick Actions</h5>'
            '<div class="row g-2 mb-3">'
            '<div class="col-4 col-md-2"><a href="/books" class="quick-action"><div class="qa-icon"><i class="bi bi-book-fill"></i></div><span class="qa-label">Browse Books</span></a></div>'
            '<div class="col-4 col-md-2"><a href="/admin/users" class="quick-action"><div class="qa-icon"><i class="bi bi-people-fill"></i></div><span class="qa-label">Users</span></a></div>'
            '<div class="col-4 col-md-2"><a href="/reports" class="quick-action"><div class="qa-icon"><i class="bi bi-bar-chart-fill"></i></div><span class="qa-label">Reports</span></a></div>'
            '<div class="col-4 col-md-2"><a href="/series/create" class="quick-action"><div class="qa-icon"><i class="bi bi-plus-circle-fill"></i></div><span class="qa-label">New Series</span></a></div>'
            '<div class="col-4 col-md-2"><a href="/settings" class="quick-action"><div class="qa-icon"><i class="bi bi-gear-fill"></i></div><span class="qa-label">Settings</span></a></div>'
            '<div class="col-4 col-md-2"><a href="/feed" class="quick-action"><div class="qa-icon"><i class="bi bi-rss-fill"></i></div><span class="qa-label">Social Feed</span></a></div>'
            "</div>"
        )

        # Monthly trends chart
        MONTHLY_CHART = (
            '<div class="glass-card p-3 mb-3 animate-d2">'
            '<div class="section-title"><i class="bi bi-bar-chart-fill"></i> Monthly Trends</div>'
            '<div class="chart-container" style="height:220px;">'
            '<canvas id="monthly-trends-chart" aria-label="Monthly issues trend for 2026"></canvas>'
            "</div></div>"
        )

        # Achievements section
        ACH_SECTION = (
            '<div class="glass-card p-3 animate-d2">'
            '<div class="section-title"><i class="bi bi-award-fill"></i> Achievements <small class="text-muted fw-normal">'
            + str(unlocked_ach)
            + "/"
            + str(total_ach)
            + "</small></div>"
            '<div class="d-flex flex-wrap justify-content-center gap-1">' + ACH_HTML + "</div>"
            '<a href="/gamification" class="btn btn-sm btn-outline w-100 mt-2">View All Achievements</a>'
            "</div>"
        )

        # Greeting
        hr = datetime.now().hour
        greeting = "morning" if hr < 12 else "afternoon" if hr < 18 else "evening"

        # Assemble CONTENT
        CONTENT = '<div class="animate-in">'
        CONTENT += PROFILE_CARD
        CONTENT += USER_STATS
        if LEVEL_BAR:
            CONTENT += LEVEL_BAR
        if CHALLENGE_WIDGET:
            CONTENT += CHALLENGE_WIDGET
        CONTENT += (
            '<div class="glass-card p-0 mb-3" style="overflow:hidden;">'
            '<div class="p-3" style="background:linear-gradient(135deg,var(--color-primary),var(--color-accent));color:white;">'
            '<h4 class="fw-bold mb-0"><i class="bi bi-speedometer2 me-2"></i> Library Overview</h4>'
            '<p class="mb-0" style="opacity:.8;font-size:.85rem;">Good '
            + greeting
            + ", "
            + h(user.name if user else "Admin")
            + "</p>"
            "</div></div>"
        )
        CONTENT += STATS_GRID
        CONTENT += QUICK_ACTIONS
        CONTENT += (
            '<div class="row g-3">'
            '<div class="col-lg-8">' + MONTHLY_CHART + "</div>"
            '<div class="col-lg-4">' + ACH_SECTION + "</div>"
            "</div>"
        )

        return render_page("Dashboard", CONTENT)

    # ════════════════════════════════════════════════════════════════
    # 3. BOOKS PAGE (/books)
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
    # 4. BOOK DETAIL PAGE (/books/<book_id>)
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
    # 5. BORROW / RETURN API
    # ════════════════════════════════════════════════════════════════

    @app.route("/api/books/<book_id>/issue", methods=["POST"])
    @login_required
    @_rate_limit("10 per minute", methods=["POST"])
    def api_book_issue(book_id) -> Response:
        data = request.get_json(silent=True) or {}
        target = str(data.get("user_id") or session.get("user_id") or "").strip()
        role = session.get("role", "")
        if target and target != session.get("user_id") and role not in ("admin", "librarian"):
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Only staff may issue on behalf of another user",
                    }
                ),
                403,
            )
        if not target:
            target = session.get("user_id")
        ok, msg = lib.issue_book(target, book_id, actor=session.get("user_id"))
        return jsonify({"success": ok, "message": msg}), 200 if ok else 409

    @app.route("/api/books/<book_id>/return", methods=["POST"])
    @login_required
    @_rate_limit("10 per minute", methods=["POST"])
    def api_book_return(book_id) -> Response:
        data = request.get_json(silent=True) or {}
        target = str(data.get("user_id") or session.get("user_id") or "").strip()
        role = session.get("role", "")
        if target and target != session.get("user_id") and role not in ("admin", "librarian"):
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Only staff may return on behalf of another user",
                    }
                ),
                403,
            )
        if not target:
            target = session.get("user_id")
        ok, msg, fine = lib.return_book(target, book_id, actor=session.get("user_id"))
        return jsonify({"success": ok, "message": msg, "fine": fine}), 200 if ok else 409

    # ════════════════════════════════════════════════════════════════
    # 6. GAMIFICATION PAGE (/gamification)
    # ════════════════════════════════════════════════════════════════

    @app.route("/gamification")
    @login_required
    def gamification_page() -> str:
        uid = session["user_id"]
        gd = gamification.get_user_gamification(uid) if gamification else {}
        leaderboard = gamification.get_leaderboard(top_n=20) if gamification else []

        pts = gd.get("points", 0)
        lvl = gd.get("level", "New Reader")
        streak = gd.get("streak_days", 0)
        next_lvl = gd.get("next_level", "")
        next_pts = gd.get("next_level_points", 0)
        unlocked = gd.get("unlocked_achievements", 0)
        total_ach = gd.get("total_achievements", 15)

        # Leaderboard
        LB = ""
        for entry in leaderboard[:10]:
            rank = entry.get("rank", 0)
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")
            LB += (
                '<div class="d-flex align-items-center gap-2 mb-2 p-2" style="border-radius:8px;border:1px solid var(--border);"><span style="min-width:30px;text-align:center;font-weight:700;">'
                + medal
                + "</span>"
                + avatar_html(entry.get("name", "?"), 28)
                + '<div class="flex-grow-1" style="min-width:0;"><div class="fw-bold small">'
                + h(entry.get("name", ""))
                + '</div><small class="text-muted">'
                + h(entry.get("level", ""))
                + '</small></div><span class="fw-bold">'
                + str(entry.get("points", 0))
                + " pts</span></div>"
            )
        if not LB:
            LB = '<div class="text-center text-muted small py-3">No leaderboard data yet.</div>'

        # Achievements grid
        ACH = ""
        for a in gd.get("achievements", []):
            unlocked_cls = "" if a.get("unlocked") else "opacity:0.4;filter:grayscale(1)"
            ACH += (
                '<div class="col-4 mb-2 text-center" style="'
                + unlocked_cls
                + '" title="'
                + h(a.get("desc", ""))
                + '"><div style="width:44px;height:44px;border-radius:12px;background:var(--primary-light);display:flex;align-items:center;justify-content:center;margin:0 auto .2rem;font-size:1.1rem;color:var(--primary);"><i class="bi bi-'
                + h(a.get("icon", "award"))
                + '-fill"></i></div><div style="font-size:.6rem;font-weight:600;line-height:1.2;">'
                + h(a.get("name", ""))
                + "</div></div>"
            )
        if not ACH:
            ACH = '<div class="col-12 text-center text-muted small py-3">No achievements yet.</div>'

        CONTENT = """<div class="animate-in">
    <div class="glass-card p-0 mb-3" style="overflow:hidden;">
        <div class="p-4" style="background:linear-gradient(135deg,#7c3aed,#a855f7);color:white;">
            <h4 class="fw-bold mb-0"><i class="bi bi-trophy-fill me-2"></i>Gamification</h4>
            <p class="mb-0" style="opacity:.8;font-size:.85rem;">Earn points, unlock achievements, and climb the leaderboard!</p>
        </div>
    </div>

    <div class="row g-3 mb-3">
        <div class="col-md-3">
            <div class="glass-card p-3 text-center h-100">
                <div style="font-size:2rem;font-weight:800;color:var(--primary);">%d</div>
                <div class="small text-muted">Points</div>
                <div class="progress-thin mt-2"><div class="bar" style="width:%d%%;background:var(--primary);"></div></div>
                <small class="text-muted">%s</small>
            </div>
        </div>
        <div class="col-md-3">
            <div class="glass-card p-3 text-center h-100">
                <div style="font-size:2rem;font-weight:800;color:var(--warning);">%s</div>
                <div class="small text-muted">Level</div>
                <small class="text-muted">%s</small>
            </div>
        </div>
        <div class="col-md-3">
            <div class="glass-card p-3 text-center h-100">
                <div style="font-size:2rem;font-weight:800;color:var(--danger);">🔥 %d</div>
                <div class="small text-muted">Day Streak</div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="glass-card p-3 text-center h-100">
                <div style="font-size:2rem;font-weight:800;color:var(--success);">%d/%d</div>
                <div class="small text-muted">Achievements</div>
            </div>
        </div>
    </div>

    <div class="row g-3">
        <div class="col-lg-8">
            <div class="glass-card p-3 mb-3">
                <div class="section-title"><i class="bi bi-award-fill text-warning"></i> Achievements (%d/%d)</div>
                <div class="row g-2">%s</div>
            </div>
        </div>
        <div class="col-lg-4">
            <div class="glass-card p-3">
                <div class="section-title"><i class="bi bi-bar-chart-fill"></i> Leaderboard</div>
                <div style="max-height:500px;overflow-y:auto;">%s</div>
            </div>
        </div>
    </div>
</div>""" % (
            pts,
            min(100, int(pts / max(1, pts + next_pts) * 100)) if next_pts > 0 else 100,
            ("Next: " + h(next_lvl) + " (" + str(next_pts) + " pts)") if next_lvl else "MAX LEVEL",
            h(lvl),
            h(lvl),
            streak,
            unlocked,
            total_ach,
            unlocked,
            total_ach,
            ACH,
            LB,
        )

        return render_page("Gamification", CONTENT)

    # ════════════════════════════════════════════════════════════════
    # 7. PROFILE PAGE (/profile/<uid>)
    # ════════════════════════════════════════════════════════════════

    @app.route("/profile/<user_id>")
    @login_required
    def profile_page(user_id) -> str:
        users_data = storage.load_users()
        user = users_data.get(user_id)
        if not user:
            return render_page("Not Found", '<div class="text-center py-5">User not found</div>')

        gd = gamification.get_user_gamification(user_id) if gamification else {}
        diary_stats = diary_mgr.get_stats(user_id) if diary_mgr else {}
        shelf_counts = review_mgr.get_shelf_counts(user_id) if review_mgr else {}

        av = avatar_html(user.name, 80)

        CONTENT = """<div class="animate-in">
    <div class="glass-card p-4 mb-3 text-center">
        %s
        <h4 class="fw-bold mt-2 mb-0">%s</h4>
        <small class="text-muted">@%s · %s</small>
        <div class="d-flex justify-content-center gap-3 mt-2">
            <div class="text-center"><div class="fw-bold">%d</div><small class="text-muted">Books</small></div>
            <div class="text-center"><div class="fw-bold">%d</div><small class="text-muted">Points</small></div>
            <div class="text-center"><div class="fw-bold">%s</div><small class="text-muted">Level</small></div>
        </div>
        <div class="mt-2">
            <a href="/profile/%s/export/pdf" class="btn btn-outline btn-sm"><i class="bi bi-file-earmark-pdf"></i> Export Report</a>
        </div>
    </div>
</div>""" % (
            av,
            h(user.name),
            h(user_id),
            h(user.role.capitalize()),
            diary_stats.get("total_books", 0),
            gd.get("points", 0),
            h(gd.get("level", "Reader")),
            h(user_id),
        )

        return render_page(h(user.name), CONTENT)

    # ════════════════════════════════════════════════════════════════
    # 8. PROFILE PDF EXPORT (/profile/<uid>/export/pdf)
    # ════════════════════════════════════════════════════════════════

    @app.route("/profile/<uid>/export/pdf")
    @login_required
    def profile_export_pdf(uid) -> Any:
        users_data = storage.load_users()
        user = users_data.get(uid)
        if not user:
            return render_page("Not Found", '<div class="text-center py-5">User not found</div>')

        diary_stats = {}
        diary_entries = []
        try:
            if diary_mgr:
                diary_entries, _ = diary_mgr.get_user_diary(uid, page=1, per_page=500)
                diary_stats = diary_mgr.get_stats(uid) if diary_mgr else {}
        except (AttributeError, TypeError, KeyError):
            pass

        reading_stats = {}
        challenge_data = {}
        try:
            reading_stats = review_mgr.get_user_reading_stats(uid) if review_mgr else {}
            challenge_data = challenge.get_goal(uid, datetime.now().year) if challenge else {}
        except (AttributeError, TypeError, KeyError):
            pass

        year = datetime.now().year
        total_books = diary_stats.get("total_books", 0)
        total_pages = diary_stats.get("total_pages_read", 0)
        streak_info = {}
        with contextlib.suppress(Exception):
            streak_info = gamification.get_user_gamification(uid) if gamification else {}

        entries_html = ""
        for e in diary_entries[-10:]:
            entries_html += (
                '<div style="margin-bottom:.5rem;padding-bottom:.5rem;border-bottom:1px solid #eee;"><strong>'
                + h(e.get("book_title", ""))
                + "</strong> <small>("
                + str(e.get("date_read", "")[:10])
                + ')</small><br><span style="color:#666;">'
                + h(e.get("diary_text", "")[:100])
                + "</span></div>"
            )
        if not entries_html:
            entries_html = '<p style="color:#999;">No reading entries recorded.</p>'

        CONTENT = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Reading Report - %s</title>
<style>
body{font-family:Georgia,serif;color:#333;max-width:800px;margin:0 auto;padding:2rem}
h1{color:#4f46e5;border-bottom:3px solid #4f46e5;padding-bottom:.5rem}
.stats-row{display:flex;gap:1rem;margin:1rem 0}
.stat{text-align:center;padding:1rem;background:#f8f8fc;border-radius:8px;flex:1}
.stat .num{font-size:2rem;font-weight:800;color:#4f46e5}
.stat .lbl{font-size:.75rem;color:#666;text-transform:uppercase}
section{margin:2rem 0}
h2{color:#4f46e5}
@media print{body{padding:0}}
</style></head><body>
<h1>📚 Annual Reading Report</h1>
<p><strong>%s</strong> · @%s · %d</p>

<section>
<div class="stats-row">
<div class="stat"><div class="num">%d</div><div class="lbl">Books Read</div></div>
<div class="stat"><div class="num">%d</div><div class="lbl">Pages Read</div></div>
<div class="stat"><div class="num">%d</div><div class="lbl">Reading Streak</div></div>
<div class="stat"><div class="num">%d%%</div><div class="lbl">Goal Progress</div></div>
</div>
</section>

<section>
<h2>Recent Reads</h2>
%s
</section>

<section>
<h2>Stats</h2>
<p>Avg Rating: <strong>%.1f</strong></p>
<p>Challenge Goal: <strong>%d / %d</strong> books</p>
<p>Level: <strong>%s</strong> (%d points)</p>
</section>

<hr>
<small>BookTale · %s</small>
</body></html>""" % (
            h(user.name),
            h(user.name),
            h(uid),
            year,
            total_books,
            total_pages,
            streak_info.get("streak_days", 0),
            round(challenge_data.get("percentage", 0)),
            entries_html,
            reading_stats.get("avg_rating", 0),
            challenge_data.get("progress", 0),
            challenge_data.get("goal", 0),
            streak_info.get("level", "Reader"),
            streak_info.get("points", 0),
            datetime.now().strftime("%B %d, %Y"),
        )

        from flask import make_response

        r = make_response(CONTENT)
        r.headers["Content-Type"] = "text/html"
        r.headers["Content-Disposition"] = (
            'attachment; filename="reading_report_' + uid + "_" + str(year) + '.html"'
        )
        return r

    return app
