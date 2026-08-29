"""Gamification route — /gamification page."""

import logging

from flask import session

from app.routes.helpers import avatar_html
from app.routes.page_state import gamification, h, login_required, render_page

logger = logging.getLogger(__name__)


def register_gamification_routes(app) -> None:
    """Register the /gamification route."""

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
