"""
admin_page_routes.py - Admin page routes.

Routes: /admin/users, /admin/audit, /admin/overdue, /reports
"""

from collections import Counter
from datetime import datetime, timedelta

from flask import request, session

from app.routes.helpers import avatar_html
from app.routes.page_state import (
    admin_required,
    h,
    login_required,
    notif_mgr,
    render_page,
    storage,
    library_stats,
)


def init_admin_page_routes(app) -> None:
    """Register admin page routes on the Flask app."""

    # ════════════════════════════════════════════════════════════════
    # 1. ADMIN USERS PAGE (/admin/users)
    # ════════════════════════════════════════════════════════════════

    @app.route("/admin/users")
    @login_required
    @admin_required
    def admin_users_page() -> str:
        users_data = storage.load_users()
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

        fines = storage.load_fines() if hasattr(storage, "load_fines") else []
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
                <small class="text-muted">%.2f%%</small>
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
                <td>{}</td>
                <td><div class="d-flex align-items-center gap-2"><div>{}</div><div><div class="fw-bold small">{}</div><small class="text-muted">@{}</small></div></div></td>
                <td>{}</td>
                <td><span class="{}">{}</span></td>
                <td><span class="{}">{}</span></td>
                <td><span class="fw-bold">&#8377;{:.0f}</span></td>
                <td><a href="/profile/{}" class="btn btn-sm btn-outline"><i class="bi bi-eye"></i></a></td>
            </tr>""".format(
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

    # ════════════════════════════════════════════════════════════════
    # 2. ADMIN AUDIT PAGE (/admin/audit)
    # ════════════════════════════════════════════════════════════════

    @app.route("/admin/audit")
    @login_required
    @admin_required
    def admin_audit_page() -> str:
        import app.db.database as _dbmod
        from app.db.repositories import AuditLogRepository
        from urllib.parse import urlencode

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
        except (TypeError, KeyError, AttributeError) as e:
            logger.warning("admin audit page query failed: %s", e)
            rows, total = [], 0

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
                <td class="text-nowrap small">{}</td>
                <td><span class="fw-bold small">{}</span></td>
                <td><span class="{}">{}</span></td>
                <td class="small"><code>{}</code></td>
                <td class="small text-muted">{}</td>
                <td class="small text-muted">{}</td>
                <td class="small text-muted text-nowrap">{}</td>
            </tr>""".format(
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
    # 3. ADMIN OVERDUE PAGE (/admin/overdue)
    # ════════════════════════════════════════════════════════════════

    @app.route("/admin/overdue")
    @login_required
    @admin_required
    def admin_overdue_page() -> str:
        txns = storage.load_transactions()
        books_data = storage.load_books()
        users_data = storage.load_users()
        now = datetime.now()

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
                except (TypeError, KeyError, ValueError):
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
                + ("{:.2f}".format(o["fine"]))
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
    # 4. REPORTS PAGE (/reports)
    # ════════════════════════════════════════════════════════════════

    @app.route("/reports")
    @login_required
    @admin_required
    def reports_page() -> str:
        s = library_stats()

        return render_template(
            "reports.html",
            title="Reports & Analytics",
            session=session,
            notif_count=(
                notif_mgr.get_unread_count(session.get("user_id")) if session.get("user_id") else 0
            ),
            s=s,
        )

    return app
