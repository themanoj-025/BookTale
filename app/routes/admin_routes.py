"""
admin_routes.py - Admin routes (admin settings, admin fines).

Extracted from web_app.py to reduce file size and improve maintainability.
"""

import html
import os
from functools import wraps

from flask import g, jsonify, redirect, render_template, request, session, url_for

from app.config.settings import Config
from typing import Any
from collections.abc import Callable


def init_admin_routes(app, storage, lib, auth, notif_mgr) -> None:
    """Register admin routes on the Flask app."""

    def _rate_limit(limit_value: str, **kwargs: Any) -> Any:
        """Rate-limit decorator; no-op fallback if flask-limiter is missing."""
        _lim = app.extensions.get("booktale_limiter")
        if _lim is None:
            return lambda f: f
        return _lim.limit(limit_value, **kwargs)

    def _user_key() -> dict[str, str]:
        uid = session.get("user_id")
        if uid:
            return f"user:{uid}"
        return f"ip:{request.remote_addr}"

    def h(text: object) -> str:
        return html.escape(str(text))

    def _audit_log(admin_id: str, action: str, target: str = "", old_value: Any = None, new_value: Any = None) -> None:
        try:
            import app.db.database as _dbmod
            from app.db.repositories import AuditLogRepository

            with _dbmod.session_scope() as db:
                AuditLogRepository(db).add(
                    admin_id=admin_id,
                    action=action,
                    target=target,
                    old_value=old_value,
                    new_value=new_value,
                    ip_address=request.remote_addr or "",
                    user_agent=request.headers.get("User-Agent", ""),
                )
        except (OSError, ValueError) as e:
            from app.core.logger import log as _log
            _log(
                f"audit write failed (admin={admin_id}, action={action}, "
                f"target={target}): {e}",
                "audit",
            )

    def get_current_user() -> Any:
        if "user_id" not in session:
            return None
        return storage.load_users().get(session["user_id"])

    def render_page(title: str, content: str, **kw: Any) -> str:
        user = get_current_user()
        return render_template(
            "base.html",
            title=title,
            content=content,
            notif_count=notif_mgr.get_unread_count(user.user_id) if user else 0,
            **kw,
        )

    def login_required(f: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(f)
        def d(*a: Any, **k: Any) -> Any:
            if "user_id" not in session:
                return redirect(url_for("login_page"))
            return f(*a, **k)
        return d

    def admin_required(f: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(f)
        def d(*a: Any, **k: Any) -> Any:
            if "user_id" not in session:
                return redirect(url_for("login_page"))
            if session.get("role") != "admin":
                return jsonify({"error": "Admin access required"}), 403
            return f(*a, **k)
        return d

    # ── Admin Settings Page ─────────────────────────────────────────────────

    @app.route("/admin/settings")
    @admin_required
    def admin_settings_page() -> str:
        """Admin settings page for managing system-wide configuration."""
        from app.config.settings import Config as C

        issue_d = C.ISSUE_DAYS
        fine_d = C.FINE_PER_DAY
        max_b = C.MAX_BORROW_LIMIT
        mem_v = C.MEMBERSHIP_VALIDITY_DAYS
        max_u = C.MAX_UPLOAD_SIZE // (1024 * 1024)
        ext_s = ", ".join(sorted(C.ALLOWED_EXTENSIONS))
        smtp_h = C.SMTP_HOST
        smtp_p = C.SMTP_PORT
        smtp_u = C.SMTP_USER
        smtp_f = C.SMTP_FROM
        lib_n = C.LIBRARY_NAME
        email_en = C.EMAIL_NOTIFICATIONS_ENABLED

        CONTENT = """<div class="animate-in">
<div class="glass-card p-0 mb-4" style="overflow:hidden;">
    <div class="p-4" style="background:linear-gradient(135deg,#7c3aed,#4f46e5);color:white;">
        <h4 class="fw-bold mb-0"><i class="bi bi-shield-lock-fill me-2"></i> Admin Settings</h4>
        <p class="mb-0" style="opacity:.8;font-size:.85rem;">System-wide configuration</p>
    </div>
</div>

<form id="adminSettingsForm" onsubmit="return saveAdminSettings()">
    <div class="glass-card p-4 mb-3">
        <h5 class="fw-bold mb-3"><i class="bi bi-building text-primary me-2"></i>Library Information</h5>
        <div class="row">
            <div class="col-md-6 mb-3">
                <label class="form-label">Library Name</label>
                <input type="text" class="form-control" id="aLibName" value="%s">
            </div>
            <div class="col-md-6 mb-3">
                <label class="form-label">Email From Address</label>
                <input type="email" class="form-control" id="aSmtpFrom" value="%s">
            </div>
        </div>
    </div>

    <div class="glass-card p-4 mb-3">
        <h5 class="fw-bold mb-3"><i class="bi bi-arrow-left-right text-success me-2"></i>Loan & Fine Policy</h5>
        <div class="row">
            <div class="col-md-3 mb-3">
                <label class="form-label">Issue Days</label>
                <input type="number" class="form-control" id="aIissueDays" value="%d" min="1" max="365">
                <small class="text-muted">Days per checkout</small>
            </div>
            <div class="col-md-3 mb-3">
                <label class="form-label">Fine per Day (&#8377;)</label>
                <input type="number" class="form-control" id="aFinePerDay" value="%s" min="0" step="0.5">
                <small class="text-muted">Late fee rate</small>
            </div>
            <div class="col-md-3 mb-3">
                <label class="form-label">Max Borrow Limit</label>
                <input type="number" class="form-control" id="aMaxBorrow" value="%d" min="1" max="50">
                <small class="text-muted">Books per user</small>
            </div>
            <div class="col-md-3 mb-3">
                <label class="form-label">Membership Validity</label>
                <input type="number" class="form-control" id="aMemValidity" value="%d" min="30" max="3650">
                <small class="text-muted">Days</small>
            </div>
        </div>
    </div>

    <div class="glass-card p-4 mb-3">
        <h5 class="fw-bold mb-3"><i class="bi bi-cloud-upload-fill text-info me-2"></i>Upload Settings</h5>
        <div class="row">
            <div class="col-md-6 mb-3">
                <label class="form-label">Max Upload Size (MB)</label>
                <input type="number" class="form-control" id="aMaxUpload" value="%d" min="1" max="100">
            </div>
            <div class="col-md-6 mb-3">
                <label class="form-label">Allowed Extensions</label>
                <input type="text" class="form-control" id="aAllowedExt" value="%s">
                <small class="text-muted">Comma-separated (e.g. .jpg,.png,.gif)</small>
            </div>
        </div>
    </div>

    <div class="glass-card p-4 mb-3">
        <h5 class="fw-bold mb-3"><i class="bi bi-envelope-fill text-warning me-2"></i>SMTP / Email Settings</h5>
        <div class="row">
            <div class="col-md-4 mb-3">
                <label class="form-label">SMTP Host</label>
                <input type="text" class="form-control" id="aSmtpHost" value="%s" placeholder="smtp.gmail.com">
            </div>
            <div class="col-md-2 mb-3">
                <label class="form-label">SMTP Port</label>
                <input type="number" class="form-control" id="aSmtpPort" value="%d" min="1" max="65535">
            </div>
            <div class="col-md-3 mb-3">
                <label class="form-label">SMTP User</label>
                <input type="text" class="form-control" id="aSmtpUser" value="%s" placeholder="your@email.com">
            </div>
            <div class="col-md-3 mb-3">
                <label class="form-label">SMTP Password</label>
                <input type="password" class="form-control" id="aSmtpPass" placeholder="App password">
                <small class="text-muted">Leave blank to keep current</small>
            </div>
        </div>
        <div class="d-flex align-items-center gap-3">
            <label class="form-label mb-0">Email Notifications</label>
            <label class="toggle-switch">
                <input type="checkbox" id="aEmailEnabled" %s>
                <span class="toggle-slider"></span>
            </label>
            <span class="small text-muted">Enable/disable all email notifications</span>
        </div>
    </div>

    <div class="glass-card p-4 mb-3">
        <h5 class="fw-bold mb-3"><i class="bi bi-key-fill text-danger me-2"></i>Admin Credentials</h5>
        <div class="row">
            <div class="col-md-6 mb-3">
                <label class="form-label">Current Admin Password</label>
                <input type="password" class="form-control" id="aCurPw" placeholder="Enter current password to save changes">
                <small class="text-muted">Required to save admin settings</small>
            </div>
            <div class="col-md-6 mb-3">
                <label class="form-label">New Admin Password <span class="text-muted">(optional)</span></label>
                <input type="password" class="form-control" id="aNewAdminPw" placeholder="Leave blank to keep current" minlength="6">
            </div>
        </div>
    </div>

    <button type="submit" class="btn btn-primary btn-lg w-100"><i class="bi bi-check-lg me-2"></i> Save All Admin Settings</button>
</form>
</div>
""" % (
            h(lib_n),
            h(smtp_f),
            issue_d,
            f"{fine_d:.1f}",
            max_b,
            mem_v,
            max_u,
            h(ext_s),
            h(smtp_h),
            smtp_p,
            h(smtp_u),
            "checked" if email_en else "",
        )

        return render_page(
            "Admin Settings",
            CONTENT
            + """
<style>
.toggle-switch{position:relative;display:inline-block;width:44px;height:24px;flex-shrink:0}
.toggle-switch input{opacity:0;width:0;height:0}
.toggle-slider{position:absolute;cursor:pointer;inset:0;background:var(--border);border-radius:24px;transition:.3s}
.toggle-slider::before{content:"";position:absolute;height:18px;width:18px;left:3px;bottom:3px;background:white;border-radius:50%;transition:.3s;box-shadow:0 1px 3px rgba(0,0,0,.15)}
.toggle-switch input:checked+.toggle-slider{background:var(--primary)}
.toggle-switch input:checked+.toggle-slider::before{transform:translateX(20px)}
</style>
<script>
function saveAdminSettings() {
    var btn = document.querySelector("#adminSettingsForm .btn-primary");
    btn.disabled = true; btn.innerHTML = "<span class='spinner-border spinner-border-sm'></span> Saving...";
    var data = {
        library_name: document.getElementById("aLibName").value.trim(),
        smtp_from: document.getElementById("aSmtpFrom").value.trim(),
        issue_days: parseInt(document.getElementById("aIissueDays").value) || 14,
        fine_per_day: parseFloat(document.getElementById("aFinePerDay").value) || 5,
        max_borrow_limit: parseInt(document.getElementById("aMaxBorrow").value) || 3,
        membership_validity_days: parseInt(document.getElementById("aMemValidity").value) || 365,
        max_upload_size: (parseInt(document.getElementById("aMaxUpload").value) || 5) * 1024 * 1024,
        allowed_extensions: document.getElementById("aAllowedExt").value.trim(),
        smtp_host: document.getElementById("aSmtpHost").value.trim(),
        smtp_port: parseInt(document.getElementById("aSmtpPort").value) || 587,
        smtp_user: document.getElementById("aSmtpUser").value.trim(),
        smtp_password: document.getElementById("aSmtpPass").value,
        email_notifications_enabled: document.getElementById("aEmailEnabled").checked,
        current_admin_password: document.getElementById("aCurPw").value,
        new_admin_password: document.getElementById("aNewAdminPw").value
    };
    if(!data.current_admin_password) {
        showToast("Enter your current password to save admin settings", "error");
        btn.disabled = false; btn.innerHTML = "<i class='bi bi-check-lg'></i> Save All Admin Settings";
        return false;
    }
    fetch("/api/admin/settings/save", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(data)
    }).then(function(r){ return r.json() }).then(function(d){
        btn.disabled = false; btn.innerHTML = "<i class='bi bi-check-lg'></i> Save All Admin Settings";
        if(d.success) { showToast("Admin settings saved!", "success"); setTimeout(function(){ location.reload(); }, 1000); }
        else showToast(d.error || "Failed", "error");
    }).catch(function(){ btn.disabled = false; btn.innerHTML = "<i class='bi bi-check-lg'></i> Save All Admin Settings"; });
    return false;
}
</script>
""",
        )

    # ── Admin Settings Save API ─────────────────────────────────────────────

    @app.route("/api/admin/settings/save", methods=["POST"])
    @admin_required
    @_rate_limit(
        "10 per minute",
        key_func=_user_key,
        deduct_when=lambda response: getattr(g, "_admin_pw_failed", False),
    )
    def api_save_admin_settings() -> dict[str, str]:
        """Save admin settings to settings_override.json."""
        data = request.get_json() or {}

        from app.services.auth.auth import hash_password as _hp
        from app.services.auth.auth import verify_password as _vp

        uid = session["user_id"]
        users = storage.load_users()
        admin = users.get(uid)
        if not admin:
            return jsonify({"success": False, "error": "Admin not found"})
        cur_pw = data.get("current_admin_password", "")
        if not cur_pw or not _vp(cur_pw, admin.password_hash):
            g._admin_pw_failed = True
            _audit_log(uid, "auth.failed", "admin_password", new_value="attempt rejected")
            return jsonify({"success": False, "error": "Current password is incorrect"})

        override = {}
        mapping = {
            "library_name": "LIBRARY_NAME",
            "smtp_from": "SMTP_FROM",
            "issue_days": "ISSUE_DAYS",
            "fine_per_day": "FINE_PER_DAY",
            "max_borrow_limit": "MAX_BORROW_LIMIT",
            "membership_validity_days": "MEMBERSHIP_VALIDITY_DAYS",
            "max_upload_size": "MAX_UPLOAD_SIZE",
            "allowed_extensions": "ALLOWED_EXTENSIONS",
            "smtp_host": "SMTP_HOST",
            "smtp_port": "SMTP_PORT",
            "smtp_user": "SMTP_USER",
            "email_notifications_enabled": "EMAIL_NOTIFICATIONS_ENABLED",
        }
        for key, cfg_key in mapping.items():
            if key in data:
                override[cfg_key] = data[key]
                old_val = getattr(Config, cfg_key, None)
                _audit_log(
                    uid,
                    "settings.update",
                    cfg_key,
                    old_value=str(old_val) if old_val is not None else None,
                    new_value=str(data[key]),
                )

        if data.get("smtp_password"):
            override["SMTP_PASSWORD"] = data["smtp_password"]
            _audit_log(
                uid,
                "settings.update",
                "SMTP_PASSWORD",
                old_value=None,
                new_value="[redacted]",
            )

        if data.get("new_admin_password"):
            npw = data["new_admin_password"]
            if len(npw) >= 6:
                admin.password_hash = _hp(npw)
                from app.core.logger import log
                log("Admin password changed via admin settings", uid)
                _audit_log(
                    uid,
                    "admin.password_change",
                    "ADMIN_PASSWORD",
                    old_value=None,
                    new_value="[redacted]",
                )

        import json as _json
        os.makedirs(Config.DATA_DIR, exist_ok=True)
        override_path = os.path.join(Config.DATA_DIR, "settings_override.json")
        with open(override_path, "w", encoding="utf-8") as f:
            _json.dump(override, f, indent=2)

        storage.save_users(users)
        from app.core.logger import log
        log("Admin settings saved", uid)
        return jsonify(
            {
                "success": True,
                "message": "Admin settings saved. Some changes may require a restart.",
            }
        )

    # ── Admin Fines Page ────────────────────────────────────────────────────

    @app.route("/admin/fines")
    @login_required
    @admin_required
    def admin_fines_page() -> str:
        """Admin fines management page."""
        fines = storage.load_fines()
        users = storage.load_users()
        total_fines = sum(f.get("amount", 0) for f in fines)
        paid = sum(f.get("amount", 0) for f in fines if f.get("paid"))
        pending = total_fines - paid

        rows = ""
        for f in sorted(fines, key=lambda x: x.get("created_at", ""), reverse=True)[:100]:
            u = users.get(f.get("user_id", ""))
            uname = h(u.name) if u else h(f.get("user_id", ""))
            paid_badge = (
                '<span class="badge bg-success">Paid</span>'
                if f.get("paid")
                else '<span class="badge bg-warning text-dark">Pending</span>'
            )
            rows += """<tr>
            <td>{}</td>
            <td><a href="/profile/{}" class="fw-bold text-decoration-none">{}</a></td>
            <td>&#8377; {:.2f}</td>
            <td>{}</td>
            <td>{}</td>
        </tr>""".format(
                paid_badge,
                h(f["user_id"]),
                uname,
                f.get("amount", 0),
                f.get("reason", "")[:40],
                f.get("created_at", "")[:10],
            )
        if not rows:
            rows = (
                '<tr><td colspan="5" class="text-center text-muted py-4">No fines recorded.</td></tr>'
            )

        CONTENT = """<div class="animate-in">
    <div class="glass-card p-0 mb-3" style="overflow:hidden;">
        <div class="p-3" style="background:linear-gradient(135deg,#7c3aed,#4f46e5);color:white;">
            <h4 class="fw-bold mb-0"><i class="bi bi-currency-rupee me-2"></i>Fines Management</h4>
            <p class="mb-0" style="opacity:.8;font-size:.85rem;">Track and manage library fines</p>
        </div>
    </div>
    <div class="stats-bar mb-3">
        <div class="stat-item"><div class="num">%d</div><div class="desc">Total Fines</div></div>
        <div class="stat-item"><div class="num text-warning">&#8377; %.2f</div><div class="desc">Pending</div></div>
        <div class="stat-item"><div class="num text-success">&#8377; %.2f</div><div class="desc">Collected</div></div>
    </div>
    <div class="glass-card p-0" style="overflow-x:auto;">
        <table class="table table-hover mb-0"><thead><tr>
            <th>Status</th><th>User</th><th>Amount</th><th>Reason</th><th>Date</th>
        </tr></thead><tbody>ROWS_HTML</tbody></table>
    </div>
</div>""" % (
            len(fines),
            pending,
            paid,
        )
        CONTENT = CONTENT.replace("ROWS_HTML", rows)
        return render_page("Fines Management", CONTENT)
