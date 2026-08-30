"""settings_pages.py - Large inline page content extracted from web_app.py.

Contains the settings page, help page, and security page which are mostly
static HTML with Jinja-style template replacements.
"""

import html as _html

from flask import session



def _h(text: object) -> str:
    """HTML-escape helper (local copy to avoid circular import)."""
    return _html.escape(str(text))


# ════════════════════════════════════════════════════════════════════════════
# Security trust page
# ════════════════════════════════════════════════════════════════════════════


def security_page(render_page_func) -> str:
    """Render the security & trust information page."""
    items = [
        ("🔑", "Password hashing", "Passwords are stored as bcrypt hashes; the policy requires 12+ characters, enforced server-side on every password surface (registration, reset, settings)."),
        ("🛡️", "Role-safe registration", 'Self-service registration can only ever create "user" accounts — client-supplied admin/librarian roles are silently downgraded.'),
        ("🎫", "CSRF protection", "CSRFProtect is enabled by default; every state-changing POST without a valid session token is rejected (400)."),
        ("⏱️", "Rate limiting", "Auth endpoints and all shared-surface writes are rate-limited (per-IP and per-account), so brute-force and spam attempts are throttled without locking real users out."),
        ("🔒", "Fail-fast boot", "The app refuses to boot with a default/empty SECRET_KEY or debug mode outside development."),
        ("📄", "Secure sessions", "Session cookies are HttpOnly + SameSite=Lax (Secure when deployed over HTTPS); HSTS headers are applied on the edge."),
        ("🎨", "Upload verification", "Image uploads are magic-byte verified with Pillow and re-encoded server-side — a renamed HTML/JS file is rejected, and embedded payloads are stripped."),
        ("⏳", "One-time tokens", "Password-reset (15 min) and email-verify (24 h) tokens are stored in the database with explicit expiry; they survive restarts and are consumed once."),
        ("📋", "Audit trail", "Every admin-settings change is recorded (who/what/when/from-where) in an append-only audit log; secrets are redacted."),
        ("🧪", "Security regression tests", "Privilege escalation, CSRF, rate limiting, XSS round-trips, upload forgery, and token expiry all have automated regression tests (tests/security/)."),
    ]
    cards = "".join(
        f'<div class="col-md-6"><div class="glass-card p-4 h-100"><div style="font-size:1.8rem;margin-bottom:.5rem;">{icon}</div>'
        f'<h5 class="fw-bold mb-2">{title}</h5><p class="mb-0" style="font-size:.9rem;color:var(--text-muted);">{_h(desc)}</p></div></div>'
        for icon, title, desc in items
    )
    CONTENT = (
        '<div class="animate-in">'
        '<div class="glass-card p-0 mb-4" style="overflow:hidden;">'
        '<div class="p-4" style="background:linear-gradient(135deg,#059669,#0d9488);color:white;">'
        '<h4 class="fw-bold mb-0"><i class="bi bi-shield-check me-2"></i> Security at BookTale</h4>'
        '<p class="mb-0" style="opacity:.85;font-size:.85rem;">How this platform protects accounts, data, and the community — every item is implemented and regression-tested.</p>'
        "</div></div>"
        '<div class="row g-3">' + cards + "</div>"
        '<p class="text-muted small mt-4">See <a href="/api/docs" class="text-decoration-none">API docs</a> and '
        '<a href="/features" class="text-decoration-none">features</a> — security notes are also in docs/SECURITY.md.</p>'
        "</div>"
    )
    return render_page_func("Security & Trust", CONTENT)


# ════════════════════════════════════════════════════════════════════════════
# Help page
# ════════════════════════════════════════════════════════════════════════════


def help_page(render_page_func) -> str:
    """Render the help & support page."""
    CONTENT = '<div class="animate-in">'
    CONTENT += '<div class="glass-card p-0 mb-4" style="overflow:hidden;">'
    CONTENT += '<div class="p-4" style="background:linear-gradient(135deg,var(--primary),#7c3aed);color:white;">'
    CONTENT += '<h4 class="fw-bold mb-0"><i class="bi bi-question-circle-fill me-2"></i> Help &amp; Support</h4>'
    CONTENT += '<p class="mb-0" style="opacity:.8;font-size:.85rem;">Guides, tips, and frequently asked questions</p>'
    CONTENT += "</div></div>"
    CONTENT += '<div class="row g-4">'
    CONTENT += '<div class="col-md-6"><div class="glass-card p-4">'
    CONTENT += '<h5 class="fw-bold mb-3"><i class="bi bi-book-fill text-primary me-2"></i>Getting Started</h5>'
    CONTENT += '<ul class="list-unstyled" style="font-size:.9rem;">'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-primary me-2"></i> Browse and search books from the Explore page</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-primary me-2"></i> Issue books from the book details page</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-primary me-2"></i> Write reviews and rate books you have read</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-primary me-2"></i> Connect with other readers in the community</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-primary me-2"></i> Create reading lists and track your progress</li>'
    CONTENT += "</ul></div>"
    CONTENT += '<div class="glass-card p-4">'
    CONTENT += '<h5 class="fw-bold mb-3"><i class="bi bi-gear-fill text-warning me-2"></i>Account Settings</h5>'
    CONTENT += '<ul class="list-unstyled" style="font-size:.9rem;">'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-warning me-2"></i> Update your profile information in <a href="/settings">Settings</a></li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-warning me-2"></i> Change notification preferences</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-warning me-2"></i> Manage privacy settings for your profile</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-warning me-2"></i> Customize appearance with themes and font sizes</li>'
    CONTENT += "</ul></div></div>"
    CONTENT += '<div class="col-md-6"><div class="glass-card p-4">'
    CONTENT += '<h5 class="fw-bold mb-3"><i class="bi bi-shield-lock-fill text-info me-2"></i>Library Rules</h5>'
    CONTENT += '<ul class="list-unstyled" style="font-size:.9rem;">'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-info me-2"></i> Books can be issued for a limited period</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-info me-2"></i> Late returns incur a fine per day</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-info me-2"></i> Maximum borrow limit applies per user</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-info me-2"></i> Membership must be renewed periodically</li>'
    CONTENT += "</ul></div>"
    CONTENT += '<div class="glass-card p-4">'
    CONTENT += '<h5 class="fw-bold mb-3"><i class="bi bi-envelope-fill text-success me-2"></i>Need Help?</h5>'
    CONTENT += '<p style="font-size:.9rem;">If you encounter any issues or have questions:</p>'
    CONTENT += '<ul class="list-unstyled" style="font-size:.9rem;">'
    CONTENT += '<li class="mb-2"><i class="bi bi-envelope-fill text-success me-2"></i> Contact the library staff for assistance</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-chat-dots-fill text-success me-2"></i> Post in the community for peer support</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-journal-text text-success me-2"></i> Check the <a href="/feed">Feed</a> for announcements</li>'
    CONTENT += "</ul></div></div></div></div>"
    return render_page_func("Help & Support", CONTENT)


# ════════════════════════════════════════════════════════════════════════════
# User Settings page
# ════════════════════════════════════════════════════════════════════════════


def settings_page(render_page_func, storage, notif_mgr) -> str:
    """User settings page with Profile, Notifications, Privacy, Appearance, and Reading tabs."""
    uid = session["user_id"]
    users = storage.load_users()
    user = users.get(uid)
    if not user:
        return render_page_func(
            "Settings",
            '<div class="empty-state"><div class="empty-icon"><i class="bi bi-person-x-fill"></i></div><h4>User not found</h4></div>',
        )

    esc = _h
    name_v = esc(user.name)
    email_v = esc(user.email)
    phone_v = esc(user.phone) if user.phone else ""
    bio_v = esc(user.bio) if user.bio else ""
    loc_v = esc(user.location) if user.location else ""
    web_v = esc(user.website) if user.website else ""
    theme_v = user.theme or "light"
    font_v = user.font_size or "medium"

    n_checks = {
        "email_notifications": user.email_notifications,
        "push_notifications": user.push_notifications,
        "notify_on_comment": user.notify_on_comment,
        "notify_on_like": user.notify_on_like,
        "notify_on_follow": user.notify_on_follow,
        "notify_on_issue_return": user.notify_on_issue_return,
        "notify_on_overdue": user.notify_on_overdue,
        "notify_on_due_reminder": user.notify_on_due_reminder,
    }
    n_html = ""
    for key, val in n_checks.items():
        label = (
            key.replace("notify_on_", "")
            .replace("_", " ")
            .title()
            .replace("Email Notifications", "Email Notifications")
            .replace("Push Notifications", "Push Notifications")
        )
        chk = "checked" if val else ""
        icon = {
            "email_notifications": "envelope-fill",
            "push_notifications": "bell-fill",
            "notify_on_comment": "chat-dots-fill",
            "notify_on_like": "heart-fill",
            "notify_on_follow": "person-plus-fill",
            "notify_on_issue_return": "arrow-left-right",
            "notify_on_overdue": "exclamation-triangle-fill",
            "notify_on_due_reminder": "clock-fill",
        }.get(key, "bell-fill")
        n_html += (
            '<div class="settings-toggle-item">'
            '<div class="d-flex align-items-center gap-3">'
            f'<i class="bi bi-{icon}" style="font-size:1.2rem;color:var(--primary);width:24px;"></i>'
            f'<div><div class="fw-medium">{label}</div></div>'
            "</div>"
            '<label class="toggle-switch">'
            f'<input type="checkbox" name="{key}" {chk} onchange="saveSetting(this)">'
            '<span class="toggle-slider"></span>'
            "</label>"
            "</div>"
        )

    p_checks = [
        ("privacy_show_activity", "Show reading activity on profile", "graph-up-arrow", user.privacy_show_activity),
        ("privacy_show_wishlist", "Show wishlist on profile", "star-fill", user.privacy_show_wishlist),
        ("privacy_show_bookmarks", "Show bookmarks on profile", "bookmark-fill", user.privacy_show_bookmarks),
        ("privacy_show_email", "Show email on profile", "envelope-fill", user.privacy_show_email),
    ]
    p_html = ""
    for key, label, icon, val in p_checks:
        chk = "checked" if val else ""
        p_html += (
            '<div class="settings-toggle-item">'
            '<div class="d-flex align-items-center gap-3">'
            f'<i class="bi bi-{icon}" style="font-size:1.2rem;color:var(--primary);width:24px;"></i>'
            f'<div><div class="fw-medium">{label}</div></div>'
            "</div>"
            '<label class="toggle-switch">'
            f'<input type="checkbox" name="{key}" {chk} onchange="saveSetting(this)">'
            '<span class="toggle-slider"></span>'
            "</label>"
            "</div>"
        )

    vis_opts = ""
    for v in ["public", "members", "private"]:
        sel = "selected" if user.privacy_profile_visibility == v else ""
        vis_opts += f'<option value="{v}" {sel}>{v.title()}</option>'

    rating_opts = ""
    for v in ["perfection", "worth_it", "timepass", "skip"]:
        sel = "selected" if user.reading_default_rating == v else ""
        label = {"perfection": "Perfection", "worth_it": "Worth It", "timepass": "Timepass", "skip": "Skip"}[v]
        rating_opts += f'<option value="{v}" {sel}>{label}</option>'

    goal_opts = ""
    for v in ["books", "pages"]:
        sel = "selected" if user.reading_goal_type == v else ""
        goal_opts += f'<option value="{v}" {sel}>{v.title()}</option>'

    CONTENT = """<div class="animate-in">
<div class="glass-card p-0 mb-4" style="overflow:hidden;">
    <div class="p-4" style="background:linear-gradient(135deg,var(--primary),#7c3aed);color:white;">
        <h4 class="fw-bold mb-0"><i class="bi bi-gear-fill me-2"></i> Settings</h4>
        <p class="mb-0" style="opacity:.8;font-size:.85rem;">Manage your account preferences</p>
    </div>
</div>

<nav class="settings-tabs mb-3" role="tablist" aria-label="Settings sections">
    <button class="settings-tab active" role="tab" aria-selected="true" data-tab="profile" onclick="switchSettingsTab(this)"><i class="bi bi-person-fill"></i> Profile</button>
    <button class="settings-tab" role="tab" aria-selected="false" data-tab="notifications" onclick="switchSettingsTab(this)"><i class="bi bi-bell-fill"></i> Notifications</button>
    <button class="settings-tab" role="tab" aria-selected="false" data-tab="privacy" onclick="switchSettingsTab(this)"><i class="bi bi-shield-lock-fill"></i> Privacy</button>
    <button class="settings-tab" role="tab" aria-selected="false" data-tab="appearance" onclick="switchSettingsTab(this)"><i class="bi bi-palette-fill"></i> Appearance</button>
    <button class="settings-tab" role="tab" aria-selected="false" data-tab="reading" onclick="switchSettingsTab(this)"><i class="bi bi-book-fill"></i> Reading</button>
</nav>

<div class="settings-panel active" id="tab-profile" role="tabpanel">
    <div class="glass-card p-4">
        <h5 class="fw-bold mb-3"><i class="bi bi-person-fill text-primary me-2"></i>Profile Information</h5>
        <form id="profileSettingsForm" onsubmit="return saveProfileSettings()">
            <div class="row">
                <div class="col-md-6 mb-3"><label class="form-label">Display Name</label><input type="text" class="form-control" id="sName" value="NAME_V" required></div>
                <div class="col-md-6 mb-3"><label class="form-label">Email</label><input type="email" class="form-control" id="sEmail" value="EMAIL_V"></div>
            </div>
            <div class="row">
                <div class="col-md-6 mb-3"><label class="form-label">Phone</label><input type="text" class="form-control" id="sPhone" value="PHONE_V"></div>
                <div class="col-md-6 mb-3"><label class="form-label">Website</label><input type="url" class="form-control" id="sWebsite" value="WEB_V" placeholder="https://example.com"></div>
            </div>
            <div class="mb-3"><label class="form-label">Location</label><input type="text" class="form-control" id="sLocation" value="LOC_V" placeholder="City, Country"></div>
            <div class="mb-3"><label class="form-label">Bio</label><textarea class="form-control" id="sBio" rows="3" placeholder="Tell us about yourself...">BIO_V</textarea></div>
            <div class="mb-3"><label class="form-label">Change Password</label>
                <div class="row">
                    <div class="col-md-4 mb-2"><input type="password" class="form-control" id="sCurPw" placeholder="Current password"></div>
                    <div class="col-md-4 mb-2"><input type="password" class="form-control" id="sNewPw" placeholder="New password" minlength="12"></div>
                    <div class="col-md-4 mb-2"><input type="password" class="form-control" id="sConfPw" placeholder="Confirm new password"></div>
                </div>
                <small class="text-muted">Leave password fields empty to keep current password</small>
            </div>
            <button type="submit" class="btn btn-primary"><i class="bi bi-check-lg me-1"></i> Save Changes</button>
        </form>
    </div>
</div>

<div class="settings-panel" id="tab-notifications" role="tabpanel">
    <div class="glass-card p-4">
        <h5 class="fw-bold mb-3"><i class="bi bi-bell-fill text-warning me-2"></i>Notification Preferences</h5>
        <p class="text-muted small mb-3">Control which notifications you receive</p>
        NOTIF_HTML
    </div>
</div>

<div class="settings-panel" id="tab-privacy" role="tabpanel">
    <div class="glass-card p-4">
        <h5 class="fw-bold mb-3"><i class="bi bi-shield-lock-fill text-info me-2"></i>Privacy Settings</h5>
        <div class="mb-3"><label class="form-label">Profile Visibility</label>
            <select class="form-select" id="sProfileVis" onchange="saveProfileVisibility(this)">VIS_OPTS</select>
        </div>
        <p class="text-muted small mb-3">Control what appears on your public profile</p>
        PRIV_HTML
    </div>
</div>

<div class="settings-panel" id="tab-appearance" role="tabpanel">
    <div class="glass-card p-4">
        <h5 class="fw-bold mb-3"><i class="bi bi-palette-fill text-purple me-2"></i>Appearance</h5>
        <div class="mb-4"><label class="form-label">Theme</label>
            <div class="d-flex gap-3">
                <label class="theme-option%s" onclick="selectTheme('light')"><input type="radio" name="theme" value="light" class="d-none" %s><i class="bi bi-sun-fill" style="font-size:1.5rem;"></i><span>Light</span></label>
                <label class="theme-option%s" onclick="selectTheme('dark')"><input type="radio" name="theme" value="dark" class="d-none" %s><i class="bi bi-moon-fill" style="font-size:1.5rem;"></i><span>Dark</span></label>
            </div>
        </div>
        <div class="mb-3"><label class="form-label">Font Size</label>
            <div class="d-flex gap-2">
                <button class="btn %s" onclick="selectFont('small')" id="fontSmall">A-</button>
                <button class="btn %s" onclick="selectFont('medium')" id="fontMedium">A</button>
                <button class="btn %s" onclick="selectFont('large')" id="fontLarge">A+</button>
            </div>
        </div>
    </div>
</div>

<div class="settings-panel" id="tab-reading" role="tabpanel">
    <div class="glass-card p-4">
        <h5 class="fw-bold mb-3"><i class="bi bi-book-fill text-success me-2"></i>Reading Preferences</h5>
        <div class="row">
            <div class="col-md-6 mb-3"><label class="form-label">Default Rating Label</label><select class="form-select" id="sDefaultRating">RATING_OPTS</select></div>
            <div class="col-md-6 mb-3"><label class="form-label">Reading Goal Type</label><select class="form-select" id="sGoalType">GOAL_OPTS</select></div>
        </div>
        <div class="mb-3"><label class="form-label">Default Reading Goal</label><input type="number" class="form-control" id="sDefaultGoal" value="GOAL_VAL" min="1" max="365"><small class="text-muted">Books or pages per year</small></div>
        <button class="btn btn-primary" onclick="saveReadingPrefs()"><i class="bi bi-check-lg me-1"></i> Save Reading Preferences</button>
    </div>
</div>
</div>
"""

    CONTENT = CONTENT.replace("NAME_V", name_v).replace("EMAIL_V", email_v)
    CONTENT = CONTENT.replace("PHONE_V", phone_v).replace("WEB_V", web_v)
    CONTENT = CONTENT.replace("LOC_V", loc_v).replace("BIO_V", bio_v)
    CONTENT = CONTENT.replace("NOTIF_HTML", n_html).replace("PRIV_HTML", p_html)
    CONTENT = CONTENT.replace("VIS_OPTS", vis_opts)
    CONTENT = CONTENT.replace("RATING_OPTS", rating_opts).replace("GOAL_OPTS", goal_opts)
    CONTENT = CONTENT.replace("GOAL_VAL", str(user.reading_default_goal or 12))

    light_sel = " active" if theme_v == "light" else ""
    light_chk = "checked" if theme_v == "light" else ""
    dark_sel = " active" if theme_v == "dark" else ""
    dark_chk = "checked" if theme_v == "dark" else ""
    font_classes = ["btn btn-outline", "btn btn-outline", "btn btn-outline"]
    if font_v == "small":
        font_classes[0] = "btn btn-primary"
    elif font_v == "medium":
        font_classes[1] = "btn btn-primary"
    elif font_v == "large":
        font_classes[2] = "btn btn-primary"
    CONTENT = CONTENT % (
        light_sel, light_chk, dark_sel, dark_chk,
        font_classes[0], font_classes[1], font_classes[2],
    )

    return render_page_func(
        "Settings",
        CONTENT
        + """
<style>
.settings-tabs{display:flex;gap:4px;overflow-x:auto;padding:4px;background:var(--border);border-radius:12px;flex-wrap:wrap}
.settings-tab{display:flex;align-items:center;gap:6px;padding:8px 14px;border:none;background:transparent;color:var(--text-muted);font-size:.85rem;font-weight:600;border-radius:8px;cursor:pointer;transition:all .2s;white-space:nowrap;font-family:var(--font)}
.settings-tab:hover{color:var(--text);background:var(--bg-card)}
.settings-tab.active{background:var(--bg-card);color:var(--text);box-shadow:0 2px 8px rgba(0,0,0,.06)}
.settings-panel{display:none;animation:fadeInUp .3s ease}
.settings-panel.active{display:block}
.settings-toggle-item{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--border)}
.settings-toggle-item:last-child{border-bottom:none}
.toggle-switch{position:relative;display:inline-block;width:44px;height:24px;flex-shrink:0}
.toggle-switch input{opacity:0;width:0;height:0}
.toggle-slider{position:absolute;cursor:pointer;inset:0;background:var(--border);border-radius:24px;transition:.3s}
.toggle-slider::before{content:"";position:absolute;height:18px;width:18px;left:3px;bottom:3px;background:white;border-radius:50%;transition:.3s;box-shadow:0 1px 3px rgba(0,0,0,.15)}
.toggle-switch input:checked+.toggle-slider{background:var(--primary)}
.toggle-switch input:checked+.toggle-slider::before{transform:translateX(20px)}
.theme-option{display:flex;flex-direction:column;align-items:center;gap:4px;padding:16px 24px;border-radius:12px;border:2px solid var(--border);cursor:pointer;transition:all .2s;min-width:100px}
.theme-option.active{border-color:var(--primary);background:var(--primary-light)}
.theme-option:hover{border-color:var(--primary)}
</style>
<script>
function switchSettingsTab(el) {
    document.querySelectorAll(".settings-tab").forEach(function(t){ t.classList.remove("active"); t.setAttribute("aria-selected","false"); });
    el.classList.add("active"); el.setAttribute("aria-selected","true");
    document.querySelectorAll(".settings-panel").forEach(function(p){ p.classList.remove("active"); });
    var tab = document.getElementById("tab-" + el.getAttribute("data-tab"));
    if(tab) tab.classList.add("active");
}
function saveSetting(el) {
    var data = {}; data[el.name] = el.checked;
    fetch("/api/settings/save", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(data)
    }).then(function(r){ return r.json() }).then(function(d){
        if(d.success) showToast("Setting saved", "success");
        else showToast(d.error || "Failed", "error");
    });
}
function saveProfileSettings() {
    var data = {
        name: document.getElementById("sName").value.trim(),
        email: document.getElementById("sEmail").value.trim(),
        phone: document.getElementById("sPhone").value.trim(),
        website: document.getElementById("sWebsite").value.trim(),
        location: document.getElementById("sLocation").value.trim(),
        bio: document.getElementById("sBio").value.trim()
    };
    var cpw = document.getElementById("sCurPw").value;
    var npw = document.getElementById("sNewPw").value;
    var cnpw = document.getElementById("sConfPw").value;
    if(cpw || npw || cnpw) {
        if(!cpw) { showToast("Enter current password", "error"); return false; }
        if(npw !== cnpw) { showToast("New passwords do not match", "error"); return false; }
        if(npw.length < 12) { showToast("New password must be at least 12 characters", "error"); return false; }
        data.current_password = cpw;
        data.new_password = npw;
    }
    var btn = document.querySelector("#tab-profile .btn-primary");
    btn.disabled = true; btn.innerHTML = "<span class='spinner-border spinner-border-sm'></span> Saving...";
    fetch("/api/settings/save", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(data)
    }).then(function(r){ return r.json() }).then(function(d){
        btn.disabled = false; btn.innerHTML = "<i class='bi bi-check-lg'></i> Save Changes";
        if(d.success) { showToast("Profile updated!", "success"); setTimeout(function(){ location.reload(); }, 1000); }
        else showToast(d.error || "Failed", "error");
    }).catch(function(){ btn.disabled = false; btn.innerHTML = "<i class='bi bi-check-lg'></i> Save Changes"; });
    return false;
}
function saveProfileVisibility(el) {
    fetch("/api/settings/save", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({privacy_profile_visibility: el.value})
    }).then(function(r){ return r.json() }).then(function(d){
        if(d.success) showToast("Privacy updated", "success");
    });
}
function selectTheme(t) {
    document.querySelectorAll(".theme-option").forEach(function(o){ o.classList.remove("active"); });
    document.querySelector(".theme-option input[value='"+t+"']").closest(".theme-option").classList.add("active");
    document.documentElement.setAttribute("data-theme", t);
    localStorage.setItem("theme", t);
    fetch("/api/settings/save", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({theme: t})
    });
}
function selectFont(s) {
    document.querySelectorAll("#fontSmall,#fontMedium,#fontLarge").forEach(function(b){ b.className = "btn btn-outline"; });
    document.getElementById("font"+s.charAt(0).toUpperCase()+s.slice(1)).className = "btn btn-primary";
    fetch("/api/settings/save", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({font_size: s})
    });
}
function saveReadingPrefs() {
    fetch("/api/settings/save", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            reading_default_rating: document.getElementById("sDefaultRating").value,
            reading_goal_type: document.getElementById("sGoalType").value,
            reading_default_goal: parseInt(document.getElementById("sDefaultGoal").value) || 12
        })
    }).then(function(r){ return r.json() }).then(function(d){
        if(d.success) showToast("Reading preferences saved!", "success");
        else showToast(d.error || "Failed", "error");
    });
}
</script>
""",
    )
