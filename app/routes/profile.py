"""Profile routes — /profile/<uid> and /profile/<uid>/export/pdf."""

import contextlib
import logging
from datetime import datetime

from flask import session

from app.routes.helpers import avatar_html
from app.routes.page_state import (
    challenge,
    diary_mgr,
    gamification,
    h,
    login_required,
    render_page,
    review_mgr,
    storage,
)

logger = logging.getLogger(__name__)


def register_profile_routes(app) -> None:
    """Register profile page and PDF export routes."""

    # ════════════════════════════════════════════════════════════════
    # 1. PROFILE PAGE (/profile/<uid>)
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
    # 2. PROFILE PDF EXPORT (/profile/<uid>/export/pdf)
    # ════════════════════════════════════════════════════════════════

    @app.route("/profile/<uid>/export/pdf")
    @login_required
    def profile_export_pdf(uid):
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
