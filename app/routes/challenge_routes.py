"""
challenge_routes.py - Reading Challenge pages and API endpoints.
Extracted from feature_routes.py for focused maintenance.
"""

import json
from datetime import datetime

from flask import jsonify, request, session

from app.routes.feature_shared import _challenge, h, _avatar_html as avatar_html


def register_challenge_routes(app, login_required, render_page, _rate_limit) -> None:
    """Register reading challenge routes on *app*."""

    @app.route("/reading-challenge")
    @login_required
    def reading_challenge_page() -> str:
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
            LB += (
                '<div class="d-flex align-items-center gap-2 mb-2">'
                '<span style="width:28px;text-align:center;font-weight:700;">' + medal + '</span>'
                + lb_avatar +
                '<div class="flex-grow-1" style="min-width:0;">'
                '<div class="fw-bold small">' + h(entry["name"]) + '</div>'
                '<div class="progress-thin"><div class="bar" style="width:' + str(lb_bar_w) + '%;background:' + lb_bar_c + ';"></div></div>'
                '</div>'
                '<small class="fw-bold">' + str(entry["count"]) + '/' + str(entry.get("goal") or "—") + '</small>'
                '</div>'
            )
        if not LB:
            LB = '<div class="text-center text-muted small py-3">No data yet. Start reading!</div>'

        YEAR_SELECTOR = ""
        for y in range(year - 2, year + 1):
            cls = "btn-primary" if y == year else "btn-outline"
            yr_label = ("📅 " if y == datetime.now().year else "") + str(y)
            YEAR_SELECTOR += '<a href="/reading-challenge?year=' + str(y) + '" class="btn ' + cls + ' btn-sm">' + yr_label + '</a>'

        CONTENT = (
            '<div class="animate-in">'
            '<div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">'
            '<h4 class="fw-bold mb-0"><i class="bi bi-trophy-fill me-2 text-warning"></i>Reading Challenge</h4>'
            '<div class="d-flex gap-1">' + YEAR_SELECTOR + '</div>'
            '</div>'
            '<div class="row mb-3">'
            '<div class="col-lg-8 mb-3">'
            '<div class="glass-card p-4">'
            '<div class="d-flex justify-content-between align-items-start mb-3">'
            '<div>'
            '<h5 class="fw-bold mb-1">' + str(year) + ' Reading Goal</h5>'
            '<p class="text-muted small mb-0">' + str(len(chart.get("monthly", []))) + ' months of data</p>'
            '</div>'
            '<div class="text-end">'
            '<div style="font-size:2rem;font-weight:800;color:var(--primary);">' + str(goal.get("progress", 0)) + '<span style="font-size:1rem;color:var(--text-muted);">/' + str(goal.get("goal", 0)) + '</span></div>'
            '<div class="small text-muted">books read</div>'
            '</div>'
            '</div>'
            '<div class="progress-thin mb-3" style="height:12px;border-radius:6px;">'
            '<div class="bar" style="width:' + str(progress_pct) + '%;background:' + progress_bar_color + ';height:12px;border-radius:6px;"></div>'
            '</div>'
            '<div class="d-flex justify-content-between align-items-center">'
            '<div class="d-flex gap-2 flex-wrap">'
            '<span class="badge" style="background:var(--primary)20;color:var(--primary);">📈 Pace: ' + str(goal.get("pace", 0)) + '/mo</span>'
            '<span class="badge" style="background:#10b98120;color:#10b981;">📊 Projected: ' + str(goal.get("projected_total", 0)) + '</span>'
            + on_track_badge +
            '</div>'
            '<div class="d-flex gap-1">'
            '<button class="btn btn-primary btn-sm" onclick="setReadingGoal()"><i class="bi bi-pencil"></i> Set Goal</button>'
            '</div>'
            '</div>'
            '<hr style="border-color:var(--border);">'
            '<div class="row text-center">'
            '<div class="col-4"><span class="fw-bold text-success">' + str(goal.get("progress", 0)) + '</span><br><small class="text-muted">Read</small></div>'
            '<div class="col-4"><span class="fw-bold text-warning">' + str(goal.get("remaining", 0)) + '</span><br><small class="text-muted">Remaining</small></div>'
            '<div class="col-4"><span class="fw-bold text-info">' + str(goal.get("days_remaining", 0)) + '</span><br><small class="text-muted">Days Left</small></div>'
            '</div>'
            '</div>'
            '</div>'
            '<div class="col-lg-4 mb-3">'
            '<div class="glass-card p-3 h-100">'
            '<div class="section-title"><i class="bi bi-trophy-fill text-warning"></i> Leaderboard ' + str(year) + '</div>'
            '<div style="max-height:350px;overflow-y:auto;">' + LB + '</div>'
            '</div>'
            '</div>'
            '</div>'
            '<div class="glass-card p-3 mb-3 animate-d1">'
            '<div class="section-title"><i class="bi bi-graph-up-arrow text-primary"></i> Monthly Progress</div>'
            '<div class="chart-container" style="height:250px;"><canvas id="challengeChart"></canvas></div>'
            '</div>'
            '<div class="glass-card p-3 animate-d2">'
            '<div class="section-title"><i class="bi bi-calendar-check"></i> Past Challenges</div>'
            '<div class="row g-2">'
        )
        for y in summary.get("years", []):
            CONTENT += (
                '<div class="col-md-4"><div class="glass-card p-3 text-center">'
                '<div class="fw-bold">' + str(y["year"]) + '</div>'
                '<div class="progress-thin mt-2"><div class="bar" style="width:' + str(y["percentage"]) + '%;background:var(--primary);"></div></div>'
                '<div class="mt-1"><span class="fw-bold">' + str(y["progress"]) + '</span><small class="text-muted">/' + str(y["goal"]) + '</small></div>'
                '</div></div>'
            )
        CONTENT += '</div></div></div>'

        # Chart.js data
        chart_js = ""
        if chart and chart.get("monthly"):
            months_json = json.dumps(chart["labels"])
            monthly_json = json.dumps(chart["monthly"])
            cumul_json = json.dumps(chart["cumulative"])
            chart_js = (
                "new Chart(document.getElementById('challengeChart'), {"
                "type: 'bar',"
                "data: {labels: " + months_json + ",datasets:[{"
                "label: 'Books Read',data: " + monthly_json + ","
                "backgroundColor: 'rgba(79,70,229,0.6)',borderColor: '#4f46e5',borderWidth: 2,borderRadius: 4,order: 2"
                "},{label: 'Cumulative',data: " + cumul_json + ","
                "type: 'line',borderColor: '#10b981',backgroundColor: 'rgba(16,185,129,0.1)',"
                "fill: true,tension: .3,pointRadius: 3,pointBackgroundColor: '#10b981',borderWidth: 2,order: 1"
                "}]},"
                "options: {responsive: true,maintainAspectRatio: false,"
                "plugins: {legend: {position: 'bottom',labels: {boxWidth: 10,font: {size: 10}}}},"
                "scales: {y: {beginAtZero: true,grid: {color: 'rgba(0,0,0,0.04)'},ticks: {stepSize: 1}},x: {grid: {display: false}}}}"
                "});"
            )

        goal_val = goal.get("goal", 0)
        CONTENT += (
            '<script>'
            'function setReadingGoal(){'
            'var current=' + str(goal_val) + ';'
            'var g=prompt("How many books do you want to read in ' + str(year) + '?",current||12);'
            "if(g&&parseInt(g)>0){"
            "fetch('/api/reading-challenge/goal',{"
            "method:'POST',headers:{'Content-Type':'application/json'},"
            "body:JSON.stringify({goal:parseInt(g),year:" + str(year) + "})"
            "}).then(r=>r.json()).then(function(d){"
            "if(d.success){showToast(d.message,'success');setTimeout(function(){location.reload()},1200)}"
            "else{showToast(d.error,'error')}"
            "});}}"
            '}' + chart_js +
            '</script>'
        )
        return render_page("Reading Challenge", CONTENT)

    @app.route("/api/reading-challenge/goal", methods=["POST"])
    @login_required
    def api_set_reading_goal() -> Response:
        uid = session["user_id"]
        data = request.get_json() or {}
        goal = int(data.get("goal", 12))
        year = int(data.get("year", datetime.now().year))
        ok, msg = _challenge.set_goal(uid, year, goal)
        return jsonify({"success": ok, "message": msg})

    @app.route("/api/reading-challenge/progress")
    @login_required
    def api_reading_progress_data() -> Response:
        uid = session["user_id"]
        year = int(request.args.get("year", datetime.now().year))
        goal = _challenge.get_goal(uid, year)
        chart = _challenge.get_progress_chart_data(uid, year)
        return jsonify({"goal": goal, "chart": chart})

    @app.route("/api/reading-challenge/leaderboard")
    @login_required
    def api_reading_leaderboard() -> Response:
        year = int(request.args.get("year", datetime.now().year))
        top_n = min(int(request.args.get("top_n", 10)), 50)
        return jsonify({"leaderboard": _challenge.get_leaderboard(year, top_n)})

    @app.route("/api/reading-challenge/stats")
    @login_required
    def api_reading_challenge_stats() -> Response:
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
