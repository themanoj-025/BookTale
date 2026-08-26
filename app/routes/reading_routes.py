"""
reading_routes.py - Reading tracking page routes.

Routes: /shelves, /reading-calendar, /analytics
"""

import json as _json
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import request, session

from app.routes.helpers import cat_color
from app.routes.page_state import (
    challenge,
    diary_mgr,
    h,
    login_required,
    reading_progress,
    render_page,
    review_mgr,
    storage,
)


def init_reading_routes(app) -> None:
    """Register reading tracking routes on the Flask app."""

    # ════════════════════════════════════════════════════════════════
    # 1. SHELVES PAGE (/shelves)
    # ════════════════════════════════════════════════════════════════

    @app.route("/shelves")
    @login_required
    def shelves_page():
        uid = session["user_id"]
        tab = request.args.get("tab", "want_to_read")
        shelves_data = review_mgr.get_user_shelf(uid) if review_mgr else []
        shelf_counts = review_mgr.get_shelf_counts(uid) if review_mgr else {}
        custom_shelves = review_mgr.get_user_custom_shelves(uid) if review_mgr else []
        books_data = storage.load_books()

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
                users_data = storage.load_users()
                user = users_data.get(uid)
                count = len(user.favorite_books) if user else 0
            elif sid == "dnf":
                count = 0
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
            users_data = storage.load_users()
            user = users_data.get(uid)
            fav_ids = user.favorite_books if user else []
            fav_books = []
            for bid in fav_ids:
                b = books_data.get(bid)
                if b and not b.is_deleted:
                    fav_books.append(b)
            for b in fav_books:
                cc = cat_color(b.category)
                books_html += f"""<div class="col-6 col-md-4 col-lg-3 mb-2">
                    <div class="glass-card p-2 text-center h-100" draggable="true">
                        <div style="width:40px;height:56px;border-radius:8px;background:linear-gradient(135deg,{cc},{cc}dd);display:flex;align-items:center;justify-content:center;margin:0 auto .3rem;">
                            <i class="bi bi-book-fill" style="color:white;font-size:.9rem;"></i></div>
                        <div style="font-size:.75rem;font-weight:600;">{h(b.title[:35])}</div>
                        <small style="font-size:.6rem;color:var(--text-muted);">{h(b.author[:20])}</small>
                        <div class="mt-1"><button class="btn btn-sm btn-outline" onclick="removeFromShelf('{h(b.book_id)}')"><i class="bi bi-x"></i></button></div>
                    </div></div>"""
            if not books_html:
                books_html = """<div class="col-12"><div class="empty-state py-4"><div class="empty-icon"><i class="bi bi-star" style="font-size:2rem;"></i></div><h5>No favorites yet</h5><p class="text-muted small">Search to add your favorite books!</p><button class="btn btn-primary btn-sm" onclick="openSearchOverlay()"><i class="bi bi-search"></i> Find Books</button></div></div>"""
        else:
            tab_books = [s for s in shelves_data if s["shelf"] == tab]
            for s in tab_books:
                b = books_data.get(s["book_id"])
                if not b or b.is_deleted:
                    continue
                cc = cat_color(b.category)
                books_html += f"""<div class="col-6 col-md-4 col-lg-3 mb-2">
                    <div class="glass-card p-2 text-center h-100">
                        <a href="/books/{h(b.book_id)}" style="text-decoration:none;color:inherit;">
                            <div style="width:40px;height:56px;border-radius:8px;background:linear-gradient(135deg,{cc},{cc}dd);display:flex;align-items:center;justify-content:center;margin:0 auto .3rem;">
                                <i class="bi bi-book-fill" style="color:white;font-size:.9rem;"></i></div>
                            <div style="font-size:.75rem;font-weight:600;">{h(b.title[:35])}</div>
                            <small style="font-size:.6rem;color:var(--text-muted);">{h(b.author[:20])}</small>
                        </a>
                        <div class="mt-1"><button class="btn btn-sm btn-outline" onclick="removeFromShelf('{h(b.book_id)}')"><i class="bi bi-x"></i></button></div>
                    </div></div>"""

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
                cs_books_html += f"""<div class="col-3 col-md-2 mb-1">
                    <div class="glass-card p-1 text-center" style="cursor:pointer;" onclick="window.location.href='/books/{h(b.book_id)}'">
                        <div style="width:30px;height:40px;border-radius:4px;background:linear-gradient(135deg,{cc},{cc}dd);display:flex;align-items:center;justify-content:center;margin:0 auto .2rem;">
                            <i class="bi bi-book-fill" style="color:white;font-size:.6rem;"></i></div>
                        <div style="font-size:.55rem;font-weight:600;line-height:1.1;">{h(b.title[:20])}</div>
                    </div></div>"""
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
    # 2. READING CALENDAR PAGE (/reading-calendar)
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
                diary_mgr.get_user_diary(uid, page=1, per_page=5000) if diary_mgr else ([], 0)
            )
            diary_entries = all_entries
        except (AttributeError, TypeError, KeyError):
            pass

        # Build date->count map
        date_counts = defaultdict(int)
        for e in diary_entries:
            try:
                dr = e.get("date_read", "")
                if dr[:4] == str(year):
                    date_counts[dr[:10]] += 1
            except (ValueError, TypeError):
                pass

        # Generate calendar grid
        today = date.today()

        MONTHS = [
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        ]

        months_html = ""
        for m in range(1, 13):
            if year > today.year and m > today.month:
                break
            first = date(year, m, 1)
            last = date(year, 12, 31) if m == 12 else date(year, m + 1, 1) - timedelta(days=1)

            month_name = MONTHS[m - 1]
            cells = ""
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
                if d.weekday() == 6:
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

        stats = diary_mgr.get_stats(uid) if diary_mgr else {}

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
    # 3. READING ANALYTICS PAGE (/analytics)
    # ════════════════════════════════════════════════════════════════

    @app.route("/analytics")
    @login_required
    def analytics_page():
        uid = session["user_id"]

        # Gather data
        diary_stats = diary_mgr.get_stats(uid) if diary_mgr else {}
        progress_stats = reading_progress.get_reading_stats(uid) if reading_progress else {}
        challenge_data = challenge.get_goal(uid, datetime.now().year) if challenge else {}
        shelf_counts = review_mgr.get_shelf_counts(uid) if review_mgr else {}
        reading_stats = review_mgr.get_user_reading_stats(uid) if review_mgr else {}

        # Prepare chart data as JSON for JS
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

    return app
