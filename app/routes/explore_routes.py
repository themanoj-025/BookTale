"""
explore_routes.py - Explore and Recommendations page routes.

Routes: /explore, /recommendations, /api/notifications/<id>/read, /api/notifications/read-all
"""

from datetime import datetime

from flask import jsonify, session

from app.models.book import CATEGORIES as BOOK_CATEGORIES
from app.routes.helpers import avatar_html, cat_color
from app.routes.page_state import (
    communities,
    h,
    login_required,
    notif_mgr,
    recommender,
    render_page,
    social,
    storage,
    make_rate_limit,
)


def init_explore_routes(app) -> None:
    """Register explore and recommendation routes on the Flask app."""

    _rate_limit = make_rate_limit(app)

    # ════════════════════════════════════════════════════════════════
    # 1. EXPLORE PAGE (/explore)
    # ════════════════════════════════════════════════════════════════

    @app.route("/explore")
    @login_required
    def explore_page() -> str:
        from app.routes.page_state import challenge as _challenge

        uid = session["user_id"]

        # Trending books (from recommender or storage)
        books_data = storage.load_books()
        all_books = [b for b in books_data.values() if not b.is_deleted]
        trending_books = sorted(
            all_books,
            key=lambda b: b.issue_count or b.average_rating or 0,
            reverse=True,
        )[:12]
        trending_html = ""
        for b in trending_books[:6]:
            cc = cat_color(b.category)
            avail = (
                '<span class="badge bg-success">Available</span>'
                if b.available_copies > 0
                else '<span class="badge bg-danger">Out</span>'
            )
            trending_html += f"""<div class="col-6 col-md-4 col-lg-2 mb-2">
                <div class="glass-card p-2 text-center h-100" onclick="window.location.href='/books/{b.book_id}'" style="cursor:pointer;">
                    <div style="width:40px;height:56px;border-radius:8px;background:linear-gradient(135deg,{cc},{cc}dd);display:flex;align-items:center;justify-content:center;margin:0 auto .3rem;">
                        <i class="bi bi-book-fill" style="color:white;font-size:.9rem;"></i></div>
                    <div style="font-size:.75rem;font-weight:600;line-height:1.2;">{h(b.title[:35])}</div>
                    <small style="font-size:.6rem;color:var(--text-muted);">{h(b.author[:25])}</small>
                    <div class="mt-1">{avail}</div>
                </div></div>"""
        if not trending_html:
            trending_html = (
                '<div class="col-12 text-center text-muted py-4">No books available yet.</div>'
            )

        # Readers to follow
        users_data = storage.load_users()
        following_set = set()
        if social:
            following_set = set(social.get_following(uid))
        suggested_users = []
        for u in users_data.values():
            if u.user_id != uid and u.user_id not in following_set:
                suggested_users.append(u)
        suggested_users = suggested_users[:6]
        readers_html = ""
        for u in suggested_users:
            av = avatar_html(u.name, 40)
            readers_html += f"""<div class="col-6 col-md-4 mb-2">
                <div class="glass-card p-3 text-center h-100">
                    {av}
                    <div class="fw-bold small mt-2">{h(u.name)}</div>
                    <small class="text-muted">@{h(u.user_id)}</small>
                    <button class="btn btn-primary btn-sm mt-2 w-100" onclick="followUser('{h(u.user_id)}',this)"><i class="bi bi-person-plus"></i> Follow</button>
                </div></div>"""
        if not readers_html:
            readers_html = '<div class="col-12 text-center text-muted py-4">No readers to suggest right now.</div>'

        # Trending hashtags
        hashtag_html = ""
        if social:
            try:
                tags = social.get_trending_hashtags(8)
                for tag in tags:
                    if isinstance(tag, dict):
                        tag = tag.get("tag", "")
                    hashtag_html += (
                        '<a href="/search?tag={}" class="btn btn-outline btn-sm mb-1" style="border-radius:50px;">#{}</a> '.format(h(tag.strip("#")), h(tag.strip("#")))
                    )
            except (AttributeError, TypeError, KeyError):
                pass
        if not hashtag_html:
            hashtag_html = '<a href="/search?tag=fantasy" class="btn btn-outline btn-sm mb-1" style="border-radius:50px;">#fantasy</a> <a href="/search?tag=scifi" class="btn btn-outline btn-sm mb-1" style="border-radius:50px;">#scifi</a> <a href="/search?tag=romance" class="btn btn-outline btn-sm mb-1" style="border-radius:50px;">#romance</a>'

        # Popular clubs
        clubs_html = ""
        if communities:
            try:
                clubs_data, _ = communities.get_clubs(page=1)
                for c in clubs_data[:3]:
                    clubs_html += """<div class="col-md-4 mb-2">
                        <div class="glass-card p-3 h-100" onclick="window.location.href='/clubs/{}'" style="cursor:pointer;">
                            <div class="fw-bold small">{}</div>
                            <small class="text-muted">{} members</small>
                            <div style="font-size:.75rem;color:var(--text-muted);margin-top:.3rem;">{}</div>
                        </div></div>""".format(
                        h(c["club_id"]),
                        h(c["name"]),
                        len(c.get("members", [])),
                        h(c.get("category", "General")),
                    )
            except (AttributeError, TypeError, KeyError):
                pass
        if not clubs_html:
            clubs_html = '<div class="col-12 text-center text-muted py-3">No clubs yet. Create the first one!</div>'

        # For You (personalized recommendations)
        for_you_html = ""
        try:
            recs = recommender.recommend_for_user(uid, top_n=4) if recommender else []
            for r in recs:
                cc = cat_color(r.get("category", ""))
                reason = h(r.get("reason", "Recommended"))[:60]
                for_you_html += """<div class="col-md-3 col-6 mb-2">
                    <div class="glass-card p-2 text-center h-100" onclick="window.location.href='/books/{}'" style="cursor:pointer;">
                        <div style="position:relative;">
                            <div style="width:40px;height:56px;border-radius:8px;background:linear-gradient(135deg,{},{}dd);display:flex;align-items:center;justify-content:center;margin:0 auto .3rem;">
                                <i class="bi bi-book-fill" style="color:white;font-size:.9rem;"></i></div>
                            <span class="badge bg-warning text-dark" style="position:absolute;top:-4px;right:10px;font-size:.5rem;">AI</span>
                        </div>
                        <div style="font-size:.7rem;font-weight:600;line-height:1.2;">{}</div>
                        <small style="font-size:.6rem;color:var(--text-muted);">{}</small>
                        <div style="font-size:.55rem;color:var(--text-muted);margin-top:.2rem;">{}</div>
                    </div></div>""".format(
                    h(r.get("book_id", "")),
                    cc,
                    cc,
                    h(r.get("title", "")[:35]),
                    h(r.get("author", "")[:20]),
                    reason,
                )
        except (AttributeError, TypeError, KeyError):
            pass

        # Challenge widget
        challenge_html = ""
        try:
            year = datetime.now().year
            goal = _challenge.get_goal(uid, year) if _challenge else {}
            if goal.get("goal", 0) > 0:
                pct = goal.get("percentage", 0)
                challenge_html = """<div class="glass-card p-3">
                    <div class="section-title"><i class="bi bi-trophy-fill text-warning"></i> Community Challenge %d</div>
                    <div class="d-flex align-items-center gap-3">
                        <div class="progress-thin flex-grow-1" style="height:10px;">
                            <div class="bar" style="width:%d%%;background:linear-gradient(90deg,var(--primary),#a855f7);height:10px;border-radius:5px;"></div>
                        </div>
                        <span class="fw-bold">%d%%</span>
                    </div>
                    <div class="d-flex justify-content-between mt-1"><small class="text-muted">%d / %d books</small><a href="/reading-challenge" class="btn btn-primary btn-sm">View</a></div>
                </div>""" % (
                    year,
                    pct,
                    pct,
                    goal.get("progress", 0),
                    goal.get("goal", 0),
                )
        except (AttributeError, TypeError, KeyError):
            pass
        if not challenge_html:
            challenge_html = """<div class="glass-card p-3">
                <div class="section-title"><i class="bi bi-trophy-fill text-muted"></i> Community Challenge</div>
                <p class="text-muted small mb-0">Set a reading goal to track your progress.</p>
                <a href="/reading-challenge" class="btn btn-primary btn-sm mt-2">Set Goal</a>
            </div>"""

        CONTENT = """<div class="animate-in">
    <style>
    .explore-hero{background:linear-gradient(135deg,var(--primary),#a855f7);border-radius:var(--radius);padding:2rem;margin-bottom:1.5rem;position:relative;overflow:hidden}
    .explore-hero::before{content:'';position:absolute;inset:0;background:radial-gradient(circle at 80% 20%,rgba(255,255,255,.1) 0%,transparent 60%)}
    .explore-hero h1{color:white;font-size:1.5rem;font-weight:800;margin-bottom:.3rem}
    .explore-hero p{color:rgba(255,255,255,.7);font-size:.85rem;margin-bottom:1rem}
    .explore-hero .search-input{background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.2);border-radius:12px;padding:.7rem 1rem;color:white;width:100%;max-width:500px;font-size:.9rem}
    .explore-hero .search-input::placeholder{color:rgba(255,255,255,.5)}
    </style>

    <div class="explore-hero">
        <h1><i class="bi bi-compass-fill me-2"></i>Discover Great Reads</h1>
        <p>Find your next favorite book, connect with readers, and join the conversation.</p>
        <div class="d-flex gap-2 flex-wrap">
            <input type="text" class="search-input" placeholder="Search books, readers, authors, topics..." onkeydown="if(event.key==='Enter'){var q=this.value.trim();if(q)window.location.href='/search?q='+encodeURIComponent(q)}">
            <button class="btn btn-primary" onclick="var inp=this.parentElement.querySelector('input');if(inp.value.trim())window.location.href='/search?q='+encodeURIComponent(inp.value.trim())" style="background:white;color:var(--primary);border:none;"><i class="bi bi-search"></i> Search</button>
        </div>
    </div>

    <div class="mb-3">
        <div class="section-title"><i class="bi bi-fire text-danger me-1"></i> Trending This Week</div>
        <div class="row g-2">TRENDING_HTML</div>
    </div>

    <div class="mb-3">
        <div class="section-title"><i class="bi bi-stars me-1" style="color:var(--primary);"></i> Recommended For You</div>
        <p class="text-muted small mb-2" style="margin-top:-.3rem;">Based on your reading history</p>
        <div class="row g-2">FOR_YOU_HTML</div>
    </div>

    <div class="row g-3">
        <div class="col-lg-8">
            <div class="mb-3">
                <div class="section-title"><i class="bi bi-people-fill me-1" style="color:var(--success);"></i> Readers to Follow</div>
                <div class="row g-2">READERS_HTML</div>
            </div>
            <div class="mb-3">
                <div class="section-title"><i class="bi bi-bookmark-fill me-1" style="color:#f59e0b;"></i> Popular Book Clubs</div>
                <div class="row g-2">CLUBS_HTML</div>
            </div>
        </div>
        <div class="col-lg-4">
            <div class="glass-card p-3 mb-3">
                <div class="section-title"><i class="bi bi-hash me-1" style="color:var(--info);"></i> Trending Topics</div>
                <div class="d-flex flex-wrap gap-1">HASHTAG_HTML</div>
            </div>
            CHALLENGE_HTML
        </div>
    </div>
</div>"""

        CONTENT = CONTENT.replace("TRENDING_HTML", trending_html)
        CONTENT = CONTENT.replace(
            "FOR_YOU_HTML",
            (
                for_you_html
                if for_you_html
                else '<div class="col-12 text-center text-muted small py-3">Keep reading to get personalized recommendations!</div>'
            ),
        )
        CONTENT = CONTENT.replace("READERS_HTML", readers_html)
        CONTENT = CONTENT.replace("CLUBS_HTML", clubs_html)
        CONTENT = CONTENT.replace("HASHTAG_HTML", hashtag_html)
        CONTENT = CONTENT.replace("CHALLENGE_HTML", challenge_html)

        CONTENT += """<script>
        function followUser(uid, btn) {
            fetch("/api/follow/" + uid, {method:"POST"})
                .then(function(r){ return r.json() })
                .then(function(d){
                    if(d.success){
                        btn.innerHTML = '<i class="bi bi-person-check"></i> Following';
                        btn.className = "btn btn-outline btn-sm mt-2 w-100";
                        showToast("Now following " + uid, "success");
                    } else {
                        showToast(d.error || "Failed", "error");
                    }
                }).catch(function(){ showToast("Network error", "error"); });
        }
        </script>"""

        return render_page("Explore", CONTENT)

    # ════════════════════════════════════════════════════════════════
    # 2. RECOMMENDATIONS PAGE (/recommendations)
    # ════════════════════════════════════════════════════════════════

    @app.route("/recommendations")
    @login_required
    def recommendations_page() -> str:
        import contextlib

        uid = session["user_id"]

        # Personalized
        for_you = []
        with contextlib.suppress(Exception):
            for_you = recommender.recommend_for_user(uid, top_n=6) if recommender else []

        def render_book_grid(books, cols=6, show_ai=False):
            if not books:
                return (
                    '<div class="text-center text-muted small py-3">No recommendations yet.</div>'
                )
            html = ""
            for r in books:
                cc = cat_color(r.get("category", ""))
                bid = r.get("book_id", "")
                title = r.get("title", "")[:35]
                author = r.get("author", "")[:20]
                ai_badge = (
                    '<span class="badge bg-warning text-dark" style="position:absolute;top:-4px;right:5px;font-size:.5rem;">AI</span>'
                    if show_ai
                    else ""
                )
                avail = r.get("available", 0)
                avail_badge = (
                    '<span class="badge bg-success" style="font-size:.5rem;">Avail</span>'
                    if avail > 0
                    else '<span class="badge bg-danger" style="font-size:.5rem;">Out</span>'
                )
                reason = h(r.get("reason", ""))[:40] if r.get("reason") else ""
                html += f"""<div class="col-md-3 col-6 mb-2">
                    <div class="glass-card p-2 text-center h-100" onclick="window.location.href='/books/{h(bid)}'" style="cursor:pointer;">
                        <div style="position:relative;">
                            <div style="width:40px;height:56px;border-radius:8px;background:linear-gradient(135deg,{cc},{cc}dd);display:flex;align-items:center;justify-content:center;margin:0 auto .3rem;">
                                <i class="bi bi-book-fill" style="color:white;font-size:.9rem;"></i></div>
                            {ai_badge}
                        </div>
                        <div style="font-size:.7rem;font-weight:600;line-height:1.2;">{h(title)}</div>
                        <small style="font-size:.6rem;color:var(--text-muted);">{h(author)}</small>
                        <div class="mt-1">{avail_badge}</div>
                        <div style="font-size:.5rem;color:var(--text-muted);margin-top:.2rem;">{reason}</div>
                    </div></div>"""
            return html

        for_you_html = render_book_grid(for_you, show_ai=True)

        # Trending
        trending = []
        with contextlib.suppress(Exception):
            trending = recommender.recommend_trending(top_n=8) if recommender else []
        trending_html = render_book_grid(trending, show_ai=False)

        # Bestsellers
        bestsellers = []
        with contextlib.suppress(Exception):
            bestsellers = recommender.recommend_all_time_best(top_n=8) if recommender else []
        bestsellers_html = render_book_grid(bestsellers)

        # By genre
        books_data = storage.load_books()
        all_books = [b for b in books_data.values() if not b.is_deleted]
        genre_html = ""
        for cat in list(BOOK_CATEGORIES)[:6]:
            cat_books = [b for b in all_books if b.category == cat][:4]
            if cat_books:
                html = ""
                for b in cat_books:
                    cc = cat_color(cat)
                    html += f"""<div class="col-3 mb-1">
                        <div class="glass-card p-1 text-center" onclick="window.location.href='/books/{h(b.book_id)}'" style="cursor:pointer;">
                            <div style="width:30px;height:40px;border-radius:4px;background:linear-gradient(135deg,{cc},{cc}dd);display:flex;align-items:center;justify-content:center;margin:0 auto .2rem;">
                                <i class="bi bi-book-fill" style="color:white;font-size:.6rem;"></i></div>
                            <div style="font-size:.55rem;font-weight:600;line-height:1.1;">{h(b.title[:20])}</div>
                        </div></div>"""
                genre_html += f"""<div class="glass-card p-3 mb-2">
                    <div class="section-title mb-2"><i class="bi bi-tag-fill" style="color:{cat_color(cat)};"></i> {h(cat)}</div>
                    <div class="row g-1">{html}</div>
                </div>"""

        if not genre_html:
            genre_html = (
                '<div class="text-center text-muted small py-3">No categories available.</div>'
            )

        CONTENT = """<div class="animate-in">
    <style>
    .rec-hero{background:linear-gradient(135deg,var(--primary),#a855f7);border-radius:var(--radius);padding:1.5rem;margin-bottom:1.5rem;color:white}
    .rec-hero h2{font-weight:800;font-size:1.3rem}
    .rec-hero p{opacity:.7;font-size:.85rem;margin-bottom:0}
    </style>

    <div class="rec-hero">
        <h2><i class="bi bi-stars me-2"></i>Book Recommendations</h2>
        <p>Discover books you will love — personalized recommendations and community insights.</p>
    </div>

    <div class="mb-3">
        <div class="section-title"><i class="bi bi-wand-fill me-1" style="color:#f59e0b;"></i> For You</div>
        <p class="text-muted small mb-2" style="margin-top:-.3rem;">Based on your reading history</p>
        <div class="row g-2">FOR_YOU_HTML</div>
    </div>

    <div class="mb-3">
        <div class="section-title"><i class="bi bi-fire text-danger me-1"></i> Trending This Month</div>
        <div class="row g-2">TRENDING_HTML</div>
    </div>

    <div class="mb-3">
        <div class="section-title"><i class="bi bi-trophy-fill me-1" style="color:#f59e0b;"></i> All-Time Bestsellers</div>
        <div class="row g-2">BESTSELLERS_HTML</div>
    </div>

    <div class="mb-3">
        <div class="section-title"><i class="bi bi-grid-3x3-gap-fill me-1" style="color:var(--success);"></i> Browse by Genre</div>
        GENRE_HTML
    </div>
</div>"""
        CONTENT = CONTENT.replace("FOR_YOU_HTML", for_you_html)
        CONTENT = CONTENT.replace("TRENDING_HTML", trending_html)
        CONTENT = CONTENT.replace("BESTSELLERS_HTML", bestsellers_html)
        CONTENT = CONTENT.replace("GENRE_HTML", genre_html)

        return render_page("Recommendations", CONTENT)

    # ════════════════════════════════════════════════════════════════
    # 3. NOTIFICATION API ENDPOINTS
    # ════════════════════════════════════════════════════════════════

    @app.route("/api/notifications/<notif_id>/read", methods=["POST"])
    @login_required
    def api_notification_read(notif_id) -> Response:
        if notif_mgr:
            notif_mgr.mark_as_read(notif_id)
        return jsonify({"success": True})

    @app.route("/api/notifications/read-all", methods=["POST"])
    @login_required
    def api_notifications_read_all() -> Response:
        uid = session["user_id"]
        if notif_mgr:
            notif_mgr.mark_all_read(uid)
        notif = notif_mgr.get_notifications(uid) if notif_mgr else []
        unread = sum(1 for n in notif if not n.get("read"))
        return jsonify({"success": True, "unread_count": unread})

    return app
