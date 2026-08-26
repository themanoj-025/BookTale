"""web_app.py - Library Management System Web Interface

Application bootstrap, middleware, error handlers, and utility helpers.
Route modules are registered via init_*_routes() calls below.
"""

import contextlib
import html
import os
import random
import sys
import zlib
from datetime import datetime
from functools import wraps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, OSError, ValueError):
            _stream.reconfigure(encoding="utf-8", errors="replace")

from flask import (
    Flask,
    g,
    jsonify,
    redirect,
    render_template,
    render_template_string,
    request,
    session,
    url_for,
)
from flask_cors import CORS

from app.config.settings import Config, validate_secure_config
from app.core.logger import log, set_request_id
from app.db.storage_adapter import create_storage
from app.routes.site_pages import init_site_pages
from app.routes.social_routes import init_social_routes
from app.services.auth.auth import AuthManager
from app.services.books.library import Library
from app.services.books.lists import BookLists
from app.services.books.series import SeriesManager
from app.services.notifications.notifications import NotificationManager
from app.services.reading.diary import DiaryManager
from app.services.reading.reading_challenge import ReadingChallenge
from app.services.reading.reading_progress import ReadingProgress
from app.services.reading.wishlist import Wishlist
from app.services.recommendations.recommender import Recommender
from app.services.social.communities import Communities
from app.services.social.gamification import Gamification

# ── Flask app ───────────────────────────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
app = Flask(
    __name__,
    template_folder=os.path.join(_PROJECT_ROOT, "app", "templates"),
    static_folder=os.path.join(_PROJECT_ROOT, "app", "static"),
)
app.secret_key = Config.SECRET_KEY

validate_secure_config()

# ── CSRF protection ─────────────────────────────────────────────────────────
app.config["WTF_CSRF_ENABLED"] = os.getenv("WTF_CSRF_ENABLED", "1").strip().lower() in (
    "1", "true", "yes", "on",
)
try:
    from flask_wtf.csrf import CSRFProtect
    csrf = CSRFProtect(app)
except ImportError:
    csrf = None

# ── Rate limiting ───────────────────────────────────────────────────────────
app.config["RATELIMIT_ENABLED"] = os.getenv("RATELIMIT_ENABLED", "1").strip().lower() in (
    "1", "true", "yes", "on",
)


def _limiter_storage_uri() -> str:
    override = os.getenv("RATELIMIT_STORAGE_URI", "").strip()
    return override or Config.REDIS_URL


try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["200 per minute"],
        storage_uri=_limiter_storage_uri(),
        in_memory_fallback_enabled=True,
    )
    limiter.init_app(app)
    app.extensions["booktale_limiter"] = limiter
except ImportError:
    limiter = None


def _rate_limit(limit_value, **kwargs):  # type: ignore[no-untyped-def]
    """Rate-limit decorator; no-op fallback if flask-limiter is not installed."""
    if limiter is None:
        return lambda f: f
    return limiter.limit(limit_value, **kwargs)


def _user_key() -> dict:  # type: ignore[no-untyped-def]
    uid = session.get("user_id")
    if uid:
        return f"user:{uid}"
    return f"ip:{request.remote_addr}"


def _audit_log(admin_id, action, target="", old_value=None, new_value=None) -> None:  # type: ignore[no-untyped-def]
    """Append one row to the admin audit trail."""
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
        log(
            f"audit write failed (admin={admin_id}, action={action}, "
            f"target={target}): {e}",
            "audit",
        )


# ── Session cookie security ────────────────────────────────────────────────
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
if not Config.FLASK_DEBUG and os.getenv("SESSION_COOKIE_SECURE", "").strip() == "1":
    app.config["SESSION_COOKIE_SECURE"] = True

# ── Frontend asset pipeline ─────────────────────────────────────────────────


def asset(path) -> str:
    """Return the content-hashed URL for a logical static asset path."""
    _manifest = getattr(asset, "_manifest", None)
    if _manifest is None:
        import json as _json
        _manifest = {}
        try:
            with open(
                os.path.join(_PROJECT_ROOT, "app", "static", "dist", "manifest.json"),
                encoding="utf-8",
            ) as _f:
                _manifest = _json.load(_f)
        except (OSError, ValueError):
            pass
        asset._manifest = _manifest
    return _manifest.get(path, "/static/" + path)


app.jinja_env.globals["asset"] = asset

# ── CORS ────────────────────────────────────────────────────────────────────
CORS(
    app,
    origins=["http://localhost:5000", "http://127.0.0.1:5000"],
    supports_credentials=True,
)


# ── Middleware ───────────────────────────────────────────────────────────────
@app.before_request
def _request_id_middleware() -> None:
    set_request_id()


@app.after_request
def apply_security_headers(response) -> dict:
    """Set security headers on every response."""
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://code.jquery.com https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
        "font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://openlibrary.org; "
        "frame-ancestors 'none';"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), interest-cohort=()"
    )
    return response


# ── Service instances ───────────────────────────────────────────────────────
storage = create_storage()
lib = Library(storage)
auth = AuthManager(storage)
recommender = Recommender(storage)
notif_mgr = NotificationManager(storage)
from app.routes.main import bootstrap

bootstrap(storage, auth)

from app.realtime.realtime import init_socketio as _init_socketio
from app.services.books.reviews import ReviewManager
from app.services.social.social import SocialFeed

socketio = _init_socketio(app, storage)
social = SocialFeed(storage)
review_mgr = ReviewManager(storage)
book_lists = BookLists(storage)
communities = Communities(storage)
gamification = Gamification(storage)
series_mgr = SeriesManager(storage)
challenge = ReadingChallenge(storage)
reading_progress = ReadingProgress(storage)
wishlist = Wishlist(storage)
diary_mgr = DiaryManager(storage)

# ── Register route modules ──────────────────────────────────────────────────

# Social routes
init_social_routes(
    app, storage, lib, auth, social, review_mgr, recommender,
    notif_mgr, book_lists, communities, gamification,
)

# Feature routes (series, challenge, progress, wishlist, diary)
from app.routes.feature_routes import init_feature_routes

init_feature_routes(
    app, storage, lib, auth, notif_mgr, series_mgr,
    challenge, reading_progress, wishlist, diary_mgr,
)

# Auth routes (login, register, forgot-password, reset-password, verify-email)
from app.routes.auth_routes import init_auth_routes

init_auth_routes(app, storage, lib, auth, notif_mgr)

# Admin routes (admin settings, admin fines)
from app.routes.admin_routes import init_admin_routes

init_admin_routes(app, storage, lib, auth, notif_mgr)

# API routes (JSON endpoints: trending, random, search, settings, AI, etc.)
from app.routes.api_routes import init_api_routes

init_api_routes(app, storage, lib, auth, notif_mgr, recommender, social, diary_mgr)

# Page routes
from app.routes.helpers import init_helpers
from app.routes.page_routes import init_page_routes

init_helpers(storage, notif_mgr)
init_page_routes(
    app, storage, lib, auth, notif_mgr, social, review_mgr,
    recommender, book_lists, communities, gamification, series_mgr,
    challenge, reading_progress, wishlist, diary_mgr,
)
init_site_pages(app, storage, lib, recommender, social, review_mgr, notif_mgr)


# ── Utility helpers ─────────────────────────────────────────────────────────

def h(text):  # type: ignore[no-untyped-def]
    return html.escape(str(text))


def login_required(f):  # type: ignore[no-untyped-def]
    @wraps(f)
    def d(*a, **k):  # type: ignore[no-untyped-def]
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        return f(*a, **k)
    return d


def admin_required(f):  # type: ignore[no-untyped-def]
    @wraps(f)
    def d(*a, **k):  # type: ignore[no-untyped-def]
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        if session.get("role") != "admin":
            return jsonify({"error": "Admin access required"}), 403
        return f(*a, **k)
    return d


def api_key_required(f):  # type: ignore[no-untyped-def]
    import secrets as _secrets

    @wraps(f)
    def d(*a, **k):  # type: ignore[no-untyped-def]
        api_key = os.environ.get("BOOKTALE_API_KEY", "")
        if not api_key:
            return f(*a, **k)
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing Authorization header"}), 401
        token = auth_header[7:]
        if not _secrets.compare_digest(token, api_key):
            return jsonify({"error": "Invalid API key"}), 403
        return f(*a, **k)
    return d


def get_current_user():  # type: ignore[no-untyped-def]
    if "user_id" not in session:
        return None
    return storage.load_users().get(session["user_id"])


def render_page(title, content, **kw):  # type: ignore[no-untyped-def]
    user = get_current_user()
    return render_template(
        "base.html",
        title=title,
        content=content,
        notif_count=notif_mgr.get_unread_count(user.user_id) if user else 0,
        **kw,
    )


def render_auth_page(title, content, **kw):  # type: ignore[no-untyped-def]
    """Render an auth page using the split-screen auth_base.html template."""
    return render_template("auth_base.html", title=title, auth_content=content, session={}, **kw)


def _initials(name):  # type: ignore[no-untyped-def]
    parts = name.strip().split()
    if not parts:
        return "?"
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return parts[0][:2].upper()


def _avatar_color(name) -> dict:  # type: ignore[no-untyped-def]
    colors = [
        "#4f46e5", "#059669", "#d97706", "#dc2626",
        "#0891b2", "#7c3aed", "#db2777", "#ca8a04",
    ]
    return colors[zlib.crc32(str(name).encode("utf-8")) % len(colors)]


def _avatar_html(name, size=32):  # type: ignore[no-untyped-def]
    i = _initials(name)
    c = _avatar_color(name)
    return (
        f'<div class="avatar" style="width:{size}px;height:{size}px;background:{c}20;color:{c};'
        f'font-size:{size // 2}px;font-weight:700;border-radius:50%;display:inline-flex;'
        f'align-items:center;justify-content:center;flex-shrink:0;" title="{h(name)}">{h(i)}</div>'
    )


CAT_COLORS = {
    "Fiction": "#4f46e5", "Non-Fiction": "#059669", "Science": "#0891b2",
    "Technology": "#7c3aed", "History": "#d97706", "Philosophy": "#be185d",
    "Art": "#db2777", "Biography": "#ca8a04", "Children": "#16a34a",
    "Comics": "#e11d48", "Poetry": "#9333ea", "Drama": "#ea580c",
    "Education": "#2563eb", "Reference": "#64748b", "Religion": "#78716c",
    "Self-Help": "#0d9488", "Cooking": "#f97316", "Travel": "#0ea5e9",
    "Music": "#8b5cf6", "Sports": "#22c55e", "Other": "#6b7280",
}


def cat_color(c):  # type: ignore[no-untyped-def]
    return CAT_COLORS.get(c, CAT_COLORS["Other"])


app.jinja_env.globals["_avatar_html"] = _avatar_html
app.jinja_env.globals["_initials"] = _initials


# ════════════════════════════════════════════════════════════════════════════
# Error handlers
# ════════════════════════════════════════════════════════════════════════════

_ERROR_PAGES = {
    400: ("400", "Bad Request", "⚠️", "The request could not be understood. Check the submitted data and try again."),
    401: ("401", "Unauthorized", "🔒", "You need to sign in to access this page."),
    403: ("403", "Forbidden", "⛔", "You don't have permission to access this resource."),
    404: ("404", "Page Not Found", "🔍", "The page you're looking for doesn't exist or was moved."),
    405: ("405", "Method Not Allowed", "🚫", "This URL doesn't accept that request method."),
    409: ("409", "Conflict", "⚔️", "The request conflicts with the current state of the resource."),
    413: ("413", "Request Too Large", "📦", "The uploaded file or request is too large."),
    415: ("415", "Unsupported Media Type", "🧩", "The request payload is in an unsupported format."),
    422: ("422", "Unprocessable Entity", "📋", "The request was well-formed but could not be processed."),
    429: ("429", "Too Many Requests", "🐌", "You've made too many requests. Please slow down and try again shortly."),
    500: ("500", "Server Error", "🛠️", "Something went wrong on our end. Please try again later."),
}


def _error_response(status: int, message: str) -> tuple:
    if request.path.startswith("/api/") and request.path != "/api/docs":
        return jsonify({"data": None, "error": {"code": status, "message": message}}), status
    _code, _title, _icon, _msg = _ERROR_PAGES.get(status, _ERROR_PAGES[500])
    return (
        render_template(
            "errors/error_page.html",
            title=f"{_code} {_title}",
            error_title=_title,
            error_message=_msg,
            icon=_icon,
        ),
        status,
    )


for _code in sorted(set(_ERROR_PAGES) - {404, 500}):

    def _make_handler(code: int):
        def _handler(e):
            return _error_response(code, _ERROR_PAGES[code][3])
        return _handler

    app.register_error_handler(_code, _make_handler(_code))


@app.errorhandler(404)
def _not_found(e):
    return _error_response(404, _ERROR_PAGES[404][3])


@app.errorhandler(500)
def _server_error(e) -> dict:
    from app.core.logger import log as _err_log
    _err_log(f"unhandled exception: {e!r}", "error")
    return _error_response(500, _ERROR_PAGES[500][3])


# ════════════════════════════════════════════════════════════════════════════
# Health endpoints
# ════════════════════════════════════════════════════════════════════════════


@app.route("/healthz")
def healthz():  # type: ignore[no-untyped-def]
    return jsonify({"status": "ok"}), 200


@app.route("/readyz")
def readyz() -> dict:  # type: ignore[no-untyped-def]
    try:
        from sqlalchemy import text as _sqltext
        import app.db.database as _dbmod

        with _dbmod.get_session_factory()() as db_session:
            db_session.execute(_sqltext("SELECT 1"))
        return jsonify({"status": "ok", "database": "connected"}), 200
    except Exception as e:
        from app.core.logger import log as _log
        _log(f"readyz probe failed: {e}", "health")
        return jsonify({"status": "not_ready", "error": "database unreachable"}), 503


# ════════════════════════════════════════════════════════════════════════════
# OpenAPI / Swagger UI
# ════════════════════════════════════════════════════════════════════════════


@app.route("/api/openapi.json")
def api_openapi_json():  # type: ignore[no-untyped-def]
    from app.api.api_spec import build_openapi_spec
    return jsonify(build_openapi_spec())


@app.route("/api/docs")
def api_docs() -> dict:  # type: ignore[no-untyped-def]
    return render_template_string(
        """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BookTale API Docs — Swagger UI</title>
<meta name="description" content="Interactive OpenAPI documentation for the BookTale API.">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui.css">
</head>
<body style="margin:0">
<div id="swagger-ui"></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"></script>
<script>
  window.onload = function() {
    window.ui = SwaggerUIBundle({
      url: "/api/openapi.json",
      dom_id: "#swagger-ui",
      deepLinking: true,
      persistAuthorization: true,
      displayRequestDuration: true
    });
  };
</script>
</body>
</html>"""
    )


# ════════════════════════════════════════════════════════════════════════════
# Security trust page
# ════════════════════════════════════════════════════════════════════════════


@app.route("/security")
def security_page():  # type: ignore[no-untyped-def]
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
        f'<h5 class="fw-bold mb-2">{title}</h5><p class="mb-0" style="font-size:.9rem;color:var(--text-muted);">{h(desc)}</p></div></div>'
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
    return render_page("Security & Trust", CONTENT)


# ════════════════════════════════════════════════════════════════════════════
# Help page (static content, stays in web_app)
# ════════════════════════════════════════════════════════════════════════════


@app.route("/help")
@login_required
def help_page():  # type: ignore[no-untyped-def]
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
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-warning me-2"></i> Update your profile information in <a href=\'/settings\'>Settings</a></li>'
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
    CONTENT += '<li class="mb-2"><i class="bi bi-journal-text text-success me-2"></i> Check the <a href=\'/feed\'>Feed</a> for announcements</li>'
    CONTENT += "</ul></div></div></div></div>"
    return render_page("Help & Support", CONTENT)


# ════════════════════════════════════════════════════════════════════════════
# User Settings page (large inline HTML — stays in web_app)
# ════════════════════════════════════════════════════════════════════════════


@app.route("/settings")
@login_required
def settings_page():  # type: ignore[no-untyped-def]
    """User settings page with Profile, Notifications, Privacy, Appearance, and Reading tabs."""
    uid = session["user_id"]
    users = storage.load_users()
    user = users.get(uid)
    if not user:
        return render_page(
            "Settings",
            '<div class="empty-state"><div class="empty-icon"><i class="bi bi-person-x-fill"></i></div><h4>User not found</h4></div>',
        )

    esc = h
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

    return render_page(
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


if __name__ == "__main__":
    print("  📚 Library Management System — Web Interface")
    print(f"  🌐 http://{Config.FLASK_HOST}:{Config.FLASK_PORT}")
    print("  ⌨️  Press Ctrl+K to search books from anywhere")
    socketio.run(
        app,
        host=Config.FLASK_HOST,
        port=Config.FLASK_PORT,
        debug=Config.FLASK_DEBUG,
        allow_unsafe_werkzeug=True,
    )
