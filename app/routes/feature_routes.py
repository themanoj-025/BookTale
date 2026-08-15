"""
feature_routes.py - Routes & Pages for Series, Reading Challenge, Reading Progress, and Wishlist

Integrates with the existing Flask web_app.py by registering routes on the app.
Uses the same patterns as social_routes.py for consistency.
"""

import html
import json
import zlib
from datetime import datetime
from functools import wraps

from flask import jsonify, redirect, render_template, request, session, url_for

from app.services.reading.diary import (
    RATING_LABELS,
    RATING_SCORES,
    rating_badge_html,
    star_rating_html,
)

_series = None
_challenge = None
_progress = None
_wishlist = None
_storage = None
_lib = None
_notif_mgr = None
_h = None
_avatar_html = None


def init_feature_routes(
    app, storage, lib, auth, notif_mgr, series, challenge, progress, wishlist, diary
):
    global _storage, _lib, _notif_mgr, _series, _challenge, _progress, _wishlist, _h, _avatar_html, _diary
    _storage = storage
    _lib = lib
    _notif_mgr = notif_mgr
    _series = series
    _challenge = challenge
    _progress = progress
    _wishlist = wishlist
    _diary = diary

    def _rate_limit(limit_value, **kwargs):
        """Rate-limit decorator; no-op fallback if flask-limiter is missing.

        Reads the single limiter instance that web_app exposes as
        app.extensions["booktale_limiter"] (flask-limiter 4.x stores itself
        in app.extensions["limiter"] as a SET, or not at all when
        RATELIMIT_ENABLED=0, so we must not depend on that key). This module
        needs no import from web_app, avoiding a circular import.
        """
        _lim = app.extensions.get("booktale_limiter")
        if _lim is None:
            return lambda f: f
        return _lim.limit(limit_value, **kwargs)

    def h(text):
        return html.escape(str(text))

    def _js_str(value):
        """Escape a value for a single-quoted JS string inside a double-quoted
        HTML attribute (onclick="..."). Escapes backslashes and single quotes
        for the JS string literal, and double quotes for the HTML attribute.
        """
        return str(value).replace("\\", "\\\\").replace("'", "\\'").replace('"', "&quot;")

    def _initials(name):
        parts = name.strip().split()
        if not parts:
            return "?"
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return parts[0][:2].upper()

    def _avatar_color(name):
        # Deterministic across processes (hash() is randomized per-process).
        colors = [
            "#4f46e5",
            "#059669",
            "#d97706",
            "#dc2626",
            "#0891b2",
            "#7c3aed",
            "#db2777",
            "#ca8a04",
        ]
        return colors[zlib.crc32(str(name).encode("utf-8")) % len(colors)]

    def avatar_html(name, size=32):
        i = _initials(name)
        c = _avatar_color(name)
        return f'<div class="avatar" style="width:{size}px;height:{size}px;background:{c}20;color:{c};font-size:{size // 2}px;font-weight:700;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;" title="{h(name)}">{h(i)}</div>'

    _h = h
    _avatar_html = avatar_html

    def get_current_user():
        if "user_id" not in session:
            return None
        return storage.load_users().get(session["user_id"])

    def render_page(title, content, **kw):
        user = get_current_user()
        return render_template(
            "base.html",
            title=title,
            content=content,
            session=session,
            notif_count=notif_mgr.get_unread_count(user.user_id) if user else 0,
            **kw,
        )

    def login_required(f):
        @wraps(f)
        def d(*a, **k):
            if "user_id" not in session:
                return redirect(url_for("login_page"))
            return f(*a, **k)

        return d

    def admin_required(f):
        @wraps(f)
        def d(*a, **k):
            if "user_id" not in session:
                return redirect(url_for("login_page"))
            if session.get("role") != "admin":
                return jsonify({"error": "Admin access required"}), 403
            return f(*a, **k)

        return d

    def cat_color(c):
        colors = {
            "Fiction": "#4f46e5",
            "Non-Fiction": "#059669",
            "Science": "#0891b2",
            "Technology": "#7c3aed",
            "History": "#d97706",
            "Philosophy": "#be185d",
            "Art": "#db2777",
            "Biography": "#ca8a04",
            "Children": "#16a34a",
            "Comics": "#e11d48",
            "Poetry": "#9333ea",
            "Drama": "#ea580c",
            "Education": "#2563eb",
            "Reference": "#64748b",
            "Religion": "#78716c",
            "Self-Help": "#0d9488",
            "Cooking": "#f97316",
            "Travel": "#0ea5e9",
            "Music": "#8b5cf6",
            "Sports": "#22c55e",
            "Other": "#6b7280",
        }
        return colors.get(c, colors["Other"])

    # ═══════════════════════════════════════════════════════════
    # 1. BOOK SERIES PAGES
    # ═══════════════════════════════════════════════════════════

    @app.route("/series")
    @login_required
    def series_list_page():
        page = max(1, int(request.args.get("page", 1)))
        q = request.args.get("q", "")
        series_list, total = _series.get_all_series(page=page)
        if q:
            series_list = _series.search_series(q)

        CARDS = ""
        for s in series_list:
            cat = s.get("category", "")
            cc = cat_color(cat) if cat else "#4f46e5"
            CARDS += f"""<div class="col-md-6 col-lg-4 mb-3 animate-scale">
                <div class="glass-card p-3 h-100" onclick="window.location.href='/series/{s["series_id"]}'" style="cursor:pointer;">
                    <div class="d-flex gap-3">
                        <div style="width:48px;height:48px;border-radius:12px;background:linear-gradient(135deg,{cc},{cc}dd);display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                            <i class="bi bi-collection-fill" style="color:white;font-size:1.3rem;"></i>
                        </div>
                        <div class="flex-grow-1" style="min-width:0;">
                            <div class="fw-bold" style="font-size:.95rem;">{h(s["name"])}</div>
                            <small class="text-muted">{s.get("book_count", 0)} book{"" if s.get("book_count", 0) == 1 else "s"}</small>
                            <div style="font-size:.75rem;color:var(--text-muted);margin-top:.3rem;">{h(s.get("description", "")[:80])}</div>
                        </div>
                    </div>
                </div>
            </div>"""
        if not CARDS:
            CARDS = '<div class="col-12"><div class="empty-state empty-state-variant"><div class="empty-icon"><i class="bi bi-collection"></i></div><div class="empty-title">No series yet</div><div class="empty-desc">Create your first book series to organize books.</div><a href="/series/create" class="empty-cta"><i class="bi bi-plus-lg"></i> Create Series</a></div></div>'

        CONTENT = f"""
        <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2 animate-in">
            <h4 class="fw-bold mb-0"><i class="bi bi-collection-fill me-2 text-primary"></i>Book Series <span class="text-muted fw-normal" style="font-size:.9rem;">({total})</span></h4>
            <a href="/series/create" class="btn btn-primary btn-sm"><i class="bi bi-plus-lg"></i> New Series</a>
        </div>
        <form class="mb-3 animate-d1" role="search"><div class="search-filters">
            <input type="text" name="q" class="form-control" placeholder="Search series..." value="{h(q) if q else ""}" style="min-width:200px;">
            <button class="btn btn-primary" type="submit"><i class="bi bi-search"></i></button>
            <a href="/series" class="btn btn-outline"><i class="bi bi-x-lg"></i></a>
        </div></form>
        <div class="row g-3 animate-d2">{CARDS}</div>"""
        return render_page("Book Series", CONTENT)

    @app.route("/series/create", methods=["GET", "POST"])
    @login_required
    @admin_required
    def series_create():
        if request.method == "GET":
            from app.models.book import CATEGORIES as BOOK_CATEGORIES

            co = "".join(f'<option value="{c}">{c}</option>' for c in BOOK_CATEGORIES)
            # Phase 4: CSRF token for the string-built native POST form.
            # Narrow catches: only an ImportError (no flask-wtf) or a missing
            # request context can fail generate_csrf inside this view.
            try:
                from flask_wtf.csrf import generate_csrf as _gen_csrf

                csrf_field = '<input type="hidden" name="csrf_token" value="' + _gen_csrf() + '">'
            except (ImportError, RuntimeError):
                csrf_field = ""
            CONTENT = f"""
            <div class="row justify-content-center animate-in">
                <div class="col-md-8 col-lg-6">
                    <h4 class="fw-bold mb-3"><i class="bi bi-plus-circle-fill text-primary me-2"></i>Create Book Series</h4>
                    <div class="glass-card p-4">
                        <form method="POST">
                            {csrf_field}
                            <div class="mb-3"><label class="form-label">Series Name</label>
                                <input type="text" name="name" class="form-control" placeholder="e.g. Harry Potter" required></div>
                            <div class="mb-3"><label class="form-label">Description</label>
                                <textarea name="description" class="form-control" rows="3" placeholder="About this series..."></textarea></div>
                            <div class="mb-3"><label class="form-label">Category</label>
                                <select name="category" class="form-select">{co}</select></div>
                            <div class="row"><div class="col-md-6 mb-3"><label class="form-label">Total Planned Books</label>
                                <input type="number" name="total_books" class="form-control" value="0" min="0"></div></div>
                            <div class="d-flex gap-2">
                                <button type="submit" class="btn btn-primary"><i class="bi bi-save me-1"></i>Create</button>
                                <a href="/series" class="btn btn-outline">Cancel</a>
                            </div>
                        </form>
                    </div>
                </div>
            </div>"""
            return render_page("Create Series", CONTENT)
        ok, msg, _ = _series.create_series(
            request.form["name"],
            request.form.get("description", ""),
            request.form.get("category", ""),
            session.get("user_id", "web"),
        )
        if ok:
            return redirect(url_for("series_list_page"))
        return render_page("Error", f'<div class="alert alert-danger">{h(msg)}</div>')

    @app.route("/series/<series_id>")
    @login_required
    def series_detail(series_id):
        s = _series.get_series(series_id)
        if not s:
            return render_page(
                "Not Found",
                '<div class="empty-state empty-state-variant"><div class="empty-icon"><i class="bi bi-collection"></i></div><div class="empty-title">Series not found</div><div class="empty-desc">The series you are looking for does not exist.</div><a href="/series" class="empty-cta"><i class="bi bi-arrow-left"></i> Browse Series</a></div>',
            )
        books = _series.get_series_books(s["name"])
        cat = s.get("category", "")
        cc = cat_color(cat) if cat else "#4f46e5"

        BOOKS_HTML = ""
        for i, b in enumerate(books):
            bcc = cat_color(b.get("category", ""))
            order = b.get("series_order", 0) or (i + 1)
            avail = (
                '<span class="badge-green px-2 py-1 small">Available</span>'
                if b.get("available_copies", 0) > 0
                else '<span class="badge-red px-2 py-1 small">Out</span>'
            )
            BOOKS_HTML += f"""
            <div class="col-md-6 mb-2">
                <div class="glass-card p-2 d-flex align-items-center gap-3" onclick="window.location.href='/books/{b["book_id"]}'" style="cursor:pointer;">
                    <div style="width:40px;height:40px;border-radius:10px;background:{bcc}20;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-weight:800;color:{bcc};">#{order}</div>
                    <div class="flex-grow-1" style="min-width:0;">
                        <div class="fw-bold" style="font-size:.9rem;">{h(b["title"])}</div>
                        <small class="text-muted">{h(b["author"])}</small>
                    </div>
                    <div class="flex-shrink-0">{avail}</div>
                </div>
            </div>"""
        if not BOOKS_HTML:
            BOOKS_HTML = '<div class="col-12"><div class="empty-state empty-state-variant"><div class="empty-icon"><i class="bi bi-book"></i></div><div class="empty-title">No books in this series yet</div><div class="empty-desc">Add books to this series to organize them.</div></div></div>'

        CONTENT = f"""
        <div class="row animate-in">
            <div class="col-lg-8">
                <div class="glass-card p-4 mb-3">
                    <div class="d-flex gap-3 mb-3">
                        <div style="width:64px;height:64px;border-radius:14px;background:linear-gradient(135deg,{cc},{cc}dd);display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                            <i class="bi bi-collection-fill" style="color:white;font-size:1.5rem;"></i>
                        </div>
                        <div>
                            <h3 class="fw-bold mb-1">{h(s["name"])}</h3>
                            <p class="text-muted mb-2">{h(s.get("description", ""))}</p>
                            <div class="d-flex gap-2">
                                <span class="badge" style="background:{cc}20;color:{cc};">{h(cat) if cat else "General"}</span>
                                <span class="badge bg-secondary">{len(books)} book{"" if len(books) == 1 else "s"}</span>
                                {f'<span class="badge bg-info">{s["total_books"]} planned</span>' if s.get("total_books", 0) > 0 else ""}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-lg-4">
                <div class="glass-card p-3 mb-3">
                    <div class="section-title"><i class="bi bi-info-circle"></i> About</div>
                    <div class="info-grid">
                        <div class="info-card"><div class="value">{len(books)}</div><div class="label">Books</div></div>
                        <div class="info-card"><div class="value">{sum(b.get("issue_count", 0) for b in books)}</div><div class="label">Total Issues</div></div>
                        <div class="info-card"><div class="value">{sum(b.get("available_copies", 0) for b in books)}</div><div class="label">Available</div></div>
                    </div>
                </div>
            </div>
        </div>
        <h5 class="fw-bold mb-3 animate-d1"><i class="bi bi-book-fill me-1"></i>Books in this Series</h5>
        <div class="row g-2 animate-d2">{BOOKS_HTML}</div>"""
        return render_page(s["name"], CONTENT)

    @app.route("/api/series/search")
    @login_required
    def api_series_search():
        q = request.args.get("q", "")
        return jsonify({"series": _series.search_series(q) if q else []})

    @app.route("/api/series/suggestions")
    @login_required
    def api_series_suggestions():
        q = request.args.get("q", "")
        return jsonify({"suggestions": _series.get_series_suggestions(q) if q else []})

    @app.route("/api/series/<series_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    # Defense in depth: destructive admin op — cap per IP well below the
    # global 200/min default to limit the blast radius of a compromised
    # admin session.
    @_rate_limit("20 per minute")
    def api_series_delete(series_id):
        ok, msg = _series.delete_series(series_id)
        return jsonify({"success": ok, "message": msg})

    # ═══════════════════════════════════════════════════════════
    # 2. READING CHALLENGE PAGES
    # ═══════════════════════════════════════════════════════════

    @app.route("/reading-challenge")
    @login_required
    def reading_challenge_page():
        uid = session["user_id"]
        year = int(request.args.get("year", datetime.now().year))
        goal = _challenge.get_goal(uid, year)
        chart = _challenge.get_progress_chart_data(uid, year)
        leaderboard = _challenge.get_leaderboard(year, top_n=10)
        summary = _challenge.get_user_challenges_summary(uid)

        progress_pct = goal.get("percentage", 0)
        progress_bar_color = (
            "var(--success)"
            if progress_pct >= 100
            else ("var(--warning)" if progress_pct >= 50 else "var(--primary)")
        )
        on_track_badge = (
            '<span class="badge bg-success">🎯 On Track</span>'
            if goal.get("on_track")
            else '<span class="badge bg-warning text-dark">⚠️ Behind Pace</span>'
        )

        LB = ""
        for entry in leaderboard:
            rank = entry.get("rank", 0)
            lb_avatar = avatar_html(entry.get("name", "?"), 28)
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")
            lb_bar_w = min(100, entry.get("percentage", 0))
            lb_bar_c = "var(--success)" if entry["percentage"] >= 100 else "var(--primary)"
            LB += f"""
            <div class="d-flex align-items-center gap-2 mb-2">
                <span style="width:28px;text-align:center;font-weight:700;">{medal}</span>
                {lb_avatar}
                <div class="flex-grow-1" style="min-width:0;">
                    <div class="fw-bold small">{h(entry["name"])}</div>
                    <div class="progress-thin"><div class="bar" style="width:{lb_bar_w}%;background:{lb_bar_c};"></div></div>
                </div>
                <small class="fw-bold">{entry["count"]}/{entry["goal"] if entry.get("goal") else "—"}</small>
            </div>"""
        if not LB:
            LB = '<div class="text-center text-muted small py-3">No data yet. Start reading!</div>'

        CHART_JS = ""
        if chart and chart.get("monthly"):
            months_json = json.dumps(chart["labels"])
            monthly_json = json.dumps(chart["monthly"])
            cumul_json = json.dumps(chart["cumulative"])
            CHART_JS = f"""
            new Chart(document.getElementById(\"challengeChart\"), {{
                type: 'bar',
                data: {{
                    labels: {months_json},
                    datasets: [{{
                        label: 'Books Read',
                        data: {monthly_json},
                        backgroundColor: 'rgba(79,70,229,0.6)',
                        borderColor: '#4f46e5',
                        borderWidth: 2,
                        borderRadius: 4,
                        order: 2
                    }}, {{
                        label: 'Cumulative',
                        data: {cumul_json},
                        type: 'line',
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16,185,129,0.1)',
                        fill: true,
                        tension: .3,
                        pointRadius: 3,
                        pointBackgroundColor: '#10b981',
                        borderWidth: 2,
                        order: 1
                    }}]
                }},
                options: {{
                    responsive: true, maintainAspectRatio: false,
                    plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 10, font: {{size: 10}} }} }} }},
                    scales: {{ y: {{ beginAtZero: true, grid: {{ color: 'rgba(0,0,0,0.04)' }}, ticks: {{ stepSize: 1 }} }}, x: {{ grid: {{ display: false }} }} }}
                }}
            }});}}"""

        YEAR_SELECTOR = ""
        for y in range(year - 2, year + 1):
            YEAR_SELECTOR += f'<a href="/reading-challenge?year={y}" class="btn {"btn-primary" if y == year else "btn-outline"} btn-sm">{"📅 " if y == datetime.now().year else ""}{y}</a>'

        CONTENT = f"""
        <div class="animate-in">
            <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
                <h4 class="fw-bold mb-0"><i class="bi bi-trophy-fill me-2 text-warning"></i>Reading Challenge</h4>
                <div class="d-flex gap-1">{YEAR_SELECTOR}</div>
            </div>

            <div class="row mb-3">
                <div class="col-lg-8 mb-3">
                    <div class="glass-card p-4">
                        <div class="d-flex justify-content-between align-items-start mb-3">
                            <div>
                                <h5 class="fw-bold mb-1">{year} Reading Goal</h5>
                                <p class="text-muted small mb-0">{len(chart.get("monthly", []))} months of data</p>
                            </div>
                            <div class="text-end">
                                <div style="font-size:2rem;font-weight:800;color:var(--primary);">{goal.get("progress", 0)}<span style="font-size:1rem;color:var(--text-muted);">/{goal.get("goal", 0)}</span></div>
                                <div class="small text-muted">books read</div>
                            </div>
                        </div>
                        <div class="progress-thin mb-3" style="height:12px;border-radius:6px;">
                            <div class="bar" style="width:{progress_pct}%;background:{progress_bar_color};height:12px;border-radius:6px;"></div>
                        </div>
                        <div class="d-flex justify-content-between align-items-center">
                            <div class="d-flex gap-2 flex-wrap">
                                <span class="badge" style="background:var(--primary)20;color:var(--primary);">📈 Pace: {goal.get("pace", 0)}/mo</span>
                                <span class="badge" style="background:#10b98120;color:#10b981;">📊 Projected: {goal.get("projected_total", 0)}</span>
                                {on_track_badge}
                            </div>
                            <div class="d-flex gap-1">
                                <button class="btn btn-primary btn-sm" onclick="setReadingGoal()"><i class="bi bi-pencil"></i> Set Goal</button>
                            </div>
                        </div>
                        <hr style="border-color:var(--border);">
                        <div class="row text-center">
                            <div class="col-4"><span class="fw-bold text-success">{goal.get("progress", 0)}</span><br><small class="text-muted">Read</small></div>
                            <div class="col-4"><span class="fw-bold text-warning">{goal.get("remaining", 0)}</span><br><small class="text-muted">Remaining</small></div>
                            <div class="col-4"><span class="fw-bold text-info">{goal.get("days_remaining", 0)}</span><br><small class="text-muted">Days Left</small></div>
                        </div>
                    </div>
                </div>
                <div class="col-lg-4 mb-3">
                    <div class="glass-card p-3 h-100">
                        <div class="section-title"><i class="bi bi-trophy-fill text-warning"></i> Leaderboard {year}</div>
                        <div style="max-height:350px;overflow-y:auto;">{LB}</div>
                    </div>
                </div>
            </div>

            <div class="glass-card p-3 mb-3 animate-d1">
                <div class="section-title"><i class="bi bi-graph-up-arrow text-primary"></i> Monthly Progress</div>
                <div class="chart-container" style="height:250px;"><canvas id="challengeChart"></canvas></div>
            </div>

            <div class="glass-card p-3 animate-d2">
                <div class="section-title"><i class="bi bi-calendar-check"></i> Past Challenges</div>
                <div class="row g-2">
                    {"".join(f'<div class="col-md-4"><div class="glass-card p-3 text-center"><div class="fw-bold">{y["year"]}</div><div class="progress-thin mt-2"><div class="bar" style="width:{y["percentage"]}%;background:var(--primary);"></div></div><div class="mt-1"><span class="fw-bold">{y["progress"]}</span><small class="text-muted">/{y["goal"]}</small></div></div></div>' for y in summary.get("years", []))}
                </div>
            </div>
        </div>
        <script>
        function setReadingGoal() {{
            var current = {goal.get("goal", 0)};
            var goal = prompt("How many books do you want to read in {year}?", current || 12);
            if (goal && parseInt(goal) > 0) {{
                fetch('/api/reading-challenge/goal', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{goal: parseInt(goal), year: {year}}})
                }}).then(r=>r.json()).then(d=>{{
                    if(d.success){{showToast(d.message,'success');setTimeout(function(){{location.reload()}},1200)}}
                    else{{showToast(d.error,'error')}}
                }});}}
            }}
        }}
        {CHART_JS}
        </script>"""
        return render_page("Reading Challenge", CONTENT)

    @app.route("/api/reading-challenge/goal", methods=["POST"])
    @login_required
    def api_set_reading_goal():
        uid = session["user_id"]
        data = request.get_json() or {}
        goal = int(data.get("goal", 12))
        year = int(data.get("year", datetime.now().year))
        ok, msg = _challenge.set_goal(uid, year, goal)
        return jsonify({"success": ok, "message": msg})

    @app.route("/api/reading-challenge/progress")
    @login_required
    def api_reading_progress_data():
        uid = session["user_id"]
        year = int(request.args.get("year", datetime.now().year))
        goal = _challenge.get_goal(uid, year)
        chart = _challenge.get_progress_chart_data(uid, year)
        return jsonify({"goal": goal, "chart": chart})

    @app.route("/api/reading-challenge/leaderboard")
    @login_required
    def api_reading_leaderboard():
        year = int(request.args.get("year", datetime.now().year))
        top_n = min(int(request.args.get("top_n", 10)), 50)
        return jsonify({"leaderboard": _challenge.get_leaderboard(year, top_n)})

    @app.route("/api/reading-challenge/stats")
    @login_required
    def api_reading_challenge_stats():
        uid = session["user_id"]
        year = int(request.args.get("year", datetime.now().year))
        goal = _challenge.get_goal(uid, year)
        return jsonify(
            {
                "total_books": goal.get("progress", 0),
                "goal": goal.get("goal", 0),
                "year": year,
                "percentage": goal.get("percentage", 0),
                "pace": goal.get("pace", 0),
                "days_remaining": goal.get("days_remaining", 0),
                "projected": goal.get("projected_total", 0),
            }
        )

    # ═══════════════════════════════════════════════════════════
    # 3. READING PROGRESS PAGES
    # ═══════════════════════════════════════════════════════════

    @app.route("/reading-progress")
    @login_required
    def reading_progress_page():
        uid = session["user_id"]
        rl = _progress.get_user_reading_list(uid)
        stats = _progress.get_reading_stats(uid)

        def render_book_list(books, empty_msg):
            if not books:
                return f'<div class="text-center text-muted small py-3">{empty_msg}</div>'
            html = ""
            for b in books:
                pct = b.get("percentage", 0)
                cc = cat_color(b.get("book_category", ""))
                bar_col = "var(--success)" if pct >= 100 else "var(--primary)"
                html += f"""
                <div class="d-flex align-items-center gap-2 mb-2 p-2" style="border-radius:8px;border:1px solid var(--border);">
                    <div style="width:36px;height:36px;border-radius:8px;background:{cc}20;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                        <i class="bi bi-book-fill" style="color:{cc};"></i>
                    </div>
                    <div class="flex-grow-1" style="min-width:0;">
                        <a href="/books/{h(b["book_id"])}" class="fw-bold text-decoration-none" style="color:var(--text);font-size:.85rem;">{h(b.get("book_title", ""))[:40]}</a>
                        <div class="progress-thin mt-1"><div class="bar" style="width:{pct}%;background:{bar_col};"></div></div>
                        <small class="text-muted" style="font-size:.65rem;">{pct}% · Page {b.get("current_page", 0)}/{b.get("total_pages", 0)}</small>
                    </div>
                    <a href="/reading-progress/{h(b["book_id"])}" class="btn btn-sm btn-outline" style="flex-shrink:0;"><i class="bi bi-arrow-right"></i></a>
                </div>"""
            return html

        READING = render_book_list(
            rl.get("currently_reading", []), "No books being read right now."
        )
        FINISHED = render_book_list(rl.get("finished", [])[:5], "No finished books yet.")

        time_h = stats.get("total_time_spent_minutes", 0) // 60
        time_m = stats.get("total_time_spent_minutes", 0) % 60

        CONTENT = f"""
        <div class="animate-in">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h4 class="fw-bold mb-0"><i class="bi bi-bookmark-check-fill me-2 text-primary"></i>Reading Progress</h4>
            </div>
            <div class="stats-bar mb-3 animate-in">
                <div class="stat-item"><div class="num">{stats.get("books_started", 0)}</div><div class="desc">Started</div></div>
                <div class="stat-item"><div class="num">{stats.get("books_finished", 0)}</div><div class="desc">Finished</div></div>
                <div class="stat-item"><div class="num">{stats.get("completion_rate", 0)}%</div><div class="desc">Completion</div></div>
                <div class="stat-item"><div class="num">{stats.get("total_pages_read", 0)}</div><div class="desc">Pages Read</div></div>
                <div class="stat-item"><div class="num">{time_h}h {time_m}m</div><div class="desc">Time Spent</div></div>
            </div>
            <div class="row">
                <div class="col-lg-7 mb-3">
                    <div class="glass-card p-3">
                        <div class="section-title"><i class="bi bi-book-fill text-primary"></i> Currently Reading ({len(rl.get("currently_reading", []))})</div>
                        {READING}
                    </div>
                    <div class="glass-card p-3 mt-3">
                        <div class="section-title"><i class="bi bi-check-circle-fill text-success"></i> Recently Finished ({len(rl.get("finished", []))})</div>
                        {FINISHED}
                        {'<a href="/reading-progress/history" class="btn btn-outline btn-sm mt-2 w-100"><i class="bi bi-clock-history"></i> View All</a>' if len(rl.get("finished", [])) > 5 else ""}
                    </div>
                </div>
                <div class="col-lg-5 mb-3">
                    <div class="glass-card p-3 mb-3">
                        <div class="section-title"><i class="bi bi-bookmark-fill text-warning"></i> Quick Update</div>
                        <p class="text-muted small">Update your progress for a book you are reading.</p>
                        <div class="input-group mb-2">
                            <input type="text" id="progressBookSearch" class="form-control" placeholder="Search a book..." oninput="searchProgressBooks(this.value)">
                        </div>
                        <div id="progressBookResults" class="mb-2"></div>
                        <div id="progressUpdateForm" style="display:none;">
                            <hr style="border-color:var(--border);">
                            <label class="form-label">Current Page</label>
                            <div class="input-group">
                                <input type="number" id="progressPage" class="form-control" min="1" placeholder="Page number">
                                <button class="btn btn-primary" onclick="submitProgressUpdate()"><i class="bi bi-check"></i> Update</button>
                            </div>
                            <small class="text-muted" id="progressBookInfo"></small>
                        </div>
                    </div>
                    <div class="glass-card p-3">
                        <div class="section-title"><i class="bi bi-bookmark-heart-fill text-danger"></i> My Bookmarks</div>
                        <div id="bookmarksList"><div class="text-center text-muted small py-3">Loading...</div></div>
                    </div>
                </div>
            </div>
        </div>
        <script>
        var selectedProgressBookId = null;
        function searchProgressBooks(q){{
            if(q.length<2){{ document.getElementById(\"progressBookResults\").innerHTML=\"\";return}}
            fetch('/api/books?q='+encodeURIComponent(q)).then(r=>r.json()).then(books=>{{
                var c=document.getElementById(\"progressBookResults\");
                if(!books.length){{c.innerHTML="<div class=\"text-muted small\">No books found</div>";return}}
                c.innerHTML=books.slice(0,5).map(b=>'<div class="search-result-item" style="cursor:pointer;padding:.3rem .5rem;" onclick="selectProgressBook(\\''+booktaleUtils.jsStr(b.book_id)+'\\',\\''+booktaleUtils.jsStr(b.title)+'\\','+(b.pages||0)+')">'+booktaleUtils.escapeHtml(b.title)+' <small class="text-muted">'+booktaleUtils.escapeHtml(b.author)+'</small></div>').join('')
            }})
        }}
        function selectProgressBook(bid,title,pages){{
            selectedProgressBookId=bid;
            document.getElementById(\"progressBookSearch\").value=title;
            document.getElementById(\"progressBookResults\").innerHTML=\"\";
            document.getElementById(\"progressUpdateForm\").style.display='block';
            document.getElementById(\"progressBookInfo\").textContent=title+' ('+(pages||'?')+' pages)';
            document.getElementById(\"progressPage\").max=pages||9999;
        }}
        function submitProgressUpdate(){{
            var page=document.getElementById(\"progressPage\").value;
            if(!selectedProgressBookId||!page){{showToast('Select a book and enter a page','error');return}}
            fetch('/api/reading-progress/'+selectedProgressBookId+'/update',{{
                method:'POST',
                headers:{{'Content-Type':'application/json'}},
                body:JSON.stringify({{current_page:parseInt(page)}})
            }}).then(r=>r.json()).then(d=>{{
                if(d.success){{showToast(d.message,'success');setTimeout(function(){{location.reload()}},1200)}}
                else{{showToast(d.error,'error')}}
            }})
        }}
        fetch('/api/bookmarks').then(r=>r.json()).then(d=>{{
            var c=document.getElementById(\"bookmarksList\");
            if(!d.bookmarks||!d.bookmarks.length){{c.innerHTML='<div class="text-center text-muted small py-3">No bookmarks yet.</div>';return}}
            c.innerHTML=d.bookmarks.slice(0,8).map(b=>'<div class="d-flex align-items-center gap-2 mb-2 p-1" style="border-bottom:1px solid var(--border);"><i class="bi bi-bookmark-fill text-warning"></i><div class="flex-grow-1" style="min-width:0;"><span class="fw-bold small">'+booktaleUtils.escapeHtml(b.book_title)+'</span><br><small class="text-muted">Page '+booktaleUtils.escapeHtml(b.page)+(b.note?' &middot; '+booktaleUtils.escapeHtml(b.note):'')+'</small></div><a href="/reading-progress/'+booktaleUtils.jsStr(b.book_id)+'" class="btn btn-sm btn-outline"><i class="bi bi-arrow-right"></i></a></div>').join('')
        }})
        </script>"""
        return render_page("Reading Progress", CONTENT)

    @app.route("/reading-progress/<book_id>")
    @login_required
    def reading_progress_book(book_id):
        uid = session["user_id"]
        book = _storage.load_books().get(book_id)
        if not book:
            return render_page(
                "Not Found",
                '<div class="empty-state empty-state-variant"><div class="empty-icon"><i class="bi bi-book-x"></i></div><div class="empty-title">Book not found</div><div class="empty-desc">This book may have been removed or does not exist.</div></div>',
            )
        progress = _progress.get_progress(uid, book_id)
        bookmarks = _progress.get_book_bookmarks(uid, book_id)

        BM_HTML = ""
        for bm in bookmarks:
            BM_HTML += f"""
            <div class="d-flex align-items-center gap-2 mb-2 p-2" style="border-radius:8px;border:1px solid var(--border);">
                <i class="bi bi-bookmark-fill text-warning"></i>
                <div class="flex-grow-1"><strong>Page {bm['page']}</strong> &middot; {h(bm.get('note', ''))}</div>
                <button class="btn btn-sm btn-outline" onclick="removeBookmark(\'{bm["bookmark_id"]}\')"><i class="bi bi-trash"></i></button>
            </div>"""
        if not BM_HTML:
            BM_HTML = (
                '<div class="text-center text-muted small py-3">No bookmarks. Add one below!</div>'
            )

        cc = cat_color(book.category)
        CONTENT = f"""
        <div class="animate-in">
            <div class="row">
                <div class="col-lg-8">
                    <div class="glass-card p-4 mb-3">
                        <div class="d-flex gap-3">
                            <div style="width:56px;height:56px;border-radius:12px;background:linear-gradient(135deg,{cc},{cc}dd);display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                                <i class="bi bi-book-fill" style="color:white;font-size:1.3rem;"></i>
                            </div>
                            <div class="flex-grow-1">
                                <h5 class="fw-bold mb-1">{h(book.title)}</h5>
                                <p class="text-muted mb-0">{h(book.author)}</p>
                            </div>
                            <div class="text-end">
                                <div class="fw-bold" style="font-size:1.5rem;color:var(--primary);">{progress.get("percentage", 0)}%</div>
                                <small class="text-muted">{progress.get("current_page", 0)}/{progress.get("total_pages", 0) or "?"} pages</small>
                            </div>
                        </div>
                        <div class="progress-thin mt-3" style="height:10px;border-radius:5px;">
                            <div class="bar" style="width:{progress.get("percentage", 0)}%;background:var(--primary);height:10px;border-radius:5px;"></div>
                        </div>
                    </div>
                    <div class="glass-card p-3 mb-3">
                        <div class="section-title"><i class="bi bi-pencil-fill"></i> Update Progress</div>
                        <div class="row g-2">
                            <div class="col-md-4">
                                <label class="form-label">Current Page</label>
                                <input type="number" id="updatePage" class="form-control" value="{progress.get("current_page", 0)}" min="0" max="{progress.get("total_pages", 9999) or 9999}">
                            </div>
                            <div class="col-md-4">
                                <label class="form-label">Minutes Read</label>
                                <input type="number" id="updateMinutes" class="form-control" value="15" min="1">
                            </div>
                            <div class="col-md-4 d-flex align-items-end gap-1">
                                <button class="btn btn-primary" onclick="updateProgress()"><i class="bi bi-check"></i> Update</button>
                                <button class="btn btn-success" onclick="markAsFinished()"><i class="bi bi-check-all"></i> Finished</button>
                            </div>
                        </div>
                        <div class="mt-2">
                            <label class="form-label">Notes</label>
                            <textarea id="updateNotes" class="form-control" rows="2" placeholder="Your thoughts...">{h(progress.get("notes", ""))}</textarea>
                        </div>
                    </div>
                </div>
                <div class="col-lg-4">
                    <div class="glass-card p-3 mb-3">
                        <div class="section-title"><i class="bi bi-clock"></i> Reading Stats</div>
                        <div class="info-grid">
                            <div class="info-card"><div class="value">{progress.get("percentage", 0)}%</div><div class="label">Complete</div></div>
                            <div class="info-card"><div class="value">{progress.get("current_page", 0)}</div><div class="label">Current Page</div></div>
                            <div class="info-card"><div class="value">{progress.get("estimated_minutes_remaining", 0):.0f}m</div><div class="label">Left to Read</div></div>
                            <div class="info-card"><div class="value">{progress.get("time_spent_minutes", 0)}m</div><div class="label">Time Spent</div></div>
                        </div>
                    </div>
                    <div class="glass-card p-3">
                        <div class="section-title"><i class="bi bi-bookmark-fill text-warning"></i> Bookmarks</div>
                        {BM_HTML}
                        <hr style="border-color:var(--border);">
                        <div class="input-group input-group-sm">
                            <input type="number" id="newBookmarkPage" class="form-control" placeholder="Page #" min="1">
                            <button class="btn btn-primary btn-sm" onclick="addBookmark()"><i class="bi bi-plus"></i> Add</button>
                        </div>
                        <input type="text" id="newBookmarkNote" class="form-control form-control-sm mt-1" placeholder="Optional note...">
                    </div>
                </div>
            </div>
        </div>
        <script>
        function updateProgress(){{
            fetch('/api/reading-progress/{book_id}/update',{{
                method:'POST',
                headers:{{'Content-Type':'application/json'}},
                body:JSON.stringify({{
                    current_page:parseInt(document.getElementById(\"updatePage\").value),
                    time_spent_minutes:parseInt(document.getElementById(\"updateMinutes\").value)||0,
                    notes:document.getElementById(\"updateNotes\").value
                }})
            }}).then(r=>r.json()).then(d=>{{if(d.success){{showToast(d.message,'success');setTimeout(function(){{location.reload()}},1000)}}else{{showToast(d.error,'error')}}}})
        }}
        function markAsFinished(){{
            if(!confirm('Mark this book as finished?'))return;
            fetch('/api/reading-progress/{book_id}/finish',{{method:'POST'}}).then(r=>r.json()).then(d=>{{if(d.success){{showToast(d.message,'success');setTimeout(function(){{location.reload()}},1000)}}else{{showToast(d.error,'error')}}}})
        }}
        function addBookmark(){{
            var p=document.getElementById(\"newBookmarkPage\").value;
            var n=document.getElementById(\"newBookmarkNote\").value;
            if(!p){{showToast('Enter a page number','error');return}}
            fetch('/api/bookmarks/add',{{
                method:'POST',
                headers:{{'Content-Type':'application/json'}},
                body:JSON.stringify({{book_id:'{book_id}',page:parseInt(p),note:n}})
            }}).then(r=>r.json()).then(d=>{{if(d.success){{showToast(d.message,'success');setTimeout(function(){{location.reload()}},1000)}}else{{showToast(d.error,'error')}}}})
        }}
        function removeBookmark(bid){{
            if(!confirm('Remove bookmark?'))return;
            fetch('/api/bookmarks/'+bid+'/remove',{{method:'POST'}}).then(r=>r.json()).then(d=>{{if(d.success){{showToast(d.message,'success');setTimeout(function(){{location.reload()}},1000)}}else{{showToast(d.error,'error')}}}})
        }}
        </script>"""
        return render_page(f"Reading: {book.title}", CONTENT)

    @app.route("/reading-progress/history")
    @login_required
    def reading_progress_history():
        uid = session["user_id"]
        rl = _progress.get_user_reading_list(uid)
        all_books = rl.get("currently_reading", []) + rl.get("finished", []) + rl.get("on_hold", [])

        ROWS = ""
        for b in all_books:
            cc = cat_color(b.get("book_category", ""))
            pct = b.get("percentage", 0)
            status_badge = (
                '<span class="badge bg-success">✅ Finished</span>'
                if b.get("finished")
                else (
                    '<span class="badge bg-primary">📖 Reading</span>'
                    if b.get("current_page", 0) > 0
                    else '<span class="badge bg-secondary">⏸️ On Hold</span>'
                )
            )
            ROWS += f"""
            <tr>
                <td><a href="/reading-progress/{h(b["book_id"])}" class="fw-bold text-decoration-none" style="color:var(--text);">{h(b.get("book_title", ""))[:50]}</a></td>
                <td><span class="badge" style="background:{cc}20;color:{cc};">{h(b.get("book_category", ""))}</span></td>
                <td>{status_badge}</td>
                <td>
                    <div class="d-flex align-items-center gap-2">
                        <div class="progress-thin flex-grow-1"><div class="bar" style="width:{pct}%;background:var(--primary);"></div></div>
                        <small class="fw-bold">{pct}%</small>
                    </div>
                </td>
                <td>{b.get("current_page", 0)}/{b.get("total_pages", 0) or "?"}</td>
                <td>{b.get("time_spent_minutes", 0)}m</td>
            </tr>"""
        if not ROWS:
            ROWS = '<tr><td colspan="6" class="text-center text-muted py-4">No reading history yet.</td></tr>'

        CONTENT = f"""
        <div class="animate-in">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h4 class="fw-bold mb-0"><i class="bi bi-clock-history me-2 text-info"></i>Reading History</h4>
                <a href="/reading-progress" class="btn btn-outline btn-sm"><i class="bi bi-arrow-left"></i> Back</a>
            </div>
            <div class="glass-card p-3">
                <div class="table-responsive"><table class="table table-hover">
                    <thead><tr><th>Book</th><th>Category</th><th>Status</th><th>Progress</th><th>Pages</th><th>Time</th></tr></thead>
                    <tbody>{ROWS}</tbody>
                </table></div>
            </div>
        </div>"""
        return render_page("Reading History", CONTENT)

    # ── Reading Progress API ──

    @app.route("/api/reading-progress/<book_id>/update", methods=["POST"])
    @login_required
    def api_update_reading_progress(book_id):
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg, progress = _progress.update_progress(
            uid,
            book_id,
            current_page=data.get("current_page"),
            time_spent_minutes=data.get("time_spent_minutes"),
            notes=data.get("notes"),
            finished=data.get("finished"),
        )
        return jsonify({"success": ok, "message": msg, "progress": progress})

    @app.route("/api/reading-progress/<book_id>/finish", methods=["POST"])
    @login_required
    def api_finish_reading(book_id):
        uid = session["user_id"]
        ok, msg, progress = _progress.mark_as_finished(uid, book_id)
        # Also update reading challenge
        try:
            _challenge.set_goal(
                uid,
                datetime.now().year,
                _challenge.get_goal(uid, datetime.now().year).get("goal", 0),
            )
        except Exception:
            pass
        return jsonify({"success": ok, "message": msg, "progress": progress})

    @app.route("/api/reading-progress/<book_id>")
    @login_required
    def api_get_progress(book_id):
        uid = session["user_id"]
        return jsonify(_progress.get_progress(uid, book_id))

    @app.route("/api/reading-progress/stats")
    @login_required
    def api_reading_progress_stats():
        uid = session["user_id"]
        rl = _progress.get_user_reading_list(uid)
        stats = _progress.get_reading_stats(uid)
        return jsonify(
            {
                "currently_reading": len(rl.get("currently_reading", [])),
                "finished": len(rl.get("finished", [])),
                "completed": stats.get("books_finished", 0),
                "total_pages": stats.get("total_pages_read", 0),
                "total_time_minutes": stats.get("total_time_spent_minutes", 0),
                "completion_rate": stats.get("completion_rate", 0),
            }
        )

    # ── Bookmarks API ──

    @app.route("/api/bookmarks")
    @login_required
    def api_get_bookmarks():
        uid = session["user_id"]
        return jsonify({"bookmarks": _progress.get_user_bookmarks(uid)})

    @app.route("/api/bookmarks/add", methods=["POST"])
    @login_required
    def api_add_bookmark():
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg, bm = _progress.add_bookmark(
            uid, data.get("book_id", ""), int(data.get("page", 1)), data.get("note", "")
        )
        return jsonify({"success": ok, "message": msg, "bookmark": bm})

    @app.route("/api/bookmarks/<bookmark_id>/remove", methods=["POST"])
    @login_required
    def api_remove_bookmark(bookmark_id):
        uid = session["user_id"]
        ok, msg = _progress.remove_bookmark(bookmark_id, uid)
        return jsonify({"success": ok, "message": msg})

    # ═══════════════════════════════════════════════════════════
    # 4. WISHLIST / SUGGESTIONS PAGES
    # ═══════════════════════════════════════════════════════════

    @app.route("/wishlist")
    @login_required
    def wishlist_page():
        uid = session["user_id"]
        status = request.args.get("status", "")
        sort_by = request.args.get("sort", "score")
        page = max(1, int(request.args.get("page", 1)))
        suggestions, total = _wishlist.get_suggestions(status=status, page=page, sort_by=sort_by)
        user_votes = {}  # Track user's votes on each suggestion
        for s in suggestions:
            if uid in s.get("upvotes", []):
                user_votes[s["suggestion_id"]] = "up"
            elif uid in s.get("downvotes", []):
                user_votes[s["suggestion_id"]] = "down"
            else:
                user_votes[s["suggestion_id"]] = "none"

        stats = _wishlist.get_suggestion_stats()
        trending = _wishlist.get_trending_suggestions(5)

        STAT_BAR = f"""
        <div class="stats-bar mb-3 animate-in">
            <div class="stat-item"><div class="num">{stats["total"]}</div><div class="desc">Total</div></div>
            <div class="stat-item"><div class="num text-warning">{stats["pending"]}</div><div class="desc">Pending</div></div>
            <div class="stat-item"><div class="num text-success">{stats["approved"]}</div><div class="desc">Approved</div></div>
            <div class="stat-item"><div class="num text-danger">{stats["rejected"]}</div><div class="desc">Rejected</div></div>
            <div class="stat-item"><div class="num">{stats["unique_suggesters"]}</div><div class="desc">Suggesters</div></div>
        </div>"""

        TRENDING_HTML = ""
        for s in trending[:5]:
            TRENDING_HTML += f"""
            <div class="d-flex align-items-center gap-2 mb-2 p-1" style="border-bottom:1px solid var(--border);">
                <div style="width:24px;height:24px;border-radius:6px;background:#f59e0b20;display:flex;align-items:center;justify-content:center;flex-shrink:0;"><i class="bi bi-fire" style="color:#f59e0b;font-size:.6rem;"></i></div>
                <div class="flex-grow-1" style="min-width:0;"><div class="fw-bold small">{h(s["title"])[:50]}</div><small class="text-muted">{s.get("author", "")[:30]}</small></div>
                <span class="badge bg-warning text-dark">+{len(s.get("upvotes", []))}</span>
            </div>"""
        if not TRENDING_HTML:
            TRENDING_HTML = (
                '<div class="text-center text-muted small py-3">No trending suggestions.</div>'
            )

        SUGGESTIONS_HTML = ""
        for s in suggestions:
            score = len(s.get("upvotes", [])) - len(s.get("downvotes", []))
            status_badges = {
                "pending": '<span class="badge bg-warning text-dark">⏳ Pending</span>',
                "approved": '<span class="badge bg-success">✅ Approved</span>',
                "rejected": '<span class="badge bg-danger">❌ Rejected</span>',
                "purchased": '<span class="badge bg-info">📦 Purchased</span>',
            }
            sb = status_badges.get(s["status"], "")
            uv = user_votes.get(s["suggestion_id"], "none")
            up_class = "upvoted" if uv == "up" else ""
            down_class = "downvoted" if uv == "down" else ""
            reason_html = (
                f'<p class="small text-muted mt-1 mb-0">{h(s.get("reason", ""))}</p>'
                if s.get("reason")
                else ""
            )
            comments_badge = (
                f'<span class="text-info">\U0001f4ac {len(s.get("comments", []))}</span>'
                if s.get("comments")
                else ""
            )
            admin_html = (
                f'<div class="mt-2 p-2" style="background:rgba(79,70,229,.04);border-radius:8px;">'
                f'<small><strong>Admin:</strong> {h(s.get("admin_notes", ""))}</small></div>'
                if s.get("admin_notes")
                else ""
            )
            mod_buttons = ""
            if session.get("role") == "admin" and s["status"] == "pending":
                _sid = _js_str(s["suggestion_id"])
                mod_buttons = (
                    f'<button class="btn btn-sm btn-success" onclick="moderateSuggestion(\'{_sid}\',\'approved\')"><i class="bi bi-check-lg"></i> Approve</button>'
                    f'<button class="btn btn-sm btn-danger" onclick="moderateSuggestion(\'{_sid}\',\'rejected\')"><i class="bi bi-x-lg"></i> Reject</button>'
                )
            SUGGESTIONS_HTML += f"""
            <div class="glass-card p-3 mb-2">
                <div class="d-flex gap-3">
                    <div class="vote-column" style="min-width:40px;">
                        <button class="vote-btn {up_class}" onclick="voteSuggestion('{_js_str(s["suggestion_id"])}','up',this)"><i class="bi bi-arrow-up-short"></i></button>
                        <span class="vote-score {"positive" if score > 0 else "negative" if score < 0 else ""}">{score}</span>
                        <button class="vote-btn {down_class}" onclick="voteSuggestion('{_js_str(s["suggestion_id"])}','down',this)"><i class="bi bi-arrow-down-short"></i></button>
                    </div>
                    <div class="flex-grow-1" style="min-width:0;">
                        <div class="d-flex justify-content-between align-items-start">
                            <div>
                                <h6 class="fw-bold mb-0">{h(s["title"])}</h6>
                                <small class="text-muted">{h(s.get("author", "")) if s.get("author") else ""}</small>
                            </div>
                            {sb}
                        </div>
                        {reason_html}
                        <div class="d-flex gap-2 mt-2 align-items-center" style="font-size:.75rem;color:var(--text-muted);">
                            <span>👤 {h(s.get("suggester_name", ""))}</span>
                            {('<span>🔖 ' + h(s.get('category', '')) + '</span>') if s.get('category') else ''}
                            <span>📅 {s.get("created_at", "")[:10]}</span>
                            {comments_badge}
                        </div>
                        {admin_html}
                        <div class="d-flex gap-1 mt-2">
                            {mod_buttons}
                            <button class="btn btn-sm btn-outline" onclick="showSuggestionComments(\'{_js_str(s["suggestion_id"])}\')"><i class="bi bi-chat"></i> Comment</button>
                        </div>
                    </div>
                </div>
            </div>"""
        if not SUGGESTIONS_HTML:
            SUGGESTIONS_HTML = """
            <div class="empty-state empty-state-variant">
                <div class="empty-icon"><i class="bi bi-lightbulb"></i></div>
                <div class="empty-title">No suggestions yet</div>
                <div class="empty-desc">Be the first to suggest a book for the library!</div>
                <button class="empty-cta" onclick="showSuggestForm()"><i class="bi bi-plus-lg"></i> Suggest a Book</button>
            </div>"""

        STATUS_TABS = f"""
        <div class="d-flex border-bottom mb-3 gap-2">
            <a href="/wishlist?status=" class="feed-tab {"active" if not status else ""}">All</a>
            <a href="/wishlist?status=pending" class="feed-tab {"active" if status == "pending" else ""}">⏳ Pending</a>
            <a href="/wishlist?status=approved" class="feed-tab {"active" if status == "approved" else ""}">✅ Approved</a>
            <a href="/wishlist?status=rejected" class="feed-tab {"active" if status == "rejected" else ""}">❌ Rejected</a>
        </div>"""

        CONTENT = f"""
        <div class="animate-in">
            <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
                <h4 class="fw-bold mb-0"><i class="bi bi-lightbulb-fill me-2 text-warning"></i>Book Wishlist & Suggestions</h4>
                <button class="btn btn-primary btn-sm" onclick="showSuggestForm()"><i class="bi bi-plus-lg"></i> Suggest a Book</button>
            </div>
            {STAT_BAR}
            {STATUS_TABS}
            <div class="row">
                <div class="col-lg-9">{SUGGESTIONS_HTML}</div>
                <div class="col-lg-3">
                    <div class="glass-card p-3" style="position:sticky;top:4.5rem;">
                        <div class="section-title"><i class="bi bi-fire text-danger"></i> Trending Suggestions</div>
                        {TRENDING_HTML}
                    </div>
                </div>
            </div>
        </div>

        <!-- Suggest Modal -->
        <div class="modal fade" id="suggestModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content">
            <div class="modal-header"><h5 class="modal-title"><i class="bi bi-lightbulb text-warning me-1"></i> Suggest a Book</h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
            <div class="modal-body">
                <div class="mb-3"><label class="form-label">Book Title *</label><input type="text" id="suggestTitle" class="form-control" placeholder="e.g. The Great Gatsby" required></div>
                <div class="mb-3"><label class="form-label">Author</label><input type="text" id="suggestAuthor" class="form-control" placeholder="F. Scott Fitzgerald"></div>
                <div class="mb-3"><label class="form-label">Why should we add this?</label><textarea id="suggestReason" class="form-control" rows="3" placeholder="Tell us why this book should be in the library..."></textarea></div>
                <div class="row">
                    <div class="col-md-6 mb-3"><label class="form-label">ISBN</label><input type="text" id="suggestIsbn" class="form-control" placeholder="Optional"></div>
                    <div class="col-md-6 mb-3"><label class="form-label">Category</label><select id="suggestCategory" class="form-select"><option value="">Any</option>
                        {"".join(f'<option value="{c}">{c}</option>' for c in ["Fiction", "Non-Fiction", "Science", "History", "Biography", "Philosophy", "Technology", "Other"])}
                    </select></div>
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-outline" data-bs-dismiss="modal">Cancel</button>
                <button class="btn btn-primary" onclick="submitSuggestion()"><i class="bi bi-send"></i> Submit</button>
            </div>
        </div></div></div>

        <script>
        function showSuggestForm(){{var m=new bootstrap.Modal(document.getElementById(\"suggestModal\"));m.show()}}
        function submitSuggestion(){{
            var t=document.getElementById(\"suggestTitle\").value.trim();
            if(!t){{showToast('Enter a book title','error');return}}
            fetch('/api/wishlist/suggest',{{
                method:'POST',
                headers:{{'Content-Type':'application/json'}},
                body:JSON.stringify({{
                    title:t,
                    author:document.getElementById(\"suggestAuthor\").value.trim(),
                    reason:document.getElementById(\"suggestReason\").value.trim(),
                    isbn:document.getElementById(\"suggestIsbn\").value.trim(),
                    category:document.getElementById(\"suggestCategory\").value
                }})
            }}).then(r=>r.json()).then(d=>{{if(d.success){{showToast(d.message,'success');setTimeout(function(){{location.reload()}},1200)}}else{{showToast(d.error,'error')}}}})
        }}
        function voteSuggestion(sid,vote,btn){{
            fetch('/api/wishlist/'+sid+'/vote',{{
                method:'POST',
                headers:{{'Content-Type':'application/json'}},
                body:JSON.stringify({{vote:vote}})
            }}).then(r=>r.json()).then(d=>{{if(d.success){{showToast(d.message,'success');setTimeout(function(){{location.reload()}},1200)}}else{{showToast(d.error,'error')}}}})
        }}
        function moderateSuggestion(sid,status){{
            var notes=prompt('Add admin notes (optional):','');
            fetch('/api/wishlist/'+sid+'/moderate',{{
                method:'POST',
                headers:{{'Content-Type':'application/json'}},
                body:JSON.stringify({{status:status,admin_notes:notes||''}})
            }}).then(r=>r.json()).then(d=>{{if(d.success){{showToast(d.message,'success');setTimeout(function(){{location.reload()}},1200)}}else{{showToast(d.error,'error')}}}})
        }}
        function showSuggestionComments(sid){{
            var notes=prompt('Add a comment:','');
            if(!notes||!notes.trim())return;
            fetch('/api/wishlist/'+sid+'/comment',{{
                method:'POST',
                headers:{{'Content-Type':'application/json'}},
                body:JSON.stringify({{content:notes.trim()}})
            }}).then(r=>r.json()).then(d=>{{if(d.success){{showToast(d.message,'success');setTimeout(function(){{location.reload()}},1200)}}else{{showToast(d.error,'error')}}}})
        }}
        </script>"""
        return render_page("Wishlist", CONTENT)

    # ── Wishlist API ──

    @app.route("/api/wishlist/suggest", methods=["POST"])
    @login_required
    # Abuse ceiling: suggestion spam floods the moderation queue.
    @_rate_limit("10 per minute")
    def api_suggest_book():
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg, suggestion = _wishlist.add_suggestion(
            uid,
            data.get("title", ""),
            data.get("author", ""),
            data.get("reason", ""),
            data.get("isbn", ""),
            data.get("category", ""),
            data.get("url", ""),
        )
        # Gamification points
        try:
            from app.services.social.gamification import Gamification

            g = Gamification(_storage)
            g.add_points(uid, 5, "Suggested a book")
        except Exception:
            pass
        return jsonify({"success": ok, "message": msg, "suggestion": suggestion})

    @app.route("/api/wishlist/<suggestion_id>/vote", methods=["POST"])
    @login_required
    # Abuse ceiling: suggestion vote-stuffing (engagement manipulation).
    @_rate_limit("60 per minute")
    def api_vote_suggestion(suggestion_id):
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg, result = _wishlist.vote_suggestion(suggestion_id, uid, data.get("vote", "up"))
        return jsonify({"success": ok, "message": msg, **result})

    @app.route("/api/wishlist/<suggestion_id>/moderate", methods=["POST"])
    @login_required
    @admin_required
    # Defense in depth: admin moderation action — cap per IP well below the
    # global 200/min default.
    @_rate_limit("20 per minute")
    def api_moderate_suggestion(suggestion_id):
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg = _wishlist.moderate_suggestion(
            suggestion_id, uid, data.get("status", ""), data.get("admin_notes", "")
        )
        return jsonify({"success": ok, "message": msg})

    @app.route("/api/wishlist/<suggestion_id>/comment", methods=["POST"])
    @login_required
    # Abuse ceiling: comment spam on the shared surface.
    @_rate_limit("30 per minute")
    def api_suggestion_comment(suggestion_id):
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg = _wishlist.add_suggestion_comment(suggestion_id, uid, data.get("content", ""))
        return jsonify({"success": ok, "message": msg})

    @app.route("/api/wishlist/stats")
    @login_required
    def api_wishlist_stats():
        return jsonify(_wishlist.get_suggestion_stats())

    # ═══════════════════════════════════════════════════════════
    # 5. READING DIARY PAGES
    # ═══════════════════════════════════════════════════════════

    @app.route("/diary")
    @login_required
    def diary_page():
        uid = session["user_id"]
        page = max(1, int(request.args.get("page", 1)))
        entries, total = _diary.get_user_diary(uid, page=page)
        stats = _diary.get_stats(uid)

        # Stats overview
        avg_info = RATING_LABELS.get(
            stats.get("avg_rating_label", "timepass"), RATING_LABELS["timepass"]
        )
        ENTRY_CARDS = ""
        for e in entries:
            cc = cat_color(e.get("book_category", ""))
            cover = e.get("book_cover", "")
            cover_html = (
                f'<img src="{cover}" alt="" class="bt-diary-cover" loading="lazy" onerror="this.style.display=&#39;none&#39;">'
                if cover
                else ""
            )
            vibe_html = (
                "".join(
                    f'<a href="/explore/vibes/{h(t)}" class="bt-vibe-tag">{h(t)}</a>'
                    for t in e.get("vibe_tags", [])
                )
                if e.get("vibe_tags")
                else ""
            )
            spoiler_badge = (
                '<span class="badge bg-warning text-dark" style="font-size:.6rem;">⚠️ Spoiler</span>'
                if e.get("spoiler")
                else ""
            )
            reread_badge = (
                '<span class="badge bg-info" style="font-size:.6rem;">🔄 Reread</span>'
                if e.get("is_reread")
                else ""
            )

            ENTRY_CARDS += f"""
            <div class="bt-diary-entry" role="article">
                <div style="width:60px;flex-shrink:0;">{cover_html or f'<div style="width:60px;height:90px;border-radius:6px;background:linear-gradient(135deg,{cc},{cc}dd);display:flex;align-items:center;justify-content:center;"><i class="bi bi-book-fill" style="color:white;font-size:1.2rem;"></i></div>'}</div>
                <div class="bt-diary-body">
                    <div class="bt-diary-date">{e.get("date_read", "")[:10]}</div>
                    <a href="/books/{h(e["book_id"])}" class="bt-diary-book-title">{h(e.get("book_title", ""))}</a>
                    <div style="font-size:.75rem;color:var(--text-muted);">{h(e.get("book_author", ""))}</div>
                    <div class="d-flex align-items-center gap-2 mt-1 flex-wrap">
                        {e.get("rating_badge", "")}
                        {e.get("star_html", "")}
                        {spoiler_badge}
                        {reread_badge}
                    </div>
                    {f'<div class="bt-diary-text">{h(e.get("diary_text", ""))[:300]}</div>' if e.get("diary_text") else ""}
                    {f'<div class="d-flex gap-1 mt-1 flex-wrap">{vibe_html}</div>' if vibe_html else ""}
                    <div class="bt-diary-meta">
                        <a href="/diary/{e["id"]}" class="btn btn-sm btn-outline"><i class="bi bi-eye"></i> View</a>
                        <button class="btn btn-sm btn-outline" onclick="editDiaryEntry('{e["id"]}')"><i class="bi bi-pencil"></i></button>
                        <button class="btn btn-sm btn-outline" onclick="deleteDiaryEntry('{e["id"]}')"><i class="bi bi-trash"></i></button>
                    </div>
                </div>
            </div>"""

        if not ENTRY_CARDS:
            ENTRY_CARDS = """
            <div class="empty-state">
                <div class="empty-icon"><i class="bi bi-journal-text"></i></div>
                <h5>Your reading diary is empty</h5>
                <p class="text-muted">Start logging books you've read!</p>
                <button class="btn btn-primary" onclick="showLogForm()"><i class="bi bi-plus-lg"></i> Log a Book</button>
            </div>"""

        # HTML before JS (f-string for variable injection)
        _vibe_tags = stats.get("vibe_tags_cloud", [])
        if _vibe_tags:
            VIBE_TAGS_HTML = (
                '<div class="glass-card p-3"><div class="section-title">'
                '<i class="bi bi-tags-fill"></i> Vibe Tags</div>'
                '<div class="d-flex flex-wrap gap-1">'
                + "".join(
                    f'<span class="bt-vibe-tag">{h(t)} <small class="text-muted">({c})</small></span>'
                    for t, c in _vibe_tags
                )
                + "</div></div>"
            )
        else:
            VIBE_TAGS_HTML = ""
        _diary_html = f"""
        <div class="animate-in">
            <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
                <h4 class="fw-bold mb-0"><i class="bi bi-journal-text me-2 text-primary"></i>Reading Diary <span class="text-muted fw-normal" style="font-size:.9rem;">({stats["total_books"]} entries)</span></h4>
                <button class="btn btn-primary btn-sm" onclick="showLogForm()"><i class="bi bi-plus-lg"></i> Log a Book</button>
            </div>
            <div class="stats-bar mb-3 animate-in">
                <div class="stat-item"><div class="num">{stats["total_books"]}</div><div class="desc">Books Read</div></div>
                <div class="stat-item"><div class="num">{stats["reread_count"]}</div><div class="desc">Rereads</div></div>
                <div class="stat-item"><div class="num">{stats["total_pages_read"]}</div><div class="desc">Pages</div></div>
                <div class="stat-item"><div class="num" style="color:{avg_info["color"]};">{avg_info["emoji"]} {avg_info["label"]}</div><div class="desc">Avg Rating</div></div>
            </div>
            <div class="row">
                <div class="col-lg-8">
                    {ENTRY_CARDS}
                </div>
                <div class="col-lg-4">
                    <div class="glass-card p-3 mb-3">
                        <div class="section-title"><i class="bi bi-pie-chart-fill"></i> Rating Distribution</div>
                        {"".join(f'<div class="d-flex align-items-center gap-2 mb-1"><span class="small" style="min-width:80px;">{RATING_LABELS.get(l, {}).get("emoji", "")} {l}</span><div class="flex-grow-1"><div class="progress-thin"><div class="bar" style="width:{round(c / stats["total_books"] * 100) if stats["total_books"] else 0}%;background:{RATING_LABELS.get(l, {}).get("color", "#6b7280")};"></div></div></div><small class="fw-bold">{c}</small></div>' for l, c in sorted(stats.get("rating_distribution", {}).items(), key=lambda x: RATING_SCORES.get(x[0], 0), reverse=True))}
                    </div>
                    <div class="glass-card p-3 mb-3">
                        <div class="section-title"><i class="bi bi-grid-3x3-gap-fill"></i> Top Genres</div>
                        {"".join(f'<div class="d-flex justify-content-between mb-1"><span>{h(g)}</span><span class="fw-bold">{c}</span></div>' for g, c in stats.get("top_genres", []))}
                    </div>
                    {VIBE_TAGS_HTML}
                </div>
            </div>
        </div>
        """

        # Modal HTML and JavaScript (regular string, no f-string - avoids brace issues)
        _diary_js = """
        <!-- Log Read Modal -->
        <div class="modal fade" id="logModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content">
            <div class="modal-header"><h5 class="modal-title"><i class="bi bi-journal-plus text-primary me-1"></i> Log a Book</h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
            <div class="modal-body">
                <div class="mb-3"><label class="form-label">Book *</label>
                    <input type="text" id="logBookSearch" class="form-control" placeholder="Search for a book..." oninput="searchDiaryBooks(this.value)">
                    <div id="logBookResults" class="mt-1"></div>
                    <input type="hidden" id="logBookId">
                </div>
                <div class="mb-3"><label class="form-label">Date Read</label>
                    <input type="date" id="logDate" class="form-control"></div>
                <div class="mb-3"><label class="form-label">Rating *</label>
                    <div class="d-flex gap-2 flex-wrap" id="ratingButtons">
                        <button class="btn btn-sm btn-outline" onclick="selectRating('perfection',this)" id="rating-perfection" type="button">📖 Perfection</button>
                        <button class="btn btn-sm btn-primary" onclick="selectRating('worth_it',this)" id="rating-worth_it" type="button">☕ Worth the Read</button>
                        <button class="btn btn-sm btn-outline" onclick="selectRating('timepass',this)" id="rating-timepass" type="button">⌛ Timepass</button>
                        <button class="btn btn-sm btn-outline" onclick="selectRating('skip',this)" id="rating-skip" type="button">❌ Skip It</button>
                    </div>
                    <input type="hidden" id="logRating" value="worth_it">
                </div>
                <div class="mb-3"><label class="form-label">Star Rating (optional)</label>
                    <div class="d-flex gap-1" id="starSelector" style="font-size:1.5rem;cursor:pointer;">
                        <span class="star-opt" data-val="1" onclick="selectStar(1)" style="color:var(--text-dim);transition:all .2s;">☆</span>
                        <span class="star-opt" data-val="2" onclick="selectStar(2)" style="color:var(--text-dim);transition:all .2s;">☆</span>
                        <span class="star-opt" data-val="3" onclick="selectStar(3)" style="color:var(--text-dim);transition:all .2s;">☆</span>
                        <span class="star-opt" data-val="4" onclick="selectStar(4)" style="color:var(--text-dim);transition:all .2s;">☆</span>
                        <span class="star-opt" data-val="5" onclick="selectStar(5)" style="color:var(--text-dim);transition:all .2s;">☆</span>
                    </div>
                </div>
                <div class="mb-3"><label class="form-label">Review / Thoughts</label>
                    <textarea id="logText" class="form-control" rows="3" placeholder="What did you think of this book?"></textarea></div>
                <div class="mb-3">
                    <div class="form-check form-check-inline"><input type="checkbox" id="logReread" class="form-check-input"><label class="form-check-label small">Reread</label></div>
                    <div class="form-check form-check-inline"><input type="checkbox" id="logSpoiler" class="form-check-input"><label class="form-check-label small">Contains spoilers</label></div>
                </div>
                <div class="mb-3"><label class="form-label">Vibe Tags <small class="text-muted">(comma-separated, e.g. cozy)</small></label>
                    <input type="text" id="logVibes" class="form-control" placeholder="cozy, slow-burn, unputdownable"></div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-outline" data-bs-dismiss="modal">Cancel</button>
                <button class="btn btn-primary" onclick="submitDiaryLog()"><i class="bi bi-check-lg"></i> Log It</button>
            </div>
        </div></div></div>

        <script>
        var selectedDiaryBookId = null;
        var ratingLabel = "worth_it";
        var starRating = null;

        function searchDiaryBooks(q) {
            if(q.length<2){ document.getElementById("logBookResults").innerHTML="";return}
            fetch("/api/books?q="+encodeURIComponent(q)).then(function(r){return r.json()}).then(function(books){
                var c=document.getElementById("logBookResults");
                if(!books.length){c.innerHTML="<div class=\"text-muted small\">No books found</div>";return}
                c.innerHTML=books.slice(0,5).map(function(b){return "<div class=\"search-result-item\" style=\"cursor:pointer;padding:.3rem .5rem;\" onclick=\"selectDiaryBook(\'"+booktaleUtils.jsStr(b.book_id)+"\',\'"+booktaleUtils.jsStr(b.title)+"\')\">"+booktaleUtils.escapeHtml(b.title)+" <small class=\"text-muted\">"+booktaleUtils.escapeHtml(b.author)+"</small></div>"}).join("");
            });
        }

        function selectDiaryBook(bid, title) {
            selectedDiaryBookId = bid;
            document.getElementById("logBookSearch").value = title;
            document.getElementById("logBookId").value = bid;
            document.getElementById("logBookResults").innerHTML = "<small class=\"text-success\">Selected: "+booktaleUtils.escapeHtml(title)+"</small>";
        }

        function showLogForm() {var m=new bootstrap.Modal(document.getElementById("logModal")); m.show()}

        function submitDiaryLog() {
            if(!selectedDiaryBookId){showToast("Select a book","error");return}
            var data = {
                book_id: selectedDiaryBookId,
                date_read: document.getElementById("logDate").value,
                rating_label: document.getElementById("logRating").value,
                diary_text: document.getElementById("logText").value.trim(),
                is_reread: document.getElementById("logReread").checked,
                spoiler: document.getElementById("logSpoiler").checked,
                vibe_tags: document.getElementById("logVibes").value.split(",").map(function(t){return t.trim()}).filter(function(t){return t})
            };
            if(starRating) data.star_rating = starRating;
            fetch("/api/diary/log", {
                method:"POST",
                headers:{"Content-Type":"application/json"},
                body: JSON.stringify(data)
            }).then(function(r){return r.json()}).then(function(d){
                if(d.success){showToast(d.message,"success");setTimeout(function(){location.reload()},1000)}
                else{showToast(d.error,"error")}
            });
        }

        function deleteDiaryEntry(eid) {
            if(!confirm("Delete this entry?")) return;
            fetch("/api/diary/"+eid, {method:"DELETE"}).then(function(r){return r.json()}).then(function(d){
                if(d.success){showToast(d.message,"success");setTimeout(function(){location.reload()},1000)}
                else{showToast(d.error,"error")}
            });
        }

        function editDiaryEntry(eid) {
            window.location.href = "/diary/" + eid;
        }
        </script>"""

        CONTENT = _diary_html + _diary_js
        return render_page("Reading Diary", CONTENT)

    @app.route("/diary/<entry_id>")
    @login_required
    def diary_entry_page(entry_id):
        uid = session["user_id"]
        entry = _diary.get_entry(entry_id)
        if not entry:
            return render_page(
                "Not Found",
                '<div class="empty-state empty-state-variant"><div class="empty-icon"><i class="bi bi-journal-x"></i></div><div class="empty-title">Entry not found</div><div class="empty-desc">This diary entry may have been deleted.</div><a href="/diary" class="empty-cta"><i class="bi bi-arrow-left"></i> Back to Diary</a></div>',
            )

        if entry["user_id"] != uid:
            users = _storage.load_users()
            user = users.get(uid)
            if not user or user.role != "admin":
                return render_page(
                    "Forbidden",
                    '<div class="empty-state empty-state-variant"><div class="empty-icon"><i class="bi bi-shield-lock-fill"></i></div><div class="empty-title">Private Entry</div><div class="empty-desc">You can only view your own diary entries.</div></div>',
                )

        books = _storage.load_books()
        book = books.get(entry["book_id"])
        cover = book.cover_url or book.cover_image or "" if book else ""

        _ed = """
        <div class="animate-in">
            <div class="row">
                <div class="col-lg-8">
                    <div class="glass-card p-4">
                        <div class="d-flex gap-4">
                            <div style="width:120px;flex-shrink:0;">COVER_PLACEHOLDER</div>
                            <div class="flex-grow-1">
                                <div class="text-muted small mb-1"><i class="bi bi-calendar3"></i> Read on DATE_PLACEHOLDER</div>
                                <h4 class="fw-bold mb-1">BOOK_TITLE_PLACEHOLDER</h4>
                                <p class="text-muted mb-2">BOOK_AUTHOR_PLACEHOLDER</p>
                                <div class="d-flex gap-2 flex-wrap mb-2">
                                    RATING_BADGE_PLACEHOLDER STAR_HTML_PLACEHOLDER REREAD_PLACEHOLDER SPOILER_PLACEHOLDER
                                </div>
                            </div>
                        </div>
                        <hr style="border-color:var(--border);">
                        <div style="font-size:.95rem;line-height:1.7;">DIARY_TEXT_PLACEHOLDER</div>
                    </div>
                    <div class="d-flex gap-2 mt-3">
                        <button class="btn btn-primary" onclick="editDiaryEntry(ENTRY_ID_PLACEHOLDER)"><i class="bi bi-pencil"></i> Edit</button>
                        <button class="btn btn-danger" onclick="deleteDiaryEntry(ENTRY_ID_PLACEHOLDER)"><i class="bi bi-trash"></i> Delete</button>
                        <a href="/diary" class="btn btn-outline"><i class="bi bi-arrow-left"></i> Back to Diary</a>
                    </div>
                </div>
                <div class="col-lg-4">
                    <div class="glass-card p-3 mb-3">
                        <div class="section-title"><i class="bi bi-info-circle"></i> Details</div>
                        <div class="info-grid">
                            <div class="info-card"><div class="value">DATE_READ_PLACEHOLDER</div><div class="label">Date Read</div></div>
                            <div class="info-card"><div class="value">REREAD_YESNO_PLACEHOLDER</div><div class="label">Reread</div></div>
                            <div class="info-card"><div class="value">SPOILER_YESNO_PLACEHOLDER</div><div class="label">Spoiler</div></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>"""
        _ej = """
        <script>
        function deleteDiaryEntry(eid) {
            if(!confirm("Delete this entry?")) return;
            fetch("/api/diary/"+eid, {method:"DELETE"}).then(function(r){return r.json()}).then(function(d){
                if(d.success){showToast(d.message,"success");setTimeout(function(){window.location.href="/diary"},1000)}
                else{showToast(d.error,"error")}
            });
        }
        function editDiaryEntry(eid) {
            window.location.href = "/diary?edit="+eid;
        }
        </script>"""
        CONTENT = (
            _ed.replace("COVER_PLACEHOLDER", cover or "")
            .replace("DATE_PLACEHOLDER", str(entry.get("date_read", "")[:10]))
            .replace("BOOK_TITLE_PLACEHOLDER", h(book.title) if book else "Unknown Book")
            .replace("BOOK_AUTHOR_PLACEHOLDER", h(book.author) if book else "")
            .replace(
                "RATING_BADGE_PLACEHOLDER",
                rating_badge_html(entry.get("rating_label", "timepass")),
            )
            .replace("STAR_HTML_PLACEHOLDER", star_rating_html(entry.get("star_rating")))
            .replace(
                "REREAD_PLACEHOLDER",
                (
                    '<span class="badge bg-info" style="font-size:.6rem;">\U0001f504 Reread</span>'
                    if entry.get("is_reread")
                    else ""
                ),
            )
            .replace(
                "SPOILER_PLACEHOLDER",
                (
                    '<span class="badge bg-warning text-dark" style="font-size:.6rem;">\u26a0\ufe0f Spoiler</span>'
                    if entry.get("spoiler")
                    else ""
                ),
            )
            .replace("DIARY_TEXT_PLACEHOLDER", h(entry.get("diary_text", "")))
            .replace("ENTRY_ID_PLACEHOLDER", "\\'" + h(entry["id"]) + "\\'")
            .replace("DATE_READ_PLACEHOLDER", str(entry.get("date_read", "")[:10]))
            .replace("REREAD_YESNO_PLACEHOLDER", "Yes" if entry.get("is_reread") else "No")
            .replace("SPOILER_YESNO_PLACEHOLDER", "Yes" if entry.get("spoiler") else "No")
            + _ej
        )
        return render_page("Diary Entry", CONTENT)

    # ── Diary API Routes ──

    @app.route("/api/diary/log", methods=["POST"])
    @login_required
    def api_diary_log():
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg, entry = _diary.log_read(
            uid,
            data.get("book_id", ""),
            date_read=data.get("date_read", ""),
            rating_label=data.get("rating_label", "worth_it"),
            star_rating=data.get("star_rating"),
            diary_text=data.get("diary_text", ""),
            is_reread=data.get("is_reread", False),
            spoiler=data.get("spoiler", False),
            vibe_tags=data.get("vibe_tags", []),
        )
        return jsonify({"success": ok, "message": msg, "entry": entry})

    @app.route("/api/diary/<entry_id>", methods=["PUT", "DELETE"])
    @login_required
    def api_diary_entry(entry_id):
        uid = session["user_id"]
        if request.method == "DELETE":
            ok, msg = _diary.delete_entry(entry_id, uid)
            return jsonify({"success": ok, "message": msg})
        else:
            data = request.get_json() or {}
            ok, msg = _diary.update_entry(entry_id, uid, **data)
            return jsonify({"success": ok, "message": msg})

    @app.route("/api/diary/stats")
    @login_required
    def api_diary_stats():
        uid = session["user_id"]
        return jsonify(_diary.get_stats(uid))

    @app.route("/api/diary/book/<book_id>")
    @login_required
    def api_diary_book_logs(book_id):
        include_spoilers = request.args.get("spoilers", "0") == "1"
        return jsonify({"logs": _diary.get_book_logs(book_id, include_spoilers=include_spoilers)})

    # ═══════════════════════════════════════════════════════════
    # DASHBOARD WIDGET HELPERS
    # ═══════════════════════════════════════════════════════════

    def get_dashboard_widgets_html(user_id):
        """Get HTML snippets for dashboard widgets."""
        html = ""

        # Reading Challenge widget
        year = datetime.now().year
        goal = _challenge.get_goal(user_id, year)
        if goal.get("goal", 0) > 0:
            pct = goal.get("percentage", 0)
            html += f"""
            <div class="col-md-6 mb-3 animate-d4">
                <div class="glass-card p-3" onclick="window.location.href='/reading-challenge'" style="cursor:pointer;">
                    <div class="section-title"><i class="bi bi-trophy-fill text-warning"></i> {year} Reading Goal</div>
                    <div class="d-flex justify-content-between align-items-center">
                        <div><span class="fw-bold" style="font-size:1.3rem;">{goal.get("progress", 0)}</span><small class="text-muted">/{goal.get("goal", 0)} books</small></div>
                        <div class="text-end"><span class="fw-bold" style="font-size:1.3rem;color:var(--primary);">{pct}%</span></div>
                    </div>
                    <div class="progress-thin mt-2" style="height:8px;border-radius:4px;">
                        <div class="bar" style="width:{pct}%;background:{"var(--success)" if pct >= 100 else "var(--primary)"};height:8px;border-radius:4px;"></div>
                    </div>
                    <div class="d-flex justify-content-between mt-1"><small class="text-muted">📈 {goal.get("pace", 0)}/mo</small><small class="text-muted">⏱️ {goal.get("days_remaining", 0)}d left</small></div>
                </div>
            </div>"""

        # Currently Reading widget
        rl = _progress.get_user_reading_list(user_id)
        reading = rl.get("currently_reading", [])
        if reading:
            books_html = ""
            for b in reading[:3]:
                cc = cat_color(b.get("book_category", ""))
                pct = b.get("percentage", 0)
                books_html += f"""
                <div class="d-flex align-items-center gap-2 mb-2">
                    <div style="width:32px;height:32px;border-radius:8px;background:{cc}20;display:flex;align-items:center;justify-content:center;flex-shrink:0;"><i class="bi bi-book-fill" style="color:{cc};"></i></div>
                    <div class="flex-grow-1" style="min-width:0;"><span class="fw-bold small">{h(b.get("book_title", ""))[:30]}</span>
                        <div class="progress-thin mt-1"><div class="bar" style="width:{pct}%;background:var(--primary);"></div></div></div>
                    <a href="/reading-progress/{h(b["book_id"])}" class="btn btn-sm btn-outline"><i class="bi bi-arrow-right"></i></a>
                </div>"""
            html += f"""
            <div class="col-md-6 mb-3 animate-d4">
                <div class="glass-card p-3" onclick="window.location.href='/reading-progress'" style="cursor:pointer;">
                    <div class="section-title"><i class="bi bi-bookmark-check-fill text-primary"></i> Currently Reading ({len(reading)})</div>
                    {books_html}
                    {f'<small class="text-muted">+{len(reading) - 3} more</small>' if len(reading) > 3 else ""}
                </div>
            </div>"""

        return html


# HTML Templates (same style as web_app.py / social_routes.py)


# ============================================================
# HTML Templates (minimal - main app templates handle the full layout)
# ============================================================

_BASE_HTML = """<!DOCTYPE html><html lang="en" data-theme="light">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{{ title }} - LibraryMS</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.2/font/bootstrap-icons.css">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root{--primary:#4f46e5;--bg:#f8fafc;--text:#0f172a;--text-muted:#64748b;--border:rgba(226,232,240,.8);--radius:16px;--font:Inter,sans-serif}
body{background:var(--bg);color:var(--text);font-family:var(--font);min-height:100vh}
.glass-card{background:rgba(255,255,255,.85);border:1px solid var(--border);border-radius:var(--radius);padding:1rem;margin-bottom:1rem}
.btn{border-radius:8px;font-weight:600;padding:.45rem 1.1rem;border:none;display:inline-block}
.btn-primary{background:linear-gradient(135deg,#4f46e5,#7c3aed);color:white}
.btn-outline{background:transparent;border:2px solid var(--border);color:var(--text)}
.btn-sm{padding:.3rem .8rem;font-size:.8rem}
.form-control,.form-select{border:2px solid var(--border);border-radius:8px;padding:.5rem .9rem;width:100%}
.form-label{font-weight:600;font-size:.75rem;color:var(--text-muted)}
.progress-thin{height:6px;border-radius:3px;background:var(--border);overflow:hidden}
.progress-thin .bar{height:100%;border-radius:3px;transition:width 1s}
.badge{border-radius:6px;padding:.3em .6em;font-weight:500;font-size:.75rem}
.section-title{font-size:.75rem;font-weight:700;text-transform:uppercase;color:var(--text-muted);margin-bottom:.8rem}
.stats-bar{display:flex;flex-wrap:wrap;gap:1rem;padding:1rem;background:rgba(255,255,255,.85);border-radius:var(--radius);border:1px solid var(--border)}
.stats-bar .stat-item{flex:1;min-width:80px}
.stats-bar .stat-item .num{font-size:1.3rem;font-weight:800}
.stats-bar .stat-item .desc{font-size:.7rem;color:var(--text-muted);text-transform:uppercase}
.info-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:.6rem}
.info-card{padding:.6rem;border-radius:8px;background:rgba(79,70,229,.04);border:1px solid var(--border)}
.info-card .value{font-size:1.1rem;font-weight:700}
.info-card .label{font-size:.6rem;color:var(--text-muted);text-transform:uppercase}
.vote-column{display:flex;flex-direction:column;align-items:center;gap:2px;min-width:36px}
.vote-btn{background:none;border:none;color:var(--text-muted);cursor:pointer;padding:2px 4px;border-radius:4px;font-size:1.1rem}
.vote-btn:hover{color:var(--primary)}
.vote-btn.upvoted{color:var(--primary)}
.vote-btn.downvoted{color:var(--danger)}
.vote-score{font-weight:700;font-size:.85rem;color:var(--text-muted)}
.vote-score.positive{color:var(--primary)}
.vote-score.negative{color:var(--danger)}
.chart-container{position:relative;height:220px;width:100%}
.empty-state{text-align:center;padding:3rem 1rem;color:var(--text-muted)}

.glass-card:hover{box-shadow:0 0 0 1px rgba(79,70,229,.25),0 12px 40px rgba(79,70,229,.08);transform:translateY(-3px)}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 8px 25px rgba(79,70,229,.4)}
.btn-outline:hover{border-color:#4f46e5;color:#4f46e5;background:#eef2ff;transform:translateY(-2px)}
.vote-btn:hover{background:rgba(79,70,229,.08);color:#4f46e5}
</style>
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-dark" style="background:linear-gradient(135deg,#4f46e5,#7c3aed);padding:.5rem 1rem;">
<div class="container">
<a class="navbar-brand fw-bold text-white" href="/">LibraryMS</a>
<button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#nNav"><span class="navbar-toggler-icon"></span></button>
<div class="collapse navbar-collapse" id="nNav">
<ul class="navbar-nav me-auto gap-1">
<li class="nav-item"><a class="nav-link text-white" href="/">Dashboard</a></li>
<li class="nav-item"><a class="nav-link text-white" href="/books">Books</a></li>
<li class="nav-item"><a class="nav-link text-white" href="/series">Series</a></li>
<li class="nav-item"><a class="nav-link text-white" href="/reading-challenge">Challenge</a></li>
<li class="nav-item"><a class="nav-link text-white" href="/reading-progress">Progress</a></li>
<li class="nav-item"><a class="nav-link text-white" href="/wishlist">Suggest</a></li>
<li class="nav-item"><a class="nav-link text-white" href="/feed">Feed</a></li>
</ul>
</div></div></nav>
<div class="container py-3">
"""

_FOOTER_HTML = """
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body></html>"""
