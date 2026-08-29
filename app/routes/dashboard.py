"""Dashboard route — /dashboard page."""

import logging
from datetime import datetime

from flask import session

from app.routes.helpers import avatar_html, get_current_user
from app.routes.page_state import (
    challenge,
    diary_mgr,
    gamification,
    h,
    login_required,
    render_page,
    storage,
    library_stats,
)

logger = logging.getLogger(__name__)


def register_dashboard_routes(app) -> None:
    """Register the /dashboard route."""

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
