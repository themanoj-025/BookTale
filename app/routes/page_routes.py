"""
page_routes.py - Missing Page Routes for BookTale v5.0

Registeres routes: /explore, /notifications, /shelves, /recommendations,
/clubs, /reading-calendar, /analytics, /admin/users
"""

import html
import logging
import zlib
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from functools import wraps
from urllib.parse import quote

from flask import jsonify, redirect, render_template, request, session, url_for

from app.models.book import CATEGORIES as BOOK_CATEGORIES

_storage = None
_lib = None
_auth = None
_notif_mgr = None
_social = None
_review_mgr = None
_recommender = None
_book_lists = None
_communities = None
_gamification = None
_series_mgr = None
_challenge = None
_reading_progress = None
_wishlist = None
_diary_mgr = None

logger = logging.getLogger(__name__)


def h(text):
    return html.escape(str(text))


def _library_stats():
    """Calculate library-wide statistics for dashboard, reports, and admin pages."""
    if not _storage:
        return {}
    books = _storage.load_books()
    users = _storage.load_users()
    txns = _storage.load_transactions()
    all_books = [b for b in books.values() if not b.is_deleted]
    now = datetime.now()
    tms = datetime(now.year, now.month, 1)
    total_books = len(all_books)
    total_copies = sum(b.total_copies for b in all_books)
    avail_copies = sum(b.available_copies for b in all_books)
    avail_rate = (avail_copies / total_copies * 100) if total_copies else 0
    new_books_month = sum(1 for b in all_books if datetime.fromisoformat(b.added_on) >= tms)
    total_users = len(users)
    active_users = sum(1 for u in users.values() if u.membership_status == "Active")
    blocked_users = sum(1 for u in users.values() if u.membership_status == "Blocked")
    new_users_month = sum(
        1
        for u in users.values()
        if hasattr(u, "added_on") and u.added_on and datetime.fromisoformat(u.added_on) >= tms
    )
    issues = [t for t in txns if t["type"] == "issue"]
    active_issues = [t for t in issues if t.get("return_date") is None]
    total_txns = len(txns)
    month_txns = sum(1 for t in txns if datetime.fromisoformat(t.get("issue_date", "")) >= tms)
    unique_borrowers = len(set(t["user_id"] for t in issues))
    fines = _storage.load_fines()
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


def avatar_html(name, size=32):
    parts = name.strip().split()
    if not parts:
        initials = "?"
    elif len(parts) >= 2:
        initials = (parts[0][0] + parts[-1][0]).upper()
    else:
        initials = parts[0][:2].upper()
    clrs = [
        "#4f46e5",
        "#059669",
        "#d97706",
        "#dc2626",
        "#0891b2",
        "#7c3aed",
        "#db2777",
        "#ca8a04",
    ]
    c = clrs[zlib.crc32(str(name).encode("utf-8")) % len(clrs)]
    return (
        '<div class="avatar" style="width:%dpx;height:%dpx;background:%s20;color:%s;font-size:%dpx;font-weight:700;border-radius:50%%;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;" title="%s">%s</div>'
        % (size, size, c, c, size // 2, h(name), h(initials))
    )


def time_ago(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str)
        now = datetime.now()
        diff = now - dt
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return "just now"
        minutes = seconds // 60
        if minutes < 60:
            return "%dm ago" % minutes
        hours = minutes // 60
        if hours < 24:
            return "%dh ago" % hours
        days = hours // 24
        if days < 7:
            return "%dd ago" % days
        weeks = days // 7
        if weeks < 4:
            return "%dw ago" % weeks
        months = days // 30
        if months < 12:
            return "%dmo ago" % months
        years = days // 365
        return "%dy ago" % years
    except Exception:
        return iso_str[:10] if iso_str else ""


def render_page(title, content, **kw):
    user = get_current_user()
    return render_template(
        "base.html",
        title=title,
        content=content,
        session=session,
        notif_count=_notif_mgr.get_unread_count(user.user_id) if user else 0,
        **kw,
    )


def get_current_user():
    if "user_id" not in session:
        return None
    return _storage.load_users().get(session["user_id"])


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
            return render_page(
                "Forbidden",
                """<div class="text-center py-5"><div style="font-size:4rem;margin-bottom:1rem;">🔒</div><h3>Admin Access Required</h3><p class="text-muted">This page requires admin privileges.</p></div>""",
            )
        return f(*a, **k)

    return d


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
):
    global _storage, _lib, _auth, _notif_mgr, _social, _review_mgr, _recommender
    global _book_lists, _communities, _gamification, _series_mgr, _challenge
    global _reading_progress, _wishlist, _diary_mgr

    _storage = storage
    _lib = lib
    _auth = auth
    _notif_mgr = notif_mgr
    _social = social
    _review_mgr = review_mgr
    _recommender = recommender
    _book_lists = book_lists
    _communities = communities
    _gamification = gamification
    _series_mgr = series_mgr
    _challenge = challenge
    _reading_progress = reading_progress
    _wishlist = wishlist
    _diary_mgr = diary_mgr

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

    # ════════════════════════════════════════════════════════════════
    # 1. EXPLORE PAGE (/explore)
    # ════════════════════════════════════════════════════════════════

    @app.route("/explore")
    @login_required
    def explore_page():
        uid = session["user_id"]

        # Trending books (from recommender or storage)
        books_data = _storage.load_books()
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
            trending_html += """<div class="col-6 col-md-4 col-lg-2 mb-2">
                <div class="glass-card p-2 text-center h-100" onclick="window.location.href='/books/%s'" style="cursor:pointer;">
                    <div style="width:40px;height:56px;border-radius:8px;background:linear-gradient(135deg,%s,%sdd);display:flex;align-items:center;justify-content:center;margin:0 auto .3rem;">
                        <i class="bi bi-book-fill" style="color:white;font-size:.9rem;"></i></div>
                    <div style="font-size:.75rem;font-weight:600;line-height:1.2;">%s</div>
                    <small style="font-size:.6rem;color:var(--text-muted);">%s</small>
                    <div class="mt-1">%s</div>
                </div></div>""" % (
                b.book_id,
                cc,
                cc,
                h(b.title[:35]),
                h(b.author[:25]),
                avail,
            )
        if not trending_html:
            trending_html = (
                '<div class="col-12 text-center text-muted py-4">No books available yet.</div>'
            )

        # Readers to follow
        users_data = _storage.load_users()
        following_set = set()
        if _social:
            following_set = set(_social.get_following(uid))
        suggested_users = []
        for u in users_data.values():
            if u.user_id != uid and u.user_id not in following_set:
                suggested_users.append(u)
        suggested_users = suggested_users[:6]
        readers_html = ""
        for u in suggested_users:
            av = avatar_html(u.name, 40)
            readers_html += """<div class="col-6 col-md-4 mb-2">
                <div class="glass-card p-3 text-center h-100">
                    %s
                    <div class="fw-bold small mt-2">%s</div>
                    <small class="text-muted">@%s</small>
                    <button class="btn btn-primary btn-sm mt-2 w-100" onclick="followUser('%s',this)"><i class="bi bi-person-plus"></i> Follow</button>
                </div></div>""" % (
                av,
                h(u.name),
                h(u.user_id),
                h(u.user_id),
            )
        if not readers_html:
            readers_html = '<div class="col-12 text-center text-muted py-4">No readers to suggest right now.</div>'

        # Trending hashtags
        hashtag_html = ""
        if _social:
            try:
                tags = _social.get_trending_hashtags(8)
                for tag in tags:
                    if isinstance(tag, dict):
                        tag = tag.get("tag", "")
                    hashtag_html += (
                        '<a href="/search?tag=%s" class="btn btn-outline btn-sm mb-1" style="border-radius:50px;">#%s</a> '
                        % (h(tag.strip("#")), h(tag.strip("#")))
                    )
            except Exception:
                pass
        if not hashtag_html:
            hashtag_html = '<a href="/search?tag=fantasy" class="btn btn-outline btn-sm mb-1" style="border-radius:50px;">#fantasy</a> <a href="/search?tag=scifi" class="btn btn-outline btn-sm mb-1" style="border-radius:50px;">#scifi</a> <a href="/search?tag=romance" class="btn btn-outline btn-sm mb-1" style="border-radius:50px;">#romance</a>'

        # Popular clubs
        clubs_html = ""
        if _communities:
            try:
                clubs_data, _ = _communities.get_clubs(page=1)
                for c in clubs_data[:3]:
                    clubs_html += """<div class="col-md-4 mb-2">
                        <div class="glass-card p-3 h-100" onclick="window.location.href='/clubs/%s'" style="cursor:pointer;">
                            <div class="fw-bold small">%s</div>
                            <small class="text-muted">%s members</small>
                            <div style="font-size:.75rem;color:var(--text-muted);margin-top:.3rem;">%s</div>
                        </div></div>""" % (
                        h(c["club_id"]),
                        h(c["name"]),
                        len(c.get("members", [])),
                        h(c.get("category", "General")),
                    )
            except Exception:
                pass
        if not clubs_html:
            clubs_html = '<div class="col-12 text-center text-muted py-3">No clubs yet. Create the first one!</div>'

        # For You (personalized recommendations)
        for_you_html = ""
        try:
            recs = _recommender.recommend_for_user(uid, top_n=4) if _recommender else []
            for r in recs:
                cc = cat_color(r.get("category", ""))
                reason = h(r.get("reason", "Recommended"))[:60]
                for_you_html += """<div class="col-md-3 col-6 mb-2">
                    <div class="glass-card p-2 text-center h-100" onclick="window.location.href='/books/%s'" style="cursor:pointer;">
                        <div style="position:relative;">
                            <div style="width:40px;height:56px;border-radius:8px;background:linear-gradient(135deg,%s,%sdd);display:flex;align-items:center;justify-content:center;margin:0 auto .3rem;">
                                <i class="bi bi-book-fill" style="color:white;font-size:.9rem;"></i></div>
                            <span class="badge bg-warning text-dark" style="position:absolute;top:-4px;right:10px;font-size:.5rem;">AI</span>
                        </div>
                        <div style="font-size:.7rem;font-weight:600;line-height:1.2;">%s</div>
                        <small style="font-size:.6rem;color:var(--text-muted);">%s</small>
                        <div style="font-size:.55rem;color:var(--text-muted);margin-top:.2rem;">%s</div>
                    </div></div>""" % (
                    h(r.get("book_id", "")),
                    cc,
                    cc,
                    h(r.get("title", "")[:35]),
                    h(r.get("author", "")[:20]),
                    reason,
                )
        except Exception:
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
        except Exception:
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
    # 2. NOTIFICATIONS PAGE (/notifications)
    # ════════════════════════════════════════════════════════════════

    @app.route("/notifications")
    @login_required
    def notifications_page():
        uid = session["user_id"]
        notifs = _notif_mgr.get_notifications(uid) if _notif_mgr else []
        total = len(notifs)
        unread = sum(1 for n in notifs if not n.get("read"))
        read_count = total - unread

        # Group by type
        by_type = Counter(n.get("type", "general") for n in notifs)

        # Group by date
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        groups = {"Today": [], "Yesterday": [], "This Week": [], "Earlier": []}
        for n in notifs:
            try:
                nd = datetime.fromisoformat(n["created_at"]).date()
                if nd == today:
                    groups["Today"].append(n)
                elif nd == yesterday:
                    groups["Yesterday"].append(n)
                elif nd > today - timedelta(days=7):
                    groups["This Week"].append(n)
                else:
                    groups["Earlier"].append(n)
            except:
                groups["Earlier"].append(n)

        notif_icons = {
            "follow": "person-plus-fill",
            "like": "heart-fill",
            "comment": "chat-dots-fill",
            "repost": "arrow-repeat",
            "overdue": "exclamation-triangle-fill",
            "reservation_available": "bell-fill",
            "challenge": "trophy-fill",
            "system": "gear-fill",
            "general": "bell-fill",
        }

        return render_template(
            "notifications.html",
            title="Notifications",
            session=session,
            notif_count=_notif_mgr.get_unread_count(uid) if _notif_mgr else 0,
            groups=[
                (label, groups[label]) for label in ["Today", "Yesterday", "This Week", "Earlier"]
            ],
            by_type=by_type.most_common() if by_type else [],
            notif_icons=notif_icons,
            time_ago=time_ago,
            total=total,
            unread=unread,
            read_count=read_count,
        )

    # ════════════════════════════════════════════════════════════════
    # 3. SHELVES PAGE (/shelves)
    # ════════════════════════════════════════════════════════════════

    @app.route("/shelves")
    @login_required
    def shelves_page():
        uid = session["user_id"]
        tab = request.args.get("tab", "want_to_read")
        shelves_data = _review_mgr.get_user_shelf(uid) if _review_mgr else []
        shelf_counts = _review_mgr.get_shelf_counts(uid) if _review_mgr else {}
        custom_shelves = _review_mgr.get_user_custom_shelves(uid) if _review_mgr else []
        books_data = _storage.load_books()

        shelf_tabs = [
            ("want_to_read", "bookmark-heart", "#f59e0b", "Want to Read"),
            ("reading", "book", "#4f46e5", "Currently Reading"),
            ("read", "check-circle", "#10b981", "Finished Reading"),
            ("favorites", "star", "#ec4899", "Favorites"),
            ("dnf", "x-circle", "#ef4444", "Did Not Finish"),
        ]

        tab_html = ""
        for sid, icon, color, label in shelf_tabs:
            count = 0
            if sid == "favorites":
                users_data = _storage.load_users()
                user = users_data.get(uid)
                count = len(user.favorite_books) if user else 0
            elif sid == "dnf":
                count = 0  # No DNF tracking yet
            else:
                count = shelf_counts.get(sid, 0)
            active = "active" if tab == sid else ""
            tab_html += """<a href="/shelves?tab=%s" class="feed-tab %s" role="tab" aria-selected="%s">
                <i class="bi bi-%s-fill" style="color:%s;"></i> %s (%d)</a>""" % (
                sid,
                active,
                "true" if active else "false",
                icon,
                color,
                label,
                count,
            )

        # Current tab books
        books_html = ""
        if tab == "favorites":
            users_data = _storage.load_users()
            user = users_data.get(uid)
            fav_ids = user.favorite_books if user else []
            fav_books = []
            for bid in fav_ids:
                b = books_data.get(bid)
                if b and not b.is_deleted:
                    fav_books.append(b)
            for b in fav_books:
                cc = cat_color(b.category)
                books_html += """<div class="col-6 col-md-4 col-lg-3 mb-2">
                    <div class="glass-card p-2 text-center h-100" draggable="true">
                        <div style="width:40px;height:56px;border-radius:8px;background:linear-gradient(135deg,%s,%sdd);display:flex;align-items:center;justify-content:center;margin:0 auto .3rem;">
                            <i class="bi bi-book-fill" style="color:white;font-size:.9rem;"></i></div>
                        <div style="font-size:.75rem;font-weight:600;">%s</div>
                        <small style="font-size:.6rem;color:var(--text-muted);">%s</small>
                        <div class="mt-1"><button class="btn btn-sm btn-outline" onclick="removeFromShelf('%s')"><i class="bi bi-x"></i></button></div>
                    </div></div>""" % (
                    cc,
                    cc,
                    h(b.title[:35]),
                    h(b.author[:20]),
                    h(b.book_id),
                )
            if not books_html:
                books_html = """<div class="col-12"><div class="empty-state py-4"><div class="empty-icon"><i class="bi bi-star" style="font-size:2rem;"></i></div><h5>No favorites yet</h5><p class="text-muted small">Search to add your favorite books!</p><button class="btn btn-primary btn-sm" onclick="openSearchOverlay()"><i class="bi bi-search"></i> Find Books</button></div></div>"""
        else:
            tab_books = [s for s in shelves_data if s["shelf"] == tab]
            for s in tab_books:
                b = books_data.get(s["book_id"])
                if not b or b.is_deleted:
                    continue
                cc = cat_color(b.category)
                books_html += """<div class="col-6 col-md-4 col-lg-3 mb-2">
                    <div class="glass-card p-2 text-center h-100">
                        <a href="/books/%s" style="text-decoration:none;color:inherit;">
                            <div style="width:40px;height:56px;border-radius:8px;background:linear-gradient(135deg,%s,%sdd);display:flex;align-items:center;justify-content:center;margin:0 auto .3rem;">
                                <i class="bi bi-book-fill" style="color:white;font-size:.9rem;"></i></div>
                            <div style="font-size:.75rem;font-weight:600;">%s</div>
                            <small style="font-size:.6rem;color:var(--text-muted);">%s</small>
                        </a>
                        <div class="mt-1"><button class="btn btn-sm btn-outline" onclick="removeFromShelf('%s')"><i class="bi bi-x"></i></button></div>
                    </div></div>""" % (
                    h(b.book_id),
                    cc,
                    cc,
                    h(b.title[:35]),
                    h(b.author[:20]),
                    h(b.book_id),
                )

        empty_states = {
            "want_to_read": """<div class="col-12"><div class="empty-state py-4"><div class="empty-icon"><i class="bi bi-bookmark-heart" style="font-size:2rem;"></i></div><h5>Your want to read list is empty</h5><p class="text-muted small">Add books you are interested in reading!</p><button class="btn btn-primary btn-sm" onclick="openSearchOverlay()"><i class="bi bi-search"></i> Browse Books</button></div></div>""",
            "reading": """<div class="col-12"><div class="empty-state py-4"><div class="empty-icon"><i class="bi bi-book" style="font-size:2rem;"></i></div><h5>Not reading anything</h5><p class="text-muted small">Start reading a book and track your progress!</p><a href="/books" class="btn btn-primary btn-sm"><i class="bi bi-search"></i> Browse Books</a></div></div>""",
            "read": """<div class="col-12"><div class="empty-state py-4"><div class="empty-icon"><i class="bi bi-check-circle" style="font-size:2rem;"></i></div><h5>No books marked as read</h5><p class="text-muted small">Log completed books to track your reading history.</p><a href="/diary" class="btn btn-primary btn-sm"><i class="bi bi-journal-plus"></i> Log a Book</a></div></div>""",
            "dnf": """<div class="col-12"><div class="empty-state py-4"><div class="empty-icon"><i class="bi bi-x-circle" style="font-size:2rem;"></i></div><h5>No DNF books</h5><p class="text-muted small">Books you did not finish will appear here.</p></div></div>""",
        }
        if not books_html:
            books_html = empty_states.get(tab, empty_states["want_to_read"])

        CONTENT = """<div class="animate-in">
    <div class="d-flex justify-content-between align-items-center mb-3">
        <h4 class="fw-bold mb-0"><i class="bi bi-bookmark-fill me-2" style="color:#f59e0b;"></i>My Shelves</h4>
        <button class="btn btn-primary btn-sm" onclick="createCustomShelf()"><i class="bi bi-plus-lg"></i> New Shelf</button>
    </div>

    <div class="d-flex border-bottom mb-3 gap-2 flex-wrap" role="tablist" aria-label="Book shelves">TABS_HTML</div>

    <div class="row g-2">BOOKS_HTML</div>

    CUSTOM_SHELVES_HTML
</div>
<script>
function removeFromShelf(bid) {
    if(!confirm("Remove this book from shelf?")) return;
    fetch("/api/bookshelves/" + bid + "/remove", {method:"POST"})
        .then(function(r){return r.json()})
        .then(function(d){
            if(d.success){showToast(d.message,"success");setTimeout(function(){location.reload()},800)}
            else{showToast(d.error||"Failed","error")}
        });
}
function createCustomShelf() {
    var name = prompt("Enter shelf name:");
    if(!name||!name.trim()) return;
    fetch("/api/shelves/create", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body: JSON.stringify({name:name.trim(),description:"",icon:"bookmark"})
    }).then(function(r){return r.json()}).then(function(d){
        if(d.success){showToast(d.message,"success");setTimeout(function(){location.reload()},800)}
        else{showToast(d.error||"Failed","error")}
    });
}
</script>"""

        CONTENT = CONTENT.replace("TABS_HTML", tab_html)
        CONTENT = CONTENT.replace("BOOKS_HTML", books_html)

        # Custom shelves section
        custom_html = ""
        for cs in custom_shelves:
            cs_books = [s for s in shelves_data if s["shelf"] == cs["name"]]
            cs_books_html = ""
            for s in cs_books[:4]:
                b = books_data.get(s["book_id"])
                if not b:
                    continue
                cc = cat_color(b.category)
                cs_books_html += """<div class="col-3 col-md-2 mb-1">
                    <div class="glass-card p-1 text-center" style="cursor:pointer;" onclick="window.location.href='/books/%s'">
                        <div style="width:30px;height:40px;border-radius:4px;background:linear-gradient(135deg,%s,%sdd);display:flex;align-items:center;justify-content:center;margin:0 auto .2rem;">
                            <i class="bi bi-book-fill" style="color:white;font-size:.6rem;"></i></div>
                        <div style="font-size:.55rem;font-weight:600;line-height:1.1;">%s</div>
                    </div></div>""" % (
                    h(b.book_id),
                    cc,
                    cc,
                    h(b.title[:20]),
                )
            if not cs_books_html:
                cs_books_html = (
                    '<div class="col-12 text-center text-muted small py-2">Empty shelf.</div>'
                )
            custom_html += """<div class="glass-card p-3 mb-2">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <div class="section-title mb-0"><i class="bi bi-bookmark-fill" style="color:%s;"></i> %s (%d)</div>
                    <div class="d-flex gap-1">
                        <button class="btn btn-sm btn-outline" onclick="deleteCustomShelf('%s')"><i class="bi bi-trash"></i></button>
                    </div>
                </div>
                <div class="row g-1">%s</div>
            </div>""" % (
                h(cs.get("color", "#4f46e5")),
                h(cs["name"]),
                cs.get("book_count", 0),
                h(cs["name"]),
                cs_books_html,
            )

        if custom_html:
            custom_html = (
                '<h5 class="fw-bold mt-3 mb-2"><i class="bi bi-stars me-1" style="color:var(--primary);"></i> Custom Shelves</h5>'
                + custom_html
            )
        CONTENT = CONTENT.replace("CUSTOM_SHELVES_HTML", custom_html)

        CONTENT += """<style>
        .feed-tab{padding:.4rem .8rem;font-size:.8rem;font-weight:600;color:var(--text-muted);text-decoration:none;border-radius:8px 8px 0 0;border-bottom:2px solid transparent;transition:all .2s;display:inline-flex;align-items:center;gap:.3rem;white-space:nowrap}
        .feed-tab.active{color:var(--text);border-bottom-color:var(--primary);background:var(--primary-light)}
        .feed-tab:hover{color:var(--text);background:var(--primary-light)}
        </style>"""

        return render_page("My Shelves", CONTENT)

    # ════════════════════════════════════════════════════════════════
    # 4. RECOMMENDATIONS PAGE (/recommendations)
    # ════════════════════════════════════════════════════════════════

    @app.route("/recommendations")
    @login_required
    def recommendations_page():
        uid = session["user_id"]

        # Personalized
        for_you = []
        try:
            for_you = _recommender.recommend_for_user(uid, top_n=6) if _recommender else []
        except Exception:
            pass

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
                html += """<div class="col-md-3 col-6 mb-2">
                    <div class="glass-card p-2 text-center h-100" onclick="window.location.href='/books/%s'" style="cursor:pointer;">
                        <div style="position:relative;">
                            <div style="width:40px;height:56px;border-radius:8px;background:linear-gradient(135deg,%s,%sdd);display:flex;align-items:center;justify-content:center;margin:0 auto .3rem;">
                                <i class="bi bi-book-fill" style="color:white;font-size:.9rem;"></i></div>
                            %s
                        </div>
                        <div style="font-size:.7rem;font-weight:600;line-height:1.2;">%s</div>
                        <small style="font-size:.6rem;color:var(--text-muted);">%s</small>
                        <div class="mt-1">%s</div>
                        <div style="font-size:.5rem;color:var(--text-muted);margin-top:.2rem;">%s</div>
                    </div></div>""" % (
                    h(bid),
                    cc,
                    cc,
                    ai_badge,
                    h(title),
                    h(author),
                    avail_badge,
                    reason,
                )
            return html

        for_you_html = render_book_grid(for_you, show_ai=True)

        # Trending
        trending = []
        try:
            trending = _recommender.recommend_trending(top_n=8) if _recommender else []
        except Exception:
            pass
        trending_html = render_book_grid(trending, show_ai=False)

        # Bestsellers
        bestsellers = []
        try:
            bestsellers = _recommender.recommend_all_time_best(top_n=8) if _recommender else []
        except Exception:
            pass
        bestsellers_html = render_book_grid(bestsellers)

        # By genre
        books_data = _storage.load_books()
        all_books = [b for b in books_data.values() if not b.is_deleted]
        genre_html = ""
        for cat in list(BOOK_CATEGORIES)[:6]:
            cat_books = [b for b in all_books if b.category == cat][:4]
            if cat_books:
                html = ""
                for b in cat_books:
                    cc = cat_color(cat)
                    html += """<div class="col-3 mb-1">
                        <div class="glass-card p-1 text-center" onclick="window.location.href='/books/%s'" style="cursor:pointer;">
                            <div style="width:30px;height:40px;border-radius:4px;background:linear-gradient(135deg,%s,%sdd);display:flex;align-items:center;justify-content:center;margin:0 auto .2rem;">
                                <i class="bi bi-book-fill" style="color:white;font-size:.6rem;"></i></div>
                            <div style="font-size:.55rem;font-weight:600;line-height:1.1;">%s</div>
                        </div></div>""" % (
                        h(b.book_id),
                        cc,
                        cc,
                        h(b.title[:20]),
                    )
                genre_html += """<div class="glass-card p-3 mb-2">
                    <div class="section-title mb-2"><i class="bi bi-tag-fill" style="color:%s;"></i> %s</div>
                    <div class="row g-1">%s</div>
                </div>""" % (
                    cat_color(cat),
                    h(cat),
                    html,
                )

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
    # 5. BOOK CLUBS PAGE (/clubs)
    # ════════════════════════════════════════════════════════════════

    @app.route("/clubs")
    @login_required
    def clubs_page():
        uid = session["user_id"]
        clubs_data, total = _communities.get_clubs(page=1) if _communities else ([], 0)

        clubs_html = ""
        for c in clubs_data:
            member_count = len(c.get("members", []))
            is_member = uid in c.get("members", [])
            btn = '<a href="/clubs/%s" class="btn btn-primary btn-sm w-100">View Club</a>' % h(
                c["club_id"]
            )
            if is_member:
                btn = (
                    '<div class="d-flex gap-1"><a href="/clubs/%s" class="btn btn-primary btn-sm flex-grow-1">View</a><span class="badge bg-success" style="display:flex;align-items:center;padding:.3rem .6rem;">Member</span></div>'
                    % h(c["club_id"])
                )
            clubs_html += """<div class="col-md-6 col-lg-4 mb-3">
                <div class="glass-card p-3 h-100">
                    <div class="d-flex align-items-center gap-3 mb-2">
                        <div style="width:48px;height:48px;border-radius:12px;background:linear-gradient(135deg,#4f46e5,#a855f7);display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                            <i class="bi bi-people-fill" style="color:white;font-size:1.2rem;"></i>
                        </div>
                        <div class="flex-grow-1" style="min-width:0;">
                            <div class="fw-bold" style="font-size:.9rem;">%s</div>
                            <small class="text-muted">%d members</small>
                        </div>
                    </div>
                    <p style="font-size:.8rem;color:var(--text-muted);margin-bottom:.5rem;">%s</p>
                    <div class="d-flex gap-1 flex-wrap">
                        <span class="badge" style="background:%s20;color:%s;">%s</span>
                    </div>
                    <div class="mt-2">%s</div>
                </div>
            </div>""" % (
                h(c["name"]),
                member_count,
                h(c.get("description", "")[:100]),
                cat_color(c.get("category", "General")),
                cat_color(c.get("category", "General")),
                h(c.get("category", "General")),
                btn,
            )

        if not clubs_html:
            clubs_html = """<div class="col-12"><div class="glass-card p-5 text-center">
                <div style="font-size:3rem;margin-bottom:.5rem;">📚</div>
                <h5>No Book Clubs Yet</h5>
                <p class="text-muted small">Create the first book club and invite readers to join!</p>
                <button class="btn btn-primary" onclick="showCreateClubForm()"><i class="bi bi-plus-lg"></i> Create Club</button>
            </div></div>"""

        CONTENT = (
            """<div class="animate-in">
    <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
        <h4 class="fw-bold mb-0"><i class="bi bi-people-fill me-2" style="color:var(--primary);"></i>Book Clubs <span class="text-muted fw-normal" style="font-size:.9rem;">(%d)</span></h4>
        <button class="btn btn-primary btn-sm" onclick="showCreateClubForm()"><i class="bi bi-plus-lg"></i> Create Club</button>
    </div>
    <div class="row g-3">CLUBS_HTML</div>
</div>

<!-- Create Club Modal -->
<div class="modal fade" id="createClubModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content">
    <div class="modal-header"><h5 class="modal-title"><i class="bi bi-people-fill me-1" style="color:var(--primary);"></i> Create Book Club</h5>
    <button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
    <div class="modal-body">
        <form id="createClubForm" onsubmit="return false;">
            <div class="mb-3"><label class="form-label">Club Name *</label><input type="text" id="clubName" class="form-control" placeholder="e.g. Fantasy Readers" required></div>
            <div class="mb-3"><label class="form-label">Description</label><textarea id="clubDesc" class="form-control" rows="3" placeholder="What is this club about?"></textarea></div>
            <div class="mb-3"><label class="form-label">Category</label><select id="clubCategory" class="form-select">
                <option>General</option><option>Fiction</option><option>Science Fiction</option><option>Fantasy</option>
                <option>Mystery</option><option>Romance</option><option>Non-Fiction</option><option>History</option>
                <option>Philosophy</option>
            </select></div>
            <div class="mb-3"><label class="form-label">Max Members</label><input type="number" id="clubMaxMembers" class="form-control" value="50" min="2" max="500"></div>
        </form>
    </div>
    <div class="modal-footer">
        <button class="btn btn-outline" data-bs-dismiss="modal">Cancel</button>
        <button class="btn btn-primary" onclick="submitCreateClub()"><i class="bi bi-check-lg"></i> Create</button>
    </div>
</div></div></div>

<script>
function showCreateClubForm(){var m=new bootstrap.Modal(document.getElementById("createClubModal"));m.show()}
function submitCreateClub(){
    var data={
        name:document.getElementById("clubName").value.trim(),
        description:document.getElementById("clubDesc").value.trim(),
        category:document.getElementById("clubCategory").value,
        max_members:parseInt(document.getElementById("clubMaxMembers").value)||50,
        is_public:true
    };
    if(!data.name){showToast("Enter a club name","error");return}
    fetch("/api/clubs/create",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify(data)
    }).then(function(r){return r.json()}).then(function(d){
        if(d.success){showToast(d.message,"success");setTimeout(function(){location.reload()},1000)}
        else{showToast(d.error||"Failed","error")}
    });
}
</script>"""
            % total
        )

        CONTENT = CONTENT.replace("CLUBS_HTML", clubs_html)
        return render_page("Book Clubs", CONTENT)

    # ════════════════════════════════════════════════════════════════
    # 6. READING CALENDAR PAGE (/reading-calendar)
    # ════════════════════════════════════════════════════════════════

    @app.route("/reading-calendar")
    @login_required
    def reading_calendar_page():
        uid = session["user_id"]
        year = int(request.args.get("year", datetime.now().year))

        # Get diary entries for the year
        diary_entries = []
        try:
            all_entries, _ = (
                _diary_mgr.get_user_diary(uid, page=1, per_page=5000) if _diary_mgr else ([], 0)
            )
            diary_entries = all_entries
        except Exception:
            pass

        # Build date->count map
        date_counts = defaultdict(int)
        for e in diary_entries:
            try:
                dr = e.get("date_read", "")
                if dr[:4] == str(year):
                    date_counts[dr[:10]] += 1
            except Exception:
                pass

        # Generate calendar grid
        today = date.today()

        MONTHS = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]

        months_html = ""
        for m in range(1, 13):
            if year > today.year and m > today.month:
                break
            first = date(year, m, 1)
            if m == 12:
                last = date(year, 12, 31)
            else:
                last = date(year, m + 1, 1) - timedelta(days=1)

            month_name = MONTHS[m - 1]
            cells = ""
            # Find start day of week (Monday = 0)
            weekday = first.weekday()
            cells += "<tr>"
            for _ in range(weekday):
                cells += '<td class="cal-empty"></td>'

            d = first
            while d <= last:
                ds = d.isoformat()
                count = date_counts.get(ds, 0)
                intensity = min(count, 5)
                cls = "cal-day"
                if count > 0:
                    cls += " cal-l%d" % intensity
                if d == today:
                    cls += " cal-today"
                if d > today:
                    cls += " cal-future"
                title = "%s - %d entries" % (ds, count) if count > 0 else ds
                cells += '<td class="%s" title="%s" onclick="showDayEntries(\'%s\')">%d</td>' % (
                    cls,
                    title,
                    ds,
                    d.day,
                )
                if d.weekday() == 6:  # Sunday
                    cells += "</tr><tr>"
                d += timedelta(days=1)

            while len(cells.split("</tr>")[-1].split("<td")) < 8 and cells.strip():
                cells += '<td class="cal-empty"></td>'
            cells += "</tr>"

            months_html += """<div class="month-card glass-card p-2 mb-2">
                <div class="month-name">%s %d</div>
                <table class="cal-table">
                    <thead><tr>%s</tr></thead>
                    <tbody>%s</tbody>
                </table>
            </div>""" % (
                month_name,
                year,
                "<th>Mon</th><th>Tue</th><th>Wed</th><th>Thu</th><th>Fri</th><th>Sat</th><th>Sun</th>",
                cells,
            )

        stats = _diary_mgr.get_stats(uid) if _diary_mgr else {}

        YEAR_SEL = ""
        for y in range(max(2024, year - 2), year + 1):
            YEAR_SEL += '<a href="/reading-calendar?year=%d" class="btn %s btn-sm">%d</a> ' % (
                y,
                "btn-primary" if y == year else "btn-outline",
                y,
            )

        CONTENT = """<div class="animate-in">
<style>
.cal-table{width:100%%;border-collapse:collapse}
.cal-table th{font-size:.6rem;color:var(--text-muted);font-weight:600;padding:2px;text-align:center;text-transform:uppercase}
.cal-day{text-align:center;padding:4px 2px;font-size:.75rem;font-weight:500;border-radius:4px;cursor:pointer;transition:all .15s}
.cal-day:hover{background:var(--primary-light);transform:scale(1.2)}
.cal-today{background:var(--primary);color:white;font-weight:700}
.cal-future{opacity:.3;cursor:default}
.cal-empty{background:transparent}
.cal-l1{background:rgba(99,102,241,.15)}
.cal-l2{background:rgba(99,102,241,.35)}
.cal-l3{background:rgba(99,102,241,.55)}
.cal-l4{background:rgba(99,102,241,.75);color:white}
.cal-l5{background:rgba(99,102,241,.9);color:white;font-weight:700}
.month-card{border-radius:10px}
.month-name{font-size:.8rem;font-weight:700;margin-bottom:.3rem;color:var(--text-muted)}
</style>
    <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
        <h4 class="fw-bold mb-0"><i class="bi bi-calendar3 me-2 text-primary"></i>Reading Calendar</h4>
        <div class="d-flex gap-1">YEAR_SEL</div>
    </div>

    <div class="stats-bar mb-3">
        <div class="stat-item"><div class="num">%d</div><div class="desc">Entries</div></div>
        <div class="stat-item"><div class="num">%d</div><div class="desc">Days Read</div></div>
        <div class="stat-item"><div class="num">%d</div><div class="desc">Pages</div></div>
        <div class="stat-item"><div class="num" style="color:var(--warning);">%d%%</div><div class="desc">Consistency</div></div>
    </div>

    <div class="row g-2">CALENDAR_HTML</div>

    <div class="glass-card p-3 mt-3">
        <div class="section-title"><i class="bi bi-info-circle"></i> Legend</div>
        <div class="d-flex gap-2 align-items-center">
            <div class="cal-day" style="background:transparent;border:1px solid var(--border);">0</div>
            <div class="cal-day cal-l1">1-2</div>
            <div class="cal-day cal-l2">3-4</div>
            <div class="cal-day cal-l3">5-7</div>
            <div class="cal-day cal-l4">8-10</div>
            <div class="cal-day cal-l5">10+</div>
            <small class="text-muted">entries per day</small>
        </div>
    </div>
</div>
<script>
function showDayEntries(ds) {
    showToast("Entries for " + ds, "info");
}
</script>""" % (
            stats.get("total_books", 0),
            len(date_counts),
            stats.get("total_pages_read", 0),
            round(len(date_counts) / max(1, (datetime.now() - datetime(year, 1, 1)).days) * 100),
        )

        CONTENT = CONTENT.replace("YEAR_SEL", YEAR_SEL)
        CONTENT = CONTENT.replace("CALENDAR_HTML", months_html)

        return render_page("Reading Calendar", CONTENT)

    # ════════════════════════════════════════════════════════════════
    # 7. READING ANALYTICS PAGE (/analytics)
    # ════════════════════════════════════════════════════════════════

    @app.route("/analytics")
    @login_required
    def analytics_page():
        uid = session["user_id"]

        # Gather data
        diary_stats = _diary_mgr.get_stats(uid) if _diary_mgr else {}
        progress_stats = _reading_progress.get_reading_stats(uid) if _reading_progress else {}
        challenge_data = _challenge.get_goal(uid, datetime.now().year) if _challenge else {}
        shelf_counts = _review_mgr.get_shelf_counts(uid) if _review_mgr else {}
        reading_stats = _review_mgr.get_user_reading_stats(uid) if _review_mgr else {}

        # Prepare chart data as JSON for JS
        import json as _json

        monthly_json = _json.dumps(reading_stats.get("monthly_reading", {}))
        rating_dist = _json.dumps(reading_stats.get("rating_distribution", {}))
        cat_data = _json.dumps(reading_stats.get("categories", {}))

        CONTENT = """<div class="animate-in">
    <div class="d-flex justify-content-between align-items-center mb-3">
        <h4 class="fw-bold mb-0"><i class="bi bi-bar-chart-fill me-2" style="color:var(--primary);"></i>Reading Analytics</h4>
    </div>

    <div class="stats-bar mb-3">
        <div class="stat-item"><div class="num">%d</div><div class="desc">Books Read</div></div>
        <div class="stat-item"><div class="num">%d</div><div class="desc">Pages Read</div></div>
        <div class="stat-item"><div class="num">%dm</div><div class="desc">Total Time</div></div>
        <div class="stat-item"><div class="num">%d</div><div class="desc">Challenge</div></div>
        <div class="stat-item"><div class="num">%.1f</div><div class="desc">Avg Rating</div></div>
        <div class="stat-item"><div class="num">%d</div><div class="desc">On Shelves</div></div>
    </div>

    <div class="row g-3">
        <div class="col-lg-6">
            <div class="glass-card p-3 mb-3">
                <div class="section-title"><i class="bi bi-bar-chart-fill"></i> Books Read Per Month</div>
                <div class="chart-container" style="height:200px;"><canvas id="analyticsMonthlyChart"></canvas></div>
            </div>
        </div>
        <div class="col-lg-6">
            <div class="glass-card p-3 mb-3">
                <div class="section-title"><i class="bi bi-pie-chart-fill"></i> Genre Distribution</div>
                <div class="chart-container" style="height:200px;"><canvas id="analyticsGenresChart"></canvas></div>
            </div>
        </div>
        <div class="col-lg-6">
            <div class="glass-card p-3 mb-3">
                <div class="section-title"><i class="bi bi-bar-chart-line-fill"></i> Pages Over Time</div>
                <div class="chart-container" style="height:200px;"><canvas id="analyticsPagesChart"></canvas></div>
            </div>
        </div>
        <div class="col-lg-6">
            <div class="glass-card p-3 mb-3">
                <div class="section-title"><i class="bi bi-star-fill"></i> Rating Distribution</div>
                <div class="chart-container" style="height:200px;"><canvas id="analyticsRatingChart"></canvas></div>
            </div>
        </div>
    </div>
</div>
<script>
(function(){
    var monthlyData = %s;
    var keys = Object.keys(monthlyData).sort();
    var vals = keys.map(function(k){return monthlyData[k]});

    if(document.getElementById("analyticsMonthlyChart") && typeof Chart !== "undefined"){
        new Chart(document.getElementById("analyticsMonthlyChart"), {
            type:"bar",
            data:{labels:keys.slice(-12), datasets:[{label:"Books", data:vals.slice(-12), backgroundColor:"rgba(99,102,241,0.6)", borderColor:"#6366f1", borderWidth:2, borderRadius:4}]},
            options:{responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}},
                scales:{y:{beginAtZero:true,grid:{color:"rgba(0,0,0,0.04)"}},x:{grid:{display:false}}}}
        });
    }

    var catData = %s;
    var catKeys = Object.keys(catData);
    var catVals = catKeys.map(function(k){return catData[k]});
    var catColors = ["#6366f1","#22c55e","#eab308","#ef4444","#3b82f6","#a855f7","#ec4899","#f97316","#14b8a6","#06b6d4"];
    if(document.getElementById("analyticsGenresChart") && typeof Chart !== "undefined"){
        new Chart(document.getElementById("analyticsGenresChart"), {
            type:"doughnut",
            data:{labels:catKeys, datasets:[{data:catVals, backgroundColor:catColors.slice(0,catKeys.length), borderWidth:2, borderColor:"transparent", hoverOffset:6}]},
            options:{responsive:true, maintainAspectRatio:false, plugins:{legend:{position:"bottom",labels:{boxWidth:10,font:{size:9}}}}, cutout:"65%%"}
        });
    }

    if(document.getElementById("analyticsPagesChart") && typeof Chart !== "undefined"){
        var cumul = []; var run = 0;
        vals.forEach(function(v){run+=v;cumul.push(run)});
        new Chart(document.getElementById("analyticsPagesChart"), {
            type:"line",
            data:{labels:keys, datasets:[{label:"Cumulative Pages", data:cumul, borderColor:"#22c55e", backgroundColor:"rgba(34,197,94,0.1)", fill:true, tension:.3, pointRadius:2, pointBackgroundColor:"#22c55e", borderWidth:2}]},
            options:{responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}},
                scales:{y:{beginAtZero:true,grid:{color:"rgba(0,0,0,0.04)"}},x:{grid:{display:false}}}}
        });
    }

    var ratingData = %s;
    var rLabels = ["1 Star","2 Stars","3 Stars","4 Stars","5 Stars"];
    var rVals = [ratingData["1"]||0, ratingData["2"]||0, ratingData["3"]||0, ratingData["4"]||0, ratingData["5"]||0];
    if(document.getElementById("analyticsRatingChart") && typeof Chart !== "undefined"){
        new Chart(document.getElementById("analyticsRatingChart"), {
            type:"bar",
            data:{labels:rLabels, datasets:[{label:"Count", data:rVals, backgroundColor:["#ef4444","#f97316","#eab308","#22c55e","#3b82f6"], borderRadius:4}]},
            options:{responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}},
                scales:{y:{beginAtZero:true,grid:{color:"rgba(0,0,0,0.04)"}},x:{grid:{display:false}}}}
        });
    }
})();
</script>""" % (
            diary_stats.get("total_books", 0),
            progress_stats.get("total_pages_read", 0),
            progress_stats.get("total_time_spent_minutes", 0),
            challenge_data.get("progress", 0),
            reading_stats.get("avg_rating", 0),
            shelf_counts.get("total", 0),
            monthly_json,
            cat_data,
            rating_dist,
        )

        return render_page("Reading Analytics", CONTENT)

    # ════════════════════════════════════════════════════════════════
    # 8. ADMIN USERS PAGE (/admin/users)
    # ════════════════════════════════════════════════════════════════

    @app.route("/admin/users")
    @login_required
    @admin_required
    def admin_users_page():
        users_data = _storage.load_users()
        q = request.args.get("q", "").strip().lower()
        role_filter = request.args.get("role", "").strip().lower()
        status_filter = request.args.get("status", "").strip().lower()

        user_list = list(users_data.values())
        if q:
            user_list = [
                u
                for u in user_list
                if q in u.name.lower() or q in u.user_id.lower() or q in (u.email or "").lower()
            ]
        if role_filter:
            user_list = [u for u in user_list if u.role == role_filter]
        if status_filter:
            user_list = [
                u for u in user_list if (u.membership_status or "Active").lower() == status_filter
            ]

        total = len(users_data)
        active = sum(
            1 for u in users_data.values() if (u.membership_status or "Active") == "Active"
        )
        blocked = sum(1 for u in users_data.values() if (u.membership_status or "") == "Blocked")

        fines = _storage.load_fines() if hasattr(_storage, "load_fines") else []
        pending_fines = sum(f.get("amount", 0) for f in fines if not f.get("paid"))

        role_counts = Counter(u.role for u in users_data.values())
        role_html = ""
        role_colors = {"admin": "#ef4444", "librarian": "#f59e0b", "user": "#6366f1"}
        total_users = max(len(users_data), 1)
        for role in ["admin", "librarian", "user"]:
            cnt = role_counts.get(role, 0)
            pct = round(cnt / total_users * 100, 2)
            role_html += """<div class="d-flex align-items-center gap-2 mb-1">
                <span class="small" style="min-width:70px;font-weight:600;">%s</span>
                <div class="flex-grow-1"><div class="progress-thin"><div class="bar" style="width:%s%%;background:%s;"></div></div></div>
                <small class="fw-bold">%d</small>
                <small class="text-muted">(%.2f%%)</small>
            </div>""" % (
                role.capitalize(),
                pct,
                role_colors.get(role, "#6366f1"),
                cnt,
                pct,
            )

        # Table rows
        rows = ""
        for u in user_list[:100]:
            av = avatar_html(u.name, 28)
            status = u.membership_status or "Active"
            status_cls = "text-success" if status == "Active" else "text-danger"
            role_cls = {
                "admin": "badge bg-danger",
                "librarian": "badge bg-warning text-dark",
                "user": "badge bg-primary",
            }
            rb = role_cls.get(u.role, "badge bg-secondary")

            user_fines = sum(
                f.get("amount", 0)
                for f in fines
                if f.get("user_id") == u.user_id and not f.get("paid")
            )
            rows += """<tr>
                <td>%s</td>
                <td><div class="d-flex align-items-center gap-2"><div>%s</div><div><div class="fw-bold small">%s</div><small class="text-muted">@%s</small></div></div></td>
                <td>%s</td>
                <td><span class="%s">%s</span></td>
                <td><span class="%s">%s</span></td>
                <td><span class="fw-bold">&#8377;%.0f</span></td>
                <td><a href="/profile/%s" class="btn btn-sm btn-outline"><i class="bi bi-eye"></i></a></td>
            </tr>""" % (
                av,
                av,
                h(u.name),
                h(u.user_id),
                rb,
                role_cls.get(u.role, "badge bg-secondary"),
                u.role.capitalize(),
                status_cls,
                status,
                user_fines,
                h(u.user_id),
            )

        if not rows:
            rows = (
                '<tr><td colspan="7" class="text-center text-muted py-4">No users found.</td></tr>'
            )

        q_esc = h(q) if q else ""
        CONTENT = """<div class="animate-in">
    <style>
    .users-table{table-layout:fixed;width:100%%}
    .users-table th{padding:.5rem .3rem;font-size:.7rem;font-weight:700;text-transform:uppercase;color:var(--text-muted);border-bottom:2px solid var(--border)}
    .users-table td{padding:.4rem .3rem;font-size:.8rem;vertical-align:middle;border-bottom:1px solid var(--border)}
    .col-avatar{width:40px}.col-user{width:auto}.col-role{width:70px}.col-status{width:80px}.col-fines{width:60px}.col-actions{width:50px}
    </style>

    <div class="glass-card p-0 mb-3" style="overflow:hidden;">
        <div class="p-3" style="background:linear-gradient(135deg,#7c3aed,#4f46e5);color:white;">
            <h4 class="fw-bold mb-0"><i class="bi bi-people-fill me-2"></i>User Management</h4>
            <p class="mb-0" style="opacity:.8;font-size:.85rem;">Manage all registered users</p>
        </div>
    </div>

    <div class="stats-bar mb-3">
        <div class="stat-item"><div class="num">%d</div><div class="desc">Total Users</div></div>
        <div class="stat-item"><div class="num text-success">%d</div><div class="desc">Active</div></div>
        <div class="stat-item"><div class="num text-danger">%d</div><div class="desc">Blocked</div></div>
        <div class="stat-item"><div class="num text-warning">&#8377;%.0f</div><div class="desc">Pending Fines</div></div>
    </div>

    <div class="row g-3 mb-3">
        <div class="col-lg-4">
            <div class="glass-card p-3 h-100">
                <div class="section-title"><i class="bi bi-pie-chart-fill"></i> Role Distribution</div>
                ROLE_HTML
            </div>
        </div>
        <div class="col-lg-8">
            <div class="glass-card p-3">
                <div class="section-title"><i class="bi bi-search"></i> Search &amp; Filter</div>
                <form class="d-flex gap-2 flex-wrap" method="GET">
                    <input type="text" name="q" class="form-control" style="flex:1;min-width:150px;" placeholder="Search by name, ID, or email..." value="%s">
                    <select name="role" class="form-select" style="width:120px;">
                        <option value="">All Roles</option>
                        <option value="admin" %s>Admin</option>
                        <option value="librarian" %s>Librarian</option>
                        <option value="user" %s>User</option>
                    </select>
                    <select name="status" class="form-select" style="width:120px;">
                        <option value="">All Status</option>
                        <option value="active" %s>Active</option>
                        <option value="blocked" %s>Blocked</option>
                    </select>
                    <button class="btn btn-primary" type="submit"><i class="bi bi-search"></i> Filter</button>
                    <a href="/admin/users" class="btn btn-outline"><i class="bi bi-x-lg"></i> Clear</a>
                </form>
            </div>
        </div>
    </div>

    <div class="glass-card p-0" style="overflow-x:auto;">
        <table class="users-table w-100" aria-label="Registered users">
            <thead><tr>
                <th class="col-avatar"></th>
                <th class="col-user">User</th>
                <th class="col-role">Role</th>
                <th class="col-status">Status</th>
                <th class="col-fines">Fines</th>
                <th class="col-actions"></th>
            </tr></thead>
            <tbody>%s</tbody>
        </table>
    </div>
    <div class="text-end text-muted small mt-2">Showing first 100 users.</div>
</div>""" % (
            total,
            active,
            blocked,
            pending_fines,
            q_esc,
            "selected" if role_filter == "admin" else "",
            "selected" if role_filter == "librarian" else "",
            "selected" if role_filter == "user" else "",
            "selected" if status_filter == "active" else "",
            "selected" if status_filter == "blocked" else "",
            rows,
        )

        CONTENT = CONTENT.replace("ROLE_HTML", role_html)

        return render_page("User Management", CONTENT)

    @app.route("/admin/audit")
    @login_required
    @admin_required
    def admin_audit_page():
        """Searchable admin audit trail: who changed what setting, when, from where."""
        import app.db.database as _dbmod
        from app.db.repositories import AuditLogRepository

        q = request.args.get("q", "").strip()
        admin_filter = request.args.get("admin_id", "").strip()
        action_filter = request.args.get("action", "").strip()
        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            page = 1
        per_page = 50

        try:
            with _dbmod.session_scope() as db:
                repo = AuditLogRepository(db)
                rows = repo.search(
                    query=q,
                    admin_id=admin_filter,
                    action=action_filter,
                    page=page,
                    per_page=per_page,
                )
                total = repo.count(query=q, admin_id=admin_filter, action=action_filter)
        except Exception as e:
            logger.warning("admin audit page query failed: %s", e)
            rows, total = [], 0

        # Action badge colors (stable set; unknown -> neutral)
        action_colors = {
            "settings.update": "badge bg-primary",
            "auth.failed": "badge bg-danger",
            "admin.password_change": "badge bg-warning text-dark",
        }
        rows_html = ""
        for r in rows:
            badge = action_colors.get(r["action"], "badge bg-secondary")
            old_txt = h(r["old_value"] or "—")
            new_txt = h(r["new_value"] or "—")
            ts = h((r["created_at"] or "")[:19])
            rows_html += """<tr>
                <td class="text-nowrap small">%s</td>
                <td><span class="fw-bold small">%s</span></td>
                <td><span class="%s">%s</span></td>
                <td class="small"><code>%s</code></td>
                <td class="small text-muted">%s</td>
                <td class="small text-muted">%s</td>
                <td class="small text-muted text-nowrap">%s</td>
            </tr>""" % (
                ts,
                h(r["admin_id"]),
                badge,
                h(r["action"]),
                h(r["target"]),
                old_txt,
                new_txt,
                h(r["ip_address"] or ""),
            )
        if not rows_html:
            rows_html = (
                '<tr><td colspan="7" class="text-center text-muted py-4">'
                "No audit entries found.</td></tr>"
            )

        pages = max(1, -(-total // per_page))
        pag_html = ""
        if pages > 1:
            # URL-encode the query params (not HTML-escape: spaces/# in q must
            # survive inside the href), and HTML-escape the ampersands for the
            # attribute itself.
            from urllib.parse import urlencode

            base_q = h("&" + urlencode({"q": q, "admin_id": admin_filter, "action": action_filter}))
            pag_html = '<nav class="mt-3" aria-label="Audit log pages"><ul class="pagination pagination-sm justify-content-end">'
            if page > 1:
                pag_html += (
                    '<li class="page-item"><a class="page-link" href="/admin/audit?page=%d%s">&laquo;</a></li>'
                    % (page - 1, base_q)
                )
            pag_html += (
                '<li class="page-item disabled"><span class="page-link">Page %d / %d</span></li>'
                % (page, pages)
            )
            if page < pages:
                pag_html += (
                    '<li class="page-item"><a class="page-link" href="/admin/audit?page=%d%s">&raquo;</a></li>'
                    % (page + 1, base_q)
                )
            pag_html += "</ul></nav>"

        CONTENT = """<div class="animate-in">
    <style>
    .audit-table th{font-size:.7rem;font-weight:700;text-transform:uppercase;color:var(--text-muted);border-bottom:2px solid var(--border)}
    .audit-table td{padding:.45rem .5rem;font-size:.8rem;vertical-align:middle;border-bottom:1px solid var(--border)}
    </style>

    <div class="glass-card p-0 mb-3" style="overflow:hidden;">
        <div class="p-3" style="background:linear-gradient(135deg,#0f766e,#059669);color:white;">
            <h4 class="fw-bold mb-0"><i class="bi bi-journal-check me-2"></i>Audit Log</h4>
            <p class="mb-0" style="opacity:.8;font-size:.85rem;">Every admin setting change — who, what, when, and from where</p>
        </div>
    </div>

    <div class="glass-card p-3 mb-3">
        <form class="d-flex gap-2 flex-wrap" method="GET">
            <input type="text" name="q" class="form-control" style="flex:1;min-width:160px;" placeholder="Search setting, value, or IP..." value="%s">
            <input type="text" name="admin_id" class="form-control" style="width:140px;" placeholder="Admin ID" value="%s">
            <select name="action" class="form-select" style="width:170px;">
                <option value="">All Actions</option>
                <option value="settings.update" %s>settings.update</option>
                <option value="auth.failed" %s>auth.failed</option>
                <option value="admin.password_change" %s>admin.password_change</option>
            </select>
            <button class="btn btn-primary" type="submit"><i class="bi bi-search"></i> Search</button>
            <a href="/admin/audit" class="btn btn-outline"><i class="bi bi-x-lg"></i> Clear</a>
        </form>
    </div>

    <div class="glass-card p-0" style="overflow-x:auto;">
        <table class="audit-table w-100" aria-label="Admin audit trail">
            <thead><tr>
                <th>When</th><th>Admin</th><th>Action</th><th>Setting</th>
                <th>Old</th><th>New</th><th>IP</th>
            </tr></thead>
            <tbody>%s</tbody>
        </table>
    </div>
    <div class="text-end text-muted small mt-2">%d entries</div>
    %s
</div>""" % (
            h(q),
            h(admin_filter),
            "selected" if action_filter == "settings.update" else "",
            "selected" if action_filter == "auth.failed" else "",
            "selected" if action_filter == "admin.password_change" else "",
            rows_html,
            total,
            pag_html,
        )

        return render_page("Audit Log", CONTENT)

    # ════════════════════════════════════════════════════════════════
    # API ENDPOINTS needed by the pages above
    # ════════════════════════════════════════════════════════════════

    @app.route("/api/notifications/<notif_id>/read", methods=["POST"])
    @login_required
    def api_notification_read(notif_id):
        if _notif_mgr:
            _notif_mgr.mark_as_read(notif_id)
        return jsonify({"success": True})

    @app.route("/api/notifications/read-all", methods=["POST"])
    @login_required
    def api_notifications_read_all():
        uid = session["user_id"]
        if _notif_mgr:
            _notif_mgr.mark_all_read(uid)
        notif = _notif_mgr.get_notifications(uid) if _notif_mgr else []
        unread = sum(1 for n in notif if not n.get("read"))
        return jsonify({"success": True, "unread_count": unread})

    @app.route("/api/clubs/create", methods=["POST"])
    @login_required
    # Abuse ceiling: club creation is shared-surface content spam.
    @_rate_limit("10 per minute")
    def api_create_club():
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg, club = (
            _communities.create_club(
                data.get("name", ""),
                data.get("description", ""),
                uid,
                category=data.get("category", "General"),
                is_public=data.get("is_public", True),
                max_members=int(data.get("max_members", 50)),
            )
            if _communities
            else (False, "Clubs module not available", None)
        )
        return jsonify(
            {"success": ok, "message": msg, "club": club}
        )  # ════════════════════════════════════════════════════════════════

    # MISSING SIDEBAR ROUTES
    # ════════════════════════════════════════════════════════════════

    @app.route("/profile")
    @login_required
    def profile_self_redirect():
        """Redirect /profile to the current user's profile."""
        uid = session["user_id"]
        return redirect(url_for("profile_page", user_id=uid))

    @app.route("/dashboard")
    @login_required
    def dashboard_page():
        """Admin dashboard with stats grid + user data (points, level, streak, leaderboard)."""
        uid = session["user_id"]
        user = get_current_user()
        s = _library_stats()

        # Fetch user gamification data
        gd = _gamification.get_user_gamification(uid) if _gamification else {}
        points = gd.get("points", 0)
        level = gd.get("level", "New Reader")
        next_level = gd.get("next_level", "")
        next_lvl_pts = gd.get("next_level_points", 0) or 1
        streak = gd.get("streak_days", 0)
        longest_streak = gd.get("longest_streak", 0)
        unlocked_ach = gd.get("unlocked_achievements", 0)
        total_ach = gd.get("total_achievements", 15)

        # Leaderboard position
        leaderboard = _gamification.get_leaderboard(top_n=50) if _gamification else []
        user_rank = 0
        for entry in leaderboard:
            if entry.get("user_id") == uid:
                user_rank = entry.get("rank", 0)
                break

        # Reading stats from diary
        diary_stats = _diary_mgr.get_stats(uid) if _diary_mgr else {}
        books_read = diary_stats.get("total_books", 0)
        pages_read = diary_stats.get("total_pages_read", 0)

        # Challenge progress
        challenge = _challenge.get_goal(uid, datetime.now().year) if _challenge else {}
        challenge_progress = challenge.get("progress", 0)
        challenge_goal = challenge.get("goal", 0)
        challenge_pct = challenge.get("percentage", 0)

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
            '<span class="stat-number" style="color:var(--color-success);">'
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

    @app.route("/books")
    @login_required
    def books_page():
        """Books page with grid/list view, filtering, inline stats."""
        books_data = _storage.load_books()
        all_books = [b for b in books_data.values() if not b.is_deleted]
        q = request.args.get("q", "").strip()
        cat_filter = request.args.get("cat", "")

        # Filter
        if q:
            ql = q.lower()
            all_books = [b for b in all_books if ql in b.title.lower() or ql in b.author.lower()]
        if cat_filter:
            all_books = [b for b in all_books if b.category == cat_filter]

        total = len(all_books)
        available = sum(1 for b in all_books if b.available_copies > 0)
        checked_out = total - available
        cats = len(set(b.category for b in all_books))
        categories = sorted(set(b.category for b in books_data.values() if not b.is_deleted))

        return render_template(
            "books.html",
            title="Books",
            session=session,
            notif_count=(
                _notif_mgr.get_unread_count(session.get("user_id")) if session.get("user_id") else 0
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

    @app.route("/reports")
    @login_required
    @admin_required
    def reports_page():
        """Reports page - metrics grouped into semantic sections."""
        s = _library_stats()

        # Render via the Jinja template (autoescape ON)
        return render_template(
            "reports.html",
            title="Reports & Analytics",
            session=session,
            notif_count=(
                _notif_mgr.get_unread_count(session.get("user_id")) if session.get("user_id") else 0
            ),
            s=s,
        )

    # ════════════════════════════════════════════════════════════════
    # BOOK DETAIL PAGE (/books/<id>) - Part 6.1
    # ════════════════════════════════════════════════════════════════

    @app.route("/books/<book_id>")
    @login_required
    def book_detail_page(book_id):
        """Book detail page with cover, metadata, reviews, similar books."""
        books_data = _storage.load_books()
        book = books_data.get(book_id)
        if not book or book.is_deleted:
            return render_page(
                "Not Found",
                '<div class="empty-state py-5"><div class="empty-icon">\U0001f4da</div><h5>Book not found</h5><p class="text-muted">This book may have been removed.</p><a href="/books" class="btn btn-primary btn-sm"><i class="bi bi-arrow-left"></i> Browse Books</a></div>',
            )

        cc = cat_color(book.category)
        avail_text = "Available" if book.available_copies > 0 else "Checked Out"
        avail_cls = "success" if book.available_copies > 0 else "danger"

        # Checkout state for the Borrow/Return buttons (Phase 8 e2e): a member
        # who currently holds this book sees Return; otherwise Borrow when a
        # copy is available. Staff see the same self-service controls.
        uid = session.get("user_id")
        is_issued_to_me = False
        if uid:
            _me = _storage.load_users().get(uid)
            is_issued_to_me = bool(_me and book_id in (_me.books_issued or []))

        # Reviews (enriched for the Jinja template)
        reviews = []
        try:
            all_reviews = _storage.load_reviews() if hasattr(_storage, "load_reviews") else []
            book_reviews = [r for r in all_reviews if r.get("book_id") == book_id][:5]
            users_data = _storage.load_users()
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
        except Exception as exc:
            logger.warning("book detail %s: reviews unavailable: %s", book_id, exc)
            reviews = []

        # Similar books (rendered by the Jinja template)
        similar = []
        try:
            sim = _recommender.recommend_similar_books(book_id, top_n=4) if _recommender else []
            similar = [
                {
                    "book_id": r.get("book_id"),
                    "title": r.get("title", ""),
                    "category": r.get("category", ""),
                }
                for r in sim
                if r and r.get("book_id")
            ]
        except Exception as exc:
            logger.warning("book detail %s: similar books unavailable: %s", book_id, exc)
            similar = []

        # Render via the Jinja template (autoescape ON)
        return render_template(
            "book_detail.html",
            title=book.title,
            session=session,
            notif_count=(
                _notif_mgr.get_unread_count(session.get("user_id")) if session.get("user_id") else 0
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
    # 7b. BORROW / RETURN API (self-service checkout — Phase 8 e2e)
    # ════════════════════════════════════════════════════════════════
    # The web layer previously had NO checkout surface (the smoke checklist
    # documented issue/return as Library-only journeys). These endpoints make
    # borrowing real in the browser: a member checks a book out to themselves
    # (self-service); staff may pass {"user_id": ...} to act on behalf of a
    # member. Both delegate to Library.issue_book/return_book, which run inside
    # a single DB transaction (no oversell), and both are CSRF-protected by the
    # global CSRFProtect (the page JS attaches X-CSRFToken via the meta tag).

    @app.route("/api/books/<book_id>/issue", methods=["POST"])
    @login_required
    @_rate_limit("10 per minute", methods=["POST"])
    def api_book_issue(book_id):
        """Check a book out. Self-service by default; staff may target a user."""
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
        ok, msg = _lib.issue_book(target, book_id, actor=session.get("user_id"))
        return jsonify({"success": ok, "message": msg}), 200 if ok else 409

    @app.route("/api/books/<book_id>/return", methods=["POST"])
    @login_required
    @_rate_limit("10 per minute", methods=["POST"])
    def api_book_return(book_id):
        """Return a book. Self-service by default; staff may target a user."""
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
        ok, msg, fine = _lib.return_book(target, book_id, actor=session.get("user_id"))
        return jsonify({"success": ok, "message": msg, "fine": fine}), 200 if ok else 409

    # ════════════════════════════════════════════════════════════════
    # CLUB DETAIL PAGE (/clubs/<club_id>)
    # ════════════════════════════════════════════════════════════════

    @app.route("/clubs/<club_id>")
    @login_required
    def club_detail_page(club_id):
        """Club detail page with members, current book, and forum topics."""
        uid = session["user_id"]
        club = _communities.get_club(club_id) if _communities else None

        if not club:
            return render_page(
                "Club Not Found",
                '<div class="text-center py-5"><div style="font-size:4rem;">🔍</div><h5>Club not found</h5><p class="text-muted">This book club may have been deleted.</p><a href="/clubs" class="btn btn-primary btn-sm"><i class="bi bi-arrow-left"></i> Browse Clubs</a></div>',
            )

        is_member = uid in club.get("members", [])
        member_count = len(club.get("members", []))

        # Enrich members
        users_data = _storage.load_users()
        members_html = ""
        for mid in club.get("members", [])[:12]:
            mu = users_data.get(mid)
            name = mu.name if mu else mid[:8]
            role_badge = (
                '<span class="badge bg-danger" style="font-size:.5rem;">Owner</span>'
                if mid == club.get("owner_id")
                else (
                    '<span class="badge bg-warning text-dark" style="font-size:.5rem;">Mod</span>'
                    if mid in club.get("moderators", [])
                    else ""
                )
            )
            members_html += (
                '<div class="d-flex align-items-center gap-2 mb-1">'
                + avatar_html(name, 28)
                + '<span class="small">'
                + h(name[:20])
                + "</span> "
                + role_badge
                + "</div>"
            )
        if not members_html:
            members_html = '<div class="text-muted small py-2">No members yet.</div>'

        # Current book
        current_book = club.get("current_book", {})
        book_html = ""
        if current_book:
            bid = current_book.get("book_id", "")
            btitle = current_book.get("title", "")
            bauth = current_book.get("author", "")
            book_html = (
                '<div class="glass-card p-3 mb-3"><div class="section-title"><i class="bi bi-book-fill text-primary"></i> Currently Reading</div><div class="d-flex align-items-center gap-2"><div style="width:36px;height:36px;border-radius:8px;background:var(--primary);display:flex;align-items:center;justify-content:center;color:white;"><i class="bi bi-book-fill"></i></div><div><a href="/books/'
                + h(bid)
                + '" class="fw-bold text-decoration-none" style="color:var(--text);font-size:.9rem;">'
                + h(btitle)
                + '</a><br><small class="text-muted">'
                + h(bauth)
                + "</small></div></div></div>"
            )
        else:
            book_html = '<div class="glass-card p-3 mb-3 text-center text-muted small py-3"><i class="bi bi-book"></i> No current book selected.</div>'

        # Forum topics
        forum_html = ""
        try:
            topics, t_total = _communities.get_topics(club_id)
            for t in topics[:8]:
                forum_html += (
                    '<div class="d-flex align-items-center gap-2 mb-2 p-2" style="border-radius:8px;border:1px solid var(--border);cursor:pointer;" onclick="showToast(\'Topic view coming soon\',\'info\')"><div style="width:32px;height:32px;border-radius:50%;background:var(--primary-light);display:flex;align-items:center;justify-content:center;"><i class="bi bi-chat-dots" style="color:var(--primary);"></i></div><div class="flex-grow-1" style="min-width:0;"><div class="fw-bold small">'
                    + h(t["title"][:50])
                    + '</div><small class="text-muted">by '
                    + h(t.get("author_name", ""))
                    + " &middot; "
                    + str(t.get("replies_count", 0))
                    + " replies</small></div></div>"
                )
        except Exception:
            pass
        if not forum_html:
            forum_html = '<div class="text-center text-muted small py-3">No discussions yet. Start one!</div>'

        cc = cat_color(club.get("category", "General"))
        join_leave_btn = ""
        if is_member:
            join_leave_btn = (
                '<button class="btn btn-outline btn-sm" onclick="leaveClub(\''
                + h(club_id)
                + '\')"><i class="bi bi-box-arrow-left"></i> Leave Club</button>'
            )
        else:
            join_leave_btn = (
                '<button class="btn btn-primary btn-sm" onclick="joinClub(\''
                + h(club_id)
                + '\')"><i class="bi bi-person-plus"></i> Join Club</button>'
            )

        CONTENT = """<div class="animate-in">
    <div class="row">
        <div class="col-lg-8">
            <div class="glass-card p-4 mb-3">
                <div class="d-flex gap-3">
                    <div style="width:56px;height:56px;border-radius:14px;background:linear-gradient(135deg,%s,%sdd);display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                        <i class="bi bi-people-fill" style="color:white;font-size:1.3rem;"></i>
                    </div>
                    <div class="flex-grow-1">
                        <h4 class="fw-bold mb-1">%s</h4>
                        <p class="text-muted mb-1" style="font-size:.85rem;">%s</p>
                        <div class="d-flex gap-2 flex-wrap">
                            <span class="badge" style="background:%s20;color:%s;">%s</span>
                            <span class="badge bg-secondary">%d members</span>
                            %s
                        </div>
                    </div>
                    <div>%s</div>
                </div>
            </div>
            %s
            <div class="glass-card p-3 mb-3">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <div class="section-title mb-0"><i class="bi bi-chat-dots-fill"></i> Discussions</div>
                    <button class="btn btn-primary btn-sm" onclick="showToast('Topic creation coming soon','info')"><i class="bi bi-plus-lg"></i> New Topic</button>
                </div>
                %s
            </div>
        </div>
        <div class="col-lg-4">
            <div class="glass-card p-3 mb-3">
                <div class="section-title"><i class="bi bi-people-fill"></i> Members (%d)</div>
                <div style="max-height:300px;overflow-y:auto;">%s</div>
                <a href="/clubs" class="btn btn-outline btn-sm w-100 mt-2">All Clubs</a>
            </div>
        </div>
    </div>
</div>
<script>
function joinClub(cid) {
    fetch("/api/clubs/" + cid + "/join", {method:"POST"})
        .then(function(r){return r.json()})
        .then(function(d){if(d.success){showToast(d.message,"success");setTimeout(function(){location.reload()},1000)}else{showToast(d.error,"error")}});
}
function leaveClub(cid) {
    if(!confirm("Leave this club?")) return;
    fetch("/api/clubs/" + cid + "/leave", {method:"POST"})
        .then(function(r){return r.json()})
        .then(function(d){if(d.success){showToast(d.message,"success");setTimeout(function(){location.reload()},1000)}else{showToast(d.error,"error")}});
}
</script>""" % (
            cc,
            cc,
            h(club["name"]),
            h(club.get("description", "")[:150]),
            cc,
            cc,
            h(club.get("category", "General")),
            member_count,
            (
                '<span class="badge bg-success">Public</span>'
                if club.get("is_public", True)
                else '<span class="badge bg-secondary">Private</span>'
            ),
            join_leave_btn,
            book_html,
            forum_html,
            member_count,
            members_html,
        )

        return render_page(club["name"], CONTENT)

    # ════════════════════════════════════════════════════════════════
    # GAMIFICATION PAGE (/gamification)
    # ════════════════════════════════════════════════════════════════

    @app.route("/gamification")
    @login_required
    def gamification_page():
        """Gamification page with badges, leaderboard, and XP."""
        uid = session["user_id"]
        gd = _gamification.get_user_gamification(uid) if _gamification else {}
        leaderboard = _gamification.get_leaderboard(top_n=20) if _gamification else []

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
            medal = {1: "\U0001f947", 2: "\U0001f948", 3: "\U0001f949"}.get(rank, f"#{rank}")
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
                <div style="font-size:2rem;font-weight:800;color:var(--danger);">\U0001f525 %d</div>
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
    # ADMIN OVERDUE PAGE (/admin/overdue)
    # ════════════════════════════════════════════════════════════════

    @app.route("/admin/overdue")
    @login_required
    @admin_required
    def admin_overdue_page():
        """Admin overdue books management page."""
        txns = _storage.load_transactions()
        books_data = _storage.load_books()
        users_data = _storage.load_users()
        now = datetime.now()

        # Find overdue issues
        overdue = []
        for t in txns:
            if t["type"] == "issue" and t.get("return_date") is None:
                try:
                    issue_date = datetime.fromisoformat(t["issue_date"])
                    from app.config.settings import Config as C

                    due_date = issue_date + timedelta(days=C.ISSUE_DAYS)
                    if now > due_date:
                        days_overdue = (now - due_date).days
                        book = books_data.get(t["book_id"])
                        user = users_data.get(t["user_id"])
                        fine_amount = round(days_overdue * C.FINE_PER_DAY, 2)
                        overdue.append(
                            {
                                "user_id": t["user_id"],
                                "user_name": user.name if user else t["user_id"],
                                "book_id": t["book_id"],
                                "book_title": book.title if book else "Unknown",
                                "issue_date": t["issue_date"][:10],
                                "due_date": due_date.isoformat()[:10],
                                "days_overdue": days_overdue,
                                "fine": fine_amount,
                            }
                        )
                except Exception:
                    pass

        overdue.sort(key=lambda x: x["days_overdue"], reverse=True)

        rows = ""
        for o in overdue[:100]:
            severity = (
                "danger"
                if o["days_overdue"] > 14
                else "warning" if o["days_overdue"] > 7 else "dark"
            )
            rows += (
                '<tr><td><a href="/profile/'
                + h(o["user_id"])
                + '" class="fw-bold text-decoration-none">'
                + h(o["user_name"])
                + '</a></td><td><a href="/books/'
                + h(o["book_id"])
                + '" class="text-decoration-none">'
                + h(o["book_title"][:40])
                + "</a></td><td>"
                + o["due_date"]
                + '</td><td><span class="badge bg-'
                + severity
                + '">'
                + str(o["days_overdue"])
                + " days</span></td><td>&#8377;"
                + ("%.2f" % o["fine"])
                + '</td><td><button class="btn btn-sm btn-outline" onclick="showToast(\'Return processing coming soon\',\'info\')"><i class="bi bi-arrow-return-left"></i></button></td></tr>'
            )

        if not rows:
            rows = '<tr><td colspan="6" class="text-center text-muted py-4">No overdue books. The library is healthy!</td></tr>'

        CONTENT = """<div class="animate-in">
    <div class="glass-card p-0 mb-3" style="overflow:hidden;">
        <div class="p-3" style="background:linear-gradient(135deg,#7c3aed,#4f46e5);color:white;">
            <h4 class="fw-bold mb-0"><i class="bi bi-exclamation-triangle-fill me-2"></i>Overdue Books</h4>
            <p class="mb-0" style="opacity:.8;font-size:.85rem;">%d items overdue</p>
        </div>
    </div>
    <div class="stats-bar mb-3">
        <div class="stat-item"><div class="num" style="color:var(--color-danger);">%d</div><div class="desc">Overdue Items</div></div>
        <div class="stat-item"><div class="num" style="color:var(--color-warning);">&#8377;%.2f</div><div class="desc">Total Fines Owed</div></div>
        <div class="stat-item"><div class="num">%.1f</div><div class="desc">Avg Days Overdue</div></div>
    </div>
    <div class="glass-card p-0" style="overflow-x:auto;">
        <table class="table table-hover mb-0"><thead><tr>
            <th>User</th><th>Book</th><th>Due Date</th><th>Overdue</th><th>Fine</th><th>Action</th>
        </tr></thead><tbody>%s</tbody></table>
    </div>
    <div class="mt-2 text-end text-muted small">Showing first 100 overdue items.</div>
</div>""" % (
            len(overdue),
            len(overdue),
            sum(o["fine"] for o in overdue),
            round(sum(o["days_overdue"] for o in overdue) / max(1, len(overdue)), 1),
            rows,
        )

        return render_page("Overdue Books", CONTENT)

    # ════════════════════════════════════════════════════════════════
    # PDF EXPORT ROUTE (/profile/<uid>/export/pdf)
    # ════════════════════════════════════════════════════════════════

    @app.route("/profile/<uid>/export/pdf")
    @login_required
    def profile_export_pdf(uid):
        """Generate an annual reading report as a printable HTML page."""
        users_data = _storage.load_users()
        user = users_data.get(uid)
        if not user:
            return render_page("Not Found", '<div class="text-center py-5">User not found</div>')

        # Gather stats
        diary_stats = {}
        diary_entries = []
        try:
            if _diary_mgr:
                diary_entries, _ = _diary_mgr.get_user_diary(uid, page=1, per_page=500)
                diary_stats = _diary_mgr.get_stats(uid) if _diary_mgr else {}
        except Exception:
            pass

        reading_stats = {}
        challenge_data = {}
        try:
            reading_stats = _review_mgr.get_user_reading_stats(uid) if _review_mgr else {}
            challenge_data = _challenge.get_goal(uid, datetime.now().year) if _challenge else {}
        except Exception:
            pass

        # Build report
        year = datetime.now().year
        total_books = diary_stats.get("total_books", 0)
        total_pages = diary_stats.get("total_pages_read", 0)
        streak_info = {}
        try:
            streak_info = _gamification.get_user_gamification(uid) if _gamification else {}
        except Exception:
            pass

        entries_html = ""
        for e in diary_entries[-10:]:  # Last 10 entries
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
<h1>\U0001f4da Annual Reading Report</h1>
<p><strong>%s</strong> &middot; @%s &middot; %d</p>

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

    # ════════════════════════════════════════════════════════════════
    # CLUB JOIN/LEAVE API ENDPOINTS
    # ════════════════════════════════════════════════════════════════

    @app.route("/api/clubs/<club_id>/join", methods=["POST"])
    @login_required
    # Abuse ceiling: mass join churn (join notifies members / adds rows).
    # api_club_leave is deliberately left at the 200/min default: it is
    # self-scoped (removes own membership, no cross-user side effects).
    @_rate_limit("60 per minute")
    def api_club_join(club_id):
        uid = session["user_id"]
        ok, msg = (
            _communities.join_club(club_id, uid) if _communities else (False, "Clubs unavailable")
        )
        return jsonify({"success": ok, "message": msg})

    @app.route("/api/clubs/<club_id>/leave", methods=["POST"])
    @login_required
    def api_club_leave(club_id):
        uid = session["user_id"]
        ok, msg = (
            _communities.leave_club(club_id, uid) if _communities else (False, "Clubs unavailable")
        )
        return jsonify({"success": ok, "message": msg})

    return app
