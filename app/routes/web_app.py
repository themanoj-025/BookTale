"""web_app.py - Library Management System Web Interface
Modern features: issue/return modals, autocomplete search, keyboard shortcuts,
loading skeletons, print-friendly CSS, avatar initials, PDF export.
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
    # Reconfigure stdout/stderr in place for UTF-8 support.
    # Do NOT replace the objects: creating new TextIOWrappers closes the
    # underlying buffer, which breaks pytest's capture machinery (and any
    # other tool that has wrapped sys.stdout).
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

# Project root (three levels up from app/routes/web_app.py). Flask's default
# root_path would resolve templates/static against the package root; we pin
# them explicitly to the canonical app/templates + app/static locations.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
app = Flask(
    __name__,
    template_folder=os.path.join(_PROJECT_ROOT, "app", "templates"),
    static_folder=os.path.join(_PROJECT_ROOT, "app", "static"),
)
app.secret_key = Config.SECRET_KEY

# Fail fast on insecure boot configuration (unset/default SECRET_KEY).
validate_secure_config()

# ── CSRF protection (Phase 4) ─────────────────────────────────────────────
# Enabled BY DEFAULT (secure-by-default). CSRFProtect validates a per-session
# token on every POST/PUT/PATCH/DELETE. Set WTF_CSRF_ENABLED=0 to disable
# (tests/CLI flows with no token plumbing). The flag is read at request time,
# so tests can toggle app.config["WTF_CSRF_ENABLED"] per-test.
app.config["WTF_CSRF_ENABLED"] = os.getenv("WTF_CSRF_ENABLED", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
try:
    from flask_wtf.csrf import CSRFProtect

    csrf = CSRFProtect(app)
except ImportError:
    csrf = None

# ── Rate limiting (Phase 4) ───────────────────────────────────────────────
# RATELIMIT_ENABLED is read at init_app() time (Limiter.enabled is captured
# from config then), so the flag must be set in app.config BEFORE init_app.
# Tests set RATELIMIT_ENABLED=0 so the suite never trips per-IP auth limits.
app.config["RATELIMIT_ENABLED"] = os.getenv("RATELIMIT_ENABLED", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)


def _limiter_storage_uri() -> str:
    """Storage backend for rate-limit budgets.

    Phase 6: defaults to Redis (Config.REDIS_URL) so budgets survive process
    restarts and are shared across multiple gunicorn workers (flask-limiter's
    per-process memory storage cannot do either). Override with
    RATELIMIT_STORAGE_URI=memory:// for single-process runs / tests that
    don't want a Redis dependency.
    """
    override = os.getenv("RATELIMIT_STORAGE_URI", "").strip()
    return override or Config.REDIS_URL


try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["200 per minute"],
        storage_uri=_limiter_storage_uri(),
        # Redis outage -> degrade to a per-process in-memory budget (fail-open
        # with a logged warning) instead of 500ing every limited request. Same
        # graceful-degradation stance as the /readyz DB probe.
        in_memory_fallback_enabled=True,
    )
    limiter.init_app(app)
    # flask-limiter 4.x stores itself in app.extensions["limiter"] as a SET
    # (it supports multiple limiters per app). Expose the single instance
    # under an app-specific key so the route modules (social_routes,
    # feature_routes) can apply per-route limits without importing
    # web_app (circular import) or depending on that set semantics.
    app.extensions["booktale_limiter"] = limiter
except ImportError:
    limiter = None


def _rate_limit(limit_value, **kwargs):
    """Rate-limit decorator; no-op fallback if flask-limiter is not installed.

    Passes through limiter options (methods, exempt_when, deduct_when, ...)
    to flask-limiter's limit().
    """
    if limiter is None:
        return lambda f: f
    return limiter.limit(limit_value, **kwargs)


def _user_key():
    """Rate-limit key scoped to the authenticated account, not just the IP.

    Per-IP limits alone let a distributed attacker (many source IPs) keep
    brute-forcing a compromised account's password fields. Keying on the
    session user_id gives each account its own budget regardless of where the
    requests originate. Falls back to the remote IP when no session exists
    (defensive; these endpoints are login-required anyway).
    """
    uid = session.get("user_id")
    if uid:
        return f"user:{uid}"
    return f"ip:{request.remote_addr}"


def _audit_log(admin_id, action, target="", old_value=None, new_value=None):
    """Append one row to the admin audit trail (who/what/when/from-where).

    Non-fatal: the audit trail must never break the action it records. On any
    failure (e.g. legacy JSON backend where the table doesn't exist) the entry
    is logged with context via the structured logger instead of raised.
    """
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
    except Exception as e:
        log(
            f"audit write failed (admin={admin_id}, action={action}, " f"target={target}): {e}",
            "audit",
        )


# ── Session cookie security (Phase 4) ─────────────────────────────────────
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# SESSION_COOKIE_SECURE: only set in production (HTTPS). In dev over HTTP,
# Secure cookies would silently drop session data.
if not Config.FLASK_DEBUG and os.getenv("SESSION_COOKIE_SECURE", "").strip() == "1":
    app.config["SESSION_COOKIE_SECURE"] = True

# ──
# Frontend asset pipeline: map logical asset paths (js/utils.js) to their
# content-hashed build outputs (static/dist/manifest.json, written by
# `npm run build`). Falls back to the raw /static/... path when the build has
# not been run (dev/tests) so pages never 404.


def asset(path):
    """Return the content-hashed URL for a logical static asset path."""
    _manifest = getattr(asset, "_manifest", None)
    if _manifest is None:
        import json as _json
        import os as _os

        _manifest = {}
        try:
            with open(
                _os.path.join(_PROJECT_ROOT, "app", "static", "dist", "manifest.json"),
                encoding="utf-8",
            ) as _f:
                _manifest = _json.load(_f)
        except (OSError, ValueError):
            pass
        asset._manifest = _manifest
    return _manifest.get(path, "/static/" + path)


app.jinja_env.globals["asset"] = asset

# ─
# Restrict CORS to known origins (not wildcard)
CORS(
    app,
    origins=["http://localhost:5000", "http://127.0.0.1:5000"],
    supports_credentials=True,
)


@app.before_request
def _request_id_middleware():
    """Assign a unique request ID for log correlation (Phase 7)."""
    set_request_id()


@app.after_request
def apply_security_headers(response):
    """Set security headers on every response."""
    # Content Security Policy — restricts script/style sources
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://code.jquery.com https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
        "font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://openlibrary.org; "
        "frame-ancestors 'none';"
    )
    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"
    # Referrer policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # HSTS (uncomment when HTTPS is enabled)
    # response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # Disable outdated XSS filter (sometimes introduces XSS bugs itself)
    response.headers["X-XSS-Protection"] = "0"
    # Restrict feature access (Permissions-Policy)
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), interest-cohort=()"
    )
    return response


storage = create_storage()
lib = Library(storage)
auth = AuthManager(storage)
recommender = Recommender(storage)
notif_mgr = NotificationManager(storage)
from app.routes.main import bootstrap

bootstrap(storage, auth)

# Initialize social modules
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

# Register social routes
init_social_routes(
    app,
    storage,
    lib,
    auth,
    social,
    review_mgr,
    recommender,
    notif_mgr,
    book_lists,
    communities,
    gamification,
)

# Register new feature routes
from app.routes.feature_routes import init_feature_routes

init_feature_routes(
    app,
    storage,
    lib,
    auth,
    notif_mgr,
    series_mgr,
    challenge,
    reading_progress,
    wishlist,
    diary_mgr,
)
from app.routes.page_routes import init_page_routes

init_page_routes(
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
)
init_site_pages(app, storage, lib, recommender, social, review_mgr, notif_mgr)


def h(text):
    return html.escape(str(text))


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
            return jsonify({"error": "Admin access required"}), 403
        return f(*a, **k)

    return d


def get_current_user():
    if "user_id" not in session:
        return None
    return storage.load_users().get(session["user_id"])


def render_page(title, content, **kw):
    user = get_current_user()
    return render_template(
        "base.html",
        title=title,
        content=content,
        notif_count=notif_mgr.get_unread_count(user.user_id) if user else 0,
        **kw,
    )


# ──
def _load_library_data():
    return storage.load_books(), storage.load_users(), storage.load_transactions()


def _library_stats():
    books, users, txns = _load_library_data()
    all_books = [b for b in books.values() if not b.is_deleted]
    now = datetime.now()
    tms = datetime(now.year, now.month, 1)
    total_books = len(all_books)
    total_copies = sum(b.total_copies for b in all_books)
    avail_copies = sum(b.available_copies for b in all_books)
    issued_copies = total_copies - avail_copies
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
    returns = [t for t in txns if t["type"] == "return"]
    active_issues = [t for t in issues if t.get("return_date") is None]
    total_txns = len(txns)
    month_txns = sum(1 for t in txns if datetime.fromisoformat(t.get("issue_date", "")) >= tms)
    unique_borrowers = len({t["user_id"] for t in issues})
    fines = storage.load_fines()
    total_fines = sum(f.get("amount", 0) for f in fines)
    paid_fines = sum(f.get("amount", 0) for f in fines if f.get("paid"))
    pending_fines = total_fines - paid_fines
    avg_bpu = round(len(issues) / total_users, 1) if total_users else 0
    return {
        "total_books": total_books,
        "total_copies": total_copies,
        "avail_copies": avail_copies,
        "issued_copies": issued_copies,
        "avail_rate": round(avail_rate, 1),
        "new_books_month": new_books_month,
        "total_users": total_users,
        "active_users": active_users,
        "blocked_users": blocked_users,
        "new_users_month": new_users_month,
        "total_issues": len(issues),
        "total_returns": len(returns),
        "active_issues": len(active_issues),
        "total_txns": total_txns,
        "month_txns": month_txns,
        "unique_borrowers": unique_borrowers,
        "avg_books_per_user": avg_bpu,
        "total_fines": round(total_fines, 2),
        "paid_fines": round(paid_fines, 2),
        "pending_fines": round(pending_fines, 2),
    }


def _book_borrowing_history(book_id):
    txns = storage.load_transactions()
    users = storage.load_users()
    history = []
    for t in txns:
        if t["book_id"] == book_id:
            u = users.get(t["user_id"])
            history.append(
                {
                    **t,
                    "user_name": u.name if u else t["user_id"],
                    "issue_date_fmt": t.get("issue_date", "")[:19],
                    "return_date_fmt": (
                        t.get("return_date", "")[:19] if t.get("return_date") else None
                    ),
                }
            )
    return sorted(history, key=lambda x: x.get("issue_date", ""), reverse=True)


def _initials(name):
    """Generate initials from a name, up to 2 characters."""
    parts = name.strip().split()
    if not parts:
        return "?"
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return parts[0][:2].upper()


def _avatar_color(name):
    """Generate a deterministic color from a name (stable across processes)."""
    colors = [
        "#4f46e5",
        "#059669",
        "#d97706",
        "#dc2626",
        "#0891b2",
        "#7c3aed",
        "#db2777",
        "#ca8a04",
    ]
    return colors[zlib.crc32(str(name).encode("utf-8")) % len(colors)]


def _avatar_html(name, size=32):
    """Generate an avatar circle with initials."""
    i = _initials(name)
    c = _avatar_color(name)
    return f'<div class="avatar" style="width:{size}px;height:{size}px;background:{c}20;color:{c};font-size:{size // 2}px;font-weight:700;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;" title="{h(name)}">{h(i)}</div>'


CAT_COLORS = {
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


def cat_color(c):
    return CAT_COLORS.get(c, CAT_COLORS["Other"])


# Make helper functions available in Jinja2 templates
app.jinja_env.globals["_avatar_html"] = _avatar_html
app.jinja_env.globals["_initials"] = _initials

# ──


# ──

# ══════════════════════════════════════════════════════════════════════
# Phase 7: centralized error handlers
# ══════════════════════════════════════════════════════════════════════
# Every status gets a consistent response: a JSON envelope for API paths,
# a styled page (templates/errors/error_page.html -> error_base.html) for
# browsers. Never a raw traceback in production.

_ERROR_PAGES = {
    400: (
        "400",
        "Bad Request",
        "⚠️",
        "The request could not be understood. Check the submitted data and try again.",
    ),
    401: ("401", "Unauthorized", "🔒", "You need to sign in to access this page."),
    403: (
        "403",
        "Forbidden",
        "⛔",
        "You don't have permission to access this resource.",
    ),
    404: (
        "404",
        "Page Not Found",
        "🔍",
        "The page you're looking for doesn't exist or was moved.",
    ),
    405: (
        "405",
        "Method Not Allowed",
        "🚫",
        "This URL doesn't accept that request method.",
    ),
    409: (
        "409",
        "Conflict",
        "⚔️",
        "The request conflicts with the current state of the resource.",
    ),
    413: (
        "413",
        "Request Too Large",
        "📦",
        "The uploaded file or request is too large.",
    ),
    415: (
        "415",
        "Unsupported Media Type",
        "🧩",
        "The request payload is in an unsupported format.",
    ),
    422: (
        "422",
        "Unprocessable Entity",
        "📋",
        "The request was well-formed but could not be processed.",
    ),
    429: (
        "429",
        "Too Many Requests",
        "🐌",
        "You've made too many requests. Please slow down and try again shortly.",
    ),
    500: (
        "500",
        "Server Error",
        "🛠️",
        "Something went wrong on our end. Please try again later.",
    ),
}


# JSON error envelope for API consumers; HTML error page for browsers.
# /api/docs is a browser page (Swagger UI), so it stays on the HTML path.
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


# 404/500 get their own explicit handlers below (they need special logging
# and must never expose internals); the loop covers the remaining codes
# (derived from _ERROR_PAGES so a new status can't silently miss a handler).
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
def _server_error(e):
    from app.core.logger import log as _err_log

    _err_log(f"unhandled exception: {e!r}", "error")
    return _error_response(500, _ERROR_PAGES[500][3])


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ──


def render_auth_page(title, content, **kw):
    """Render an auth page using the split-screen auth_base.html template."""
    from flask import render_template

    return render_template("auth_base.html", title=title, auth_content=content, session={}, **kw)


# ──────────────────────────────────────────────────────────────────────────
# Phase 7: Health endpoints
# ──────────────────────────────────────────────────────────────────────────


@app.route("/healthz")
def healthz():
    """Liveness probe: confirms the process is alive and responding."""
    return jsonify({"status": "ok"}), 200


@app.route("/readyz")
def readyz():
    """Readiness probe: confirms the DB is reachable."""
    try:
        from sqlalchemy import text as _sqltext

        import app.db.database as _dbmod

        with _dbmod.get_session_factory()() as db_session:
            db_session.execute(_sqltext("SELECT 1"))
        return jsonify({"status": "ok", "database": "connected"}), 200
    except Exception as e:
        from app.core.logger import log as _log

        _log(f"readyz probe failed: {e}", "health")
        # Never leak driver names, connection strings, or internal paths to
        # clients — the detail stays in the log for operators (info disclosure).
        return jsonify({"status": "not_ready", "error": "database unreachable"}), 503


# ──────────────────────────────────────────────────────────────────────────
# Phase 5: real generated OpenAPI spec + Swagger UI
# ──────────────────────────────────────────────────────────────────────────
# api_spec.build_openapi_spec() documents the app's ACTUAL endpoints; Swagger
# UI (pinned CDN) renders it with working "Try it out" — the README's
# "/api/docs" claim is now real and executable against a running instance.


@app.route("/api/openapi.json")
def api_openapi_json():
    """Serve the generated OpenAPI 3.1 document."""
    from app.api.api_spec import build_openapi_spec

    return jsonify(build_openapi_spec())


@app.route("/api/docs")
def api_docs():
    """Swagger UI for the BookTale API (pinned CDN, matches the CSP)."""
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


@app.route("/security")
def security_page():
    """Public trust page: what BookTale actually does for security.

    Every claim here is implemented and covered by a regression test (see
    docs/SECURITY.md for the mapping) — no aspirational marketing.
    """
    items = [
        (
            "🔑",
            "Password hashing",
            "Passwords are stored as bcrypt hashes; the policy requires 12+ characters, enforced server-side on every password surface (registration, reset, settings).",
        ),
        (
            "🛡️",
            "Role-safe registration",
            'Self-service registration can only ever create "user" accounts — client-supplied admin/librarian roles are silently downgraded.',
        ),
        (
            "🎫",
            "CSRF protection",
            "CSRFProtect is enabled by default; every state-changing POST without a valid session token is rejected (400).",
        ),
        (
            "⏱️",
            "Rate limiting",
            "Auth endpoints and all shared-surface writes are rate-limited (per-IP and per-account), so brute-force and spam attempts are throttled without locking real users out.",
        ),
        (
            "🔒",
            "Fail-fast boot",
            "The app refuses to boot with a default/empty SECRET_KEY or debug mode outside development.",
        ),
        (
            "📄",
            "Secure sessions",
            "Session cookies are HttpOnly + SameSite=Lax (Secure when deployed over HTTPS); HSTS headers are applied on the edge.",
        ),
        (
            "🎨",
            "Upload verification",
            "Image uploads are magic-byte verified with Pillow and re-encoded server-side — a renamed HTML/JS file is rejected, and embedded payloads are stripped.",
        ),
        (
            "⏳",
            "One-time tokens",
            "Password-reset (15 min) and email-verify (24 h) tokens are stored in the database with explicit expiry; they survive restarts and are consumed once.",
        ),
        (
            "📋",
            "Audit trail",
            "Every admin-settings change is recorded (who/what/when/from-where) in an append-only audit log; secrets are redacted.",
        ),
        (
            "🧪",
            "Security regression tests",
            "Privilege escalation, CSRF, rate limiting, XSS round-trips, upload forgery, and token expiry all have automated regression tests (tests/security/).",
        ),
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


@app.route("/login", methods=["GET", "POST"])
# Split rate limit (Phase 4): only FAILED credential attempts count.
# - methods=["POST"]: the limit is scoped to POST, so GET page loads are
#   never checked against (or charged to) this budget.
# - exempt_when: belt-and-braces — GET requests are exempt from the check.
# - deduct_when: called with the response AFTER the view runs; it returns
#   True only when the view flagged g._login_failed, so a user who types
#   their password correctly is never charged by the same-IP failure counter.
@_rate_limit(
    "10 per minute",
    methods=["POST"],
    exempt_when=lambda: request.method == "GET",
    deduct_when=lambda response: getattr(g, "_login_failed", False),
)
def login_page():
    if request.method == "GET":
        # Phase 3: real Jinja2 template (autoescape ON). The hero-stats fetch
        # lives in auth_base.html already, so no hero_script needed here.
        return render_template("auth/login.html", title="Login", form_aria_label="Login form")

    from app.core.exceptions import AuthenticationError

    try:
        user = auth.login(request.form["user_id"], request.form["password"])
        session["user_id"] = user.user_id
        session["user_name"] = user.name
        session["role"] = user.role
        log("Web login", user.user_id)
        return redirect(url_for("feed_page"))
    except AuthenticationError:
        # Flag the failure so the limiter's deduct_when counts THIS attempt
        # (only failed attempts consume the per-IP budget).
        g._login_failed = True
        return render_template(
            "auth/login.html", title="Login", error=True, form_aria_label="Login form"
        )


@app.route("/register", methods=["GET", "POST"])
# Split limit (Phase 4): page loads must never consume the anti-spam budget.
# GET /register is exempt (mirrors the login route's GET-exempt pattern);
# only POSTs count against the 5/min budget, so refreshing the form is free.
@_rate_limit("5 per minute", methods=["POST"], exempt_when=lambda: request.method == "GET")
def register_page():
    if request.method == "GET":
        # Phase 3: real Jinja2 template (autoescape ON).
        return render_template(
            "auth/register.html", title="Register", form_aria_label="Registration form"
        )

    # POST - handle registration
    user_id = request.form.get("user_id", "").strip()
    name = request.form.get("name", "").strip()
    password = request.form.get("password", "")
    confirm_pw = request.form.get("confirm_password", "")
    email = request.form.get("email", "").strip()
    role = request.form.get("role", "user")
    # ── Security: self-service registration can ONLY create "user" accounts.
    # Any attempt to self-assign an elevated role (admin/librarian) is
    # silently downgraded (CWE-269). Elevated roles require an admin action.
    if role not in ("user",):
        role = "user"

    errors = []
    if not user_id or not name or not password:
        errors.append("All required fields must be filled")
    if password != confirm_pw:
        errors.append("Passwords do not match")
    # Phase 4 (P1): password policy raised to >=12 chars, enforced server-side
    # (never trust client-side minlength/strength meters alone).
    if len(password) < 12:
        errors.append("Password must be at least 12 characters")
    if user_id and not user_id.startswith("MEM-"):
        errors.append("User ID must follow MEM-XXXX format")

    if errors:
        return render_template(
            "auth/register.html",
            title="Register",
            errors=errors,
            form_aria_label="Registration form",
        )

    users = storage.load_users()
    if user_id in users:
        return render_template(
            "auth/register.html",
            title="Register",
            error="User ID already exists",
            form_aria_label="Registration form",
        )

    from app.services.auth.auth import generate_verify_token as _gvt
    from app.services.auth.auth import hash_password as _hp

    lib.register_user(user_id, name, email, "", role, _hp(password), actor="registration")

    # Send welcome email with verification link
    if email:
        try:
            from app.services.email.email_notifier import send_email

            token = _gvt(user_id)
            verify_url = request.host_url.rstrip("/") + "/verify-email?token=" + token
            send_email(
                email,
                "Welcome to BookTale!",
                (
                    "<h2>Welcome to BookTale!</h2>"
                    "<p>Thanks for joining, " + name + "!</p>"
                    "<p>Please verify your email address:</p>"
                    '<p><a href="'
                    + verify_url
                    + '" style="display:inline-block;padding:.6rem 1.2rem;background:#4f46e5;color:white;text-decoration:none;border-radius:8px;">Verify Email</a></p>'
                    "<p>Or copy this link: " + verify_url + "</p>"
                    "<p>Happy reading!</p>"
                ),
            )
        except Exception as e:
            print("Welcome email error:", e)

    # Phase 3: name/email passed as template vars — autoescape ON kills the
    # stored-XSS surface here (previously concatenated raw into HTML).
    return render_template(
        "auth/registered.html", title="Registered", name=name, email=email or None
    )


@app.route("/forgot-password", methods=["GET", "POST"])
# Split limit (Phase 4): page loads must never consume the anti-spam budget.
# GET /forgot-password is exempt; only POSTs count against the 5/min budget.
@_rate_limit("5 per minute", methods=["POST"], exempt_when=lambda: request.method == "GET")
def forgot_password_page():
    if request.method == "GET":
        # Phase 3: real Jinja2 template (autoescape ON).
        return render_template(
            "auth/forgot_password.html",
            title="Forgot Password",
            form_aria_label="Password reset form",
        )

    # POST - anti-enumeration: always show success
    identity = request.form.get("identity", "").strip()
    if identity:
        try:
            from app.services.auth.auth import generate_reset_token as _grt

            users = storage.load_users()
            target_user = None
            for u in users.values():
                if u.user_id == identity or u.email == identity:
                    target_user = u
                    break
            if target_user and target_user.email:
                from app.services.email.email_notifier import send_email

                token = _grt(target_user.user_id)
                reset_url = request.host_url.rstrip("/") + "/reset-password?token=" + token
                send_email(
                    target_user.email,
                    "Reset your BookTale password",
                    (
                        "<h2>Password Reset Request</h2>"
                        "<p>Hi " + target_user.name + ",</p>"
                        "<p>Click the button below to reset your password:</p>"
                        '<p><a href="'
                        + reset_url
                        + '" style="display:inline-block;padding:.6rem 1.2rem;background:#4f46e5;color:white;text-decoration:none;border-radius:8px;">Reset Password</a></p>'
                        "<p>Or copy this link: " + reset_url + "</p>"
                        "<p>This link expires in 15 minutes.</p>"
                        "<p>If you did not request this, you can safely ignore this email.</p>"
                    ),
                )
        except Exception as e:
            print("Reset email error:", e)

    return render_template(
        "auth/forgot_password.html",
        title="Email Sent",
        sent=True,
        form_aria_label="Password reset form",
    )


@app.route("/verify-email")
def verify_email_page():
    token = request.args.get("token", "")
    if not token:
        CONTENT = (
            '<div class="text-center">'
            '<div style="font-size:4rem;margin-bottom:1rem;">🔗</div>'
            "<h2>Invalid Link</h2>"
            '<p class="auth-subtitle">No verification token provided.</p>'
            "</div>"
            '<a href="/login" class="btn btn-primary"><i class="bi bi-arrow-left me-2"></i> Back to Login</a>'
        )
        return render_auth_page("Verify Email", CONTENT)

    from app.services.auth.auth import consume_verify_token as _cvt

    user_id = _cvt(token)

    if not user_id:
        CONTENT = (
            '<div class="text-center">'
            '<div style="font-size:4rem;margin-bottom:1rem;">⏰</div>'
            "<h2>Invalid or Expired Link</h2>"
            '<p class="auth-subtitle">This verification link has expired or is invalid. Please register again for a new link.</p>'
            "</div>"
            '<a href="/register" class="btn btn-primary"><i class="bi bi-person-plus-fill me-2"></i> Register Again</a>'
        )
        return render_auth_page("Verify Email", CONTENT)

    users = storage.load_users()
    if user_id in users:
        users[user_id].email_verified = True
        storage.save_users(users)

    CONTENT = (
        '<div class="text-center">'
        '<div style="font-size:4rem;margin-bottom:1rem;">✅</div>'
        "<h2>Email Verified!</h2>"
        '<p class="auth-subtitle">Your email has been verified. You can now access all features.</p>'
        "</div>"
        '<a href="/login" class="btn btn-primary"><i class="bi bi-shield-lock-fill me-2"></i> Sign In</a>'
    )
    return render_auth_page("Email Verified", CONTENT)


@app.route("/reset-password", methods=["GET", "POST"])
# Split limit (Phase 4): page loads must never consume the anti-spam budget.
# GET /reset-password (valid or invalid token) is exempt; only POSTs count.
@_rate_limit("5 per minute", methods=["POST"], exempt_when=lambda: request.method == "GET")
def reset_password_page():
    if request.method == "GET":
        token = request.args.get("token", "")
        if not token:
            return render_auth_page(
                "Reset Password",
                (
                    '<div class="text-center">'
                    '<div style="font-size:4rem;margin-bottom:1rem;">🔗</div>'
                    "<h2>Invalid Link</h2>"
                    '<p class="auth-subtitle">This reset link is missing or invalid.</p>'
                    '<a href="/forgot-password" class="btn btn-primary mt-3">Request New Link</a>'
                    "</div>"
                ),
            )
        from app.services.auth.auth import verify_reset_token as _vrt

        uid = _vrt(token)
        if not uid:
            return render_auth_page(
                "Reset Password",
                (
                    '<div class="text-center">'
                    '<div style="font-size:4rem;margin-bottom:1rem;">⏰</div>'
                    "<h2>Link Expired</h2>"
                    '<p class="auth-subtitle">This reset link has expired. Please request a new one.</p>'
                    '<a href="/forgot-password" class="btn btn-primary mt-3">Request New Link</a>'
                    "</div>"
                ),
            )

        # Phase 4: CSRF token for the string-built reset form (WTF_CSRF_ENABLED
        # is read per-request, so this is safe even when disabled in tests).
        # Narrow catches: only an ImportError (no flask-wtf) or a missing
        # request context can fail generate_csrf inside this view.
        try:
            from flask_wtf.csrf import generate_csrf as _gen_csrf
        except ImportError:
            _gen_csrf = None
        _csrf_hidden = ""
        if _gen_csrf is not None:
            try:
                _csrf_hidden = (
                    '<input type="hidden" name="csrf_token" ' 'value="' + _gen_csrf() + '">'
                )
            except (ImportError, RuntimeError):
                _csrf_hidden = ""

        CONTENT = (
            "<h2>Set New Password</h2>"
            '<p class="auth-subtitle">Enter your new password for account <strong>'
            + h(uid)
            + "</strong></p>"
            '<form method="POST" onsubmit="return validateResetForm()">'
            + _csrf_hidden
            + '<input type="hidden" name="token" value="'
            + token
            + '">'
            '<div class="mb-3"><label class="form-label">New Password *</label>'
            '<div class="input-group"><span class="input-group-text"><i class="bi bi-lock-fill"></i></span>'
            '<input type="password" name="password" class="form-control" placeholder="Min 12 characters" required id="resetPw" minlength="12" oninput="checkPwStrength(this.value)"></div>'
            '<div class="password-strength" id="resetPwStrength"></div>'
            '<small class="text-muted" id="resetPwHelp">At least 12 characters</small></div>'
            '<div class="mb-3"><label class="form-label">Confirm Password *</label>'
            '<div class="input-group"><span class="input-group-text"><i class="bi bi-lock-fill"></i></span>'
            '<input type="password" name="confirm_password" class="form-control" placeholder="Repeat password" required id="resetConfirmPw"></div></div>'
            '<button type="submit" class="btn btn-primary"><i class="bi bi-check-lg me-1"></i> Reset Password</button>'
            "</form>"
            '<div class="auth-divider">Remember your password?</div>'
            '<a href="/login" class="btn btn-outline"><i class="bi bi-box-arrow-in-right me-1"></i> Sign In</a>'
            "<script>"
            "function checkPwStrength(pw) {"
            'var bar = document.getElementById("resetPwStrength");'
            'var help = document.getElementById("resetPwHelp");'
            "if (!bar) return;"
            'if (pw.length === 0) { bar.className = "password-strength"; help.textContent = "At least 12 characters"; return; }'
            "var score = 0;"
            "if (pw.length >= 12) score++;"
            "if (pw.length >= 16) score++;"
            "if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) score++;"
            "if (/[0-9]/.test(pw)) score++;"
            "if (/[^A-Za-z0-9]/.test(pw)) score++;"
            'var classes = ["", "weak", "medium", "strong", "very-strong"];'
            'bar.className = "password-strength " + classes[Math.min(score, 4)];'
            'var labels = ["", "Weak", "Medium", "Strong", "Very Strong"];'
            "help.textContent = labels[Math.min(score, 4)];"
            "}"
            "function validateResetForm() {"
            'var pw = document.getElementById("resetPw").value;'
            'var cpw = document.getElementById("resetConfirmPw").value;'
            'if (pw !== cpw) { showToast("Passwords do not match", "error"); return false; }'
            'if (pw.length < 12) { showToast("Password must be at least 12 characters", "error"); return false; }'
            "return true;"
            "}"
            "</script>"
        )
        return render_auth_page("Reset Password", CONTENT)

    # POST - process password reset
    token = request.form.get("token", "")
    password = request.form.get("password", "")
    confirm_pw = request.form.get("confirm_password", "")

    if not token or not password:
        return render_auth_page(
            "Reset Password",
            '<div class="alert alert-danger">Invalid request</div><a href="/forgot-password" class="btn btn-primary">Request New Link</a>',
        )
    if password != confirm_pw:
        return render_auth_page(
            "Reset Password",
            '<div class="alert alert-danger">Passwords do not match</div><a href="/forgot-password" class="btn btn-primary">Request New Link</a>',
        )
    if len(password) < 12:
        return render_auth_page(
            "Reset Password",
            '<div class="alert alert-danger">Password must be at least 12 characters</div><a href="/forgot-password" class="btn btn-primary">Request New Link</a>',
        )

    from app.services.auth.auth import consume_reset_token as _crt
    from app.services.auth.auth import hash_password as _hp

    user_id = _crt(token)
    if not user_id:
        return render_auth_page(
            "Reset Password",
            '<div class="alert alert-danger">Invalid or expired reset link</div><a href="/forgot-password" class="btn btn-primary">Request New Link</a>',
        )

    users = storage.load_users()
    user = users.get(user_id)
    if not user:
        return render_auth_page(
            "Reset Password",
            '<div class="alert alert-danger">User not found</div><a href="/forgot-password" class="btn btn-primary">Request New Link</a>',
        )

    user.password_hash = _hp(password)
    storage.save_users(users)
    log("Password reset", user_id)

    return render_auth_page(
        "Password Reset",
        (
            '<div class="text-center">'
            '<div style="font-size:4rem;margin-bottom:1rem;">🔐</div>'
            "<h2>Password Reset!</h2>"
            '<p class="auth-subtitle">Your password has been successfully changed.</p>'
            '<a href="/login" class="btn btn-primary mt-3"><i class="bi bi-box-arrow-in-right me-1"></i> Sign In</a>'
            "</div>"
        ),
    )


# HELP PAGE


@app.route("/help")
@login_required
def help_page():
    CONTENT = '<div class="animate-in">'
    CONTENT += '<div class="glass-card p-0 mb-4" style="overflow:hidden;">'
    CONTENT += '<div class="p-4" style="background:linear-gradient(135deg,var(--primary),#7c3aed);color:white;">'
    CONTENT += '<h4 class="fw-bold mb-0"><i class="bi bi-question-circle-fill me-2"></i> Help &amp; Support</h4>'
    CONTENT += '<p class="mb-0" style="opacity:.8;font-size:.85rem;">Guides, tips, and frequently asked questions</p>'
    CONTENT += "</div></div>"
    CONTENT += '<div class="row g-4">'
    # Getting Started
    CONTENT += '<div class="col-md-6"><div class="glass-card p-4">'
    CONTENT += '<h5 class="fw-bold mb-3"><i class="bi bi-book-fill text-primary me-2"></i>Getting Started</h5>'
    CONTENT += '<ul class="list-unstyled" style="font-size:.9rem;">'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-primary me-2"></i> Browse and search books from the Explore page</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-primary me-2"></i> Issue books from the book details page</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-primary me-2"></i> Write reviews and rate books you have read</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-primary me-2"></i> Connect with other readers in the community</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-primary me-2"></i> Create reading lists and track your progress</li>'
    CONTENT += "</ul></div>"
    # Account Settings
    CONTENT += '<div class="glass-card p-4">'
    CONTENT += '<h5 class="fw-bold mb-3"><i class="bi bi-gear-fill text-warning me-2"></i>Account Settings</h5>'
    CONTENT += '<ul class="list-unstyled" style="font-size:.9rem;">'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-warning me-2"></i> Update your profile information in <a href=\'/settings\'>Settings</a></li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-warning me-2"></i> Change notification preferences</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-warning me-2"></i> Manage privacy settings for your profile</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-warning me-2"></i> Customize appearance with themes and font sizes</li>'
    CONTENT += "</ul></div></div>"
    # Library Rules
    CONTENT += '<div class="col-md-6"><div class="glass-card p-4">'
    CONTENT += '<h5 class="fw-bold mb-3"><i class="bi bi-shield-lock-fill text-info me-2"></i>Library Rules</h5>'
    CONTENT += '<ul class="list-unstyled" style="font-size:.9rem;">'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-info me-2"></i> Books can be issued for a limited period</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-info me-2"></i> Late returns incur a fine per day</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-info me-2"></i> Maximum borrow limit applies per user</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-arrow-right-circle text-info me-2"></i> Membership must be renewed periodically</li>'
    CONTENT += "</ul></div>"
    # Need Help
    CONTENT += '<div class="glass-card p-4">'
    CONTENT += '<h5 class="fw-bold mb-3"><i class="bi bi-envelope-fill text-success me-2"></i>Need Help?</h5>'
    CONTENT += '<p style="font-size:.9rem;">If you encounter any issues or have questions:</p>'
    CONTENT += '<ul class="list-unstyled" style="font-size:.9rem;">'
    CONTENT += '<li class="mb-2"><i class="bi bi-envelope-fill text-success me-2"></i> Contact the library staff for assistance</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-chat-dots-fill text-success me-2"></i> Post in the community for peer support</li>'
    CONTENT += '<li class="mb-2"><i class="bi bi-journal-text text-success me-2"></i> Check the <a href=\'/feed\'>Feed</a> for announcements</li>'
    CONTENT += "</ul></div></div></div></div>"
    return render_page("Help & Support", CONTENT)


# ──


@app.route("/settings")
@login_required
def settings_page():
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

    # Privacy toggles
    p_checks = [
        (
            "privacy_show_activity",
            "Show reading activity on profile",
            "graph-up-arrow",
            user.privacy_show_activity,
        ),
        (
            "privacy_show_wishlist",
            "Show wishlist on profile",
            "star-fill",
            user.privacy_show_wishlist,
        ),
        (
            "privacy_show_bookmarks",
            "Show bookmarks on profile",
            "bookmark-fill",
            user.privacy_show_bookmarks,
        ),
        (
            "privacy_show_email",
            "Show email on profile",
            "envelope-fill",
            user.privacy_show_email,
        ),
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
        label = {
            "perfection": "Perfection",
            "worth_it": "Worth It",
            "timepass": "Timepass",
            "skip": "Skip",
        }[v]
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

<!-- Settings Tabs -->
<nav class="settings-tabs mb-3" role="tablist" aria-label="Settings sections">
    <button class="settings-tab active" role="tab" aria-selected="true" data-tab="profile" onclick="switchSettingsTab(this)"><i class="bi bi-person-fill"></i> Profile</button>
    <button class="settings-tab" role="tab" aria-selected="false" data-tab="notifications" onclick="switchSettingsTab(this)"><i class="bi bi-bell-fill"></i> Notifications</button>
    <button class="settings-tab" role="tab" aria-selected="false" data-tab="privacy" onclick="switchSettingsTab(this)"><i class="bi bi-shield-lock-fill"></i> Privacy</button>
    <button class="settings-tab" role="tab" aria-selected="false" data-tab="appearance" onclick="switchSettingsTab(this)"><i class="bi bi-palette-fill"></i> Appearance</button>
    <button class="settings-tab" role="tab" aria-selected="false" data-tab="reading" onclick="switchSettingsTab(this)"><i class="bi bi-book-fill"></i> Reading</button>
</nav>

<!-- Profile Tab -->
<div class="settings-panel active" id="tab-profile" role="tabpanel">
    <div class="glass-card p-4">
        <h5 class="fw-bold mb-3"><i class="bi bi-person-fill text-primary me-2"></i>Profile Information</h5>
        <form id="profileSettingsForm" onsubmit="return saveProfileSettings()">
            <div class="row">
                <div class="col-md-6 mb-3">
                    <label class="form-label">Display Name</label>
                    <input type="text" class="form-control" id="sName" value="NAME_V" required>
                </div>
                <div class="col-md-6 mb-3">
                    <label class="form-label">Email</label>
                    <input type="email" class="form-control" id="sEmail" value="EMAIL_V">
                </div>
            </div>
            <div class="row">
                <div class="col-md-6 mb-3">
                    <label class="form-label">Phone</label>
                    <input type="text" class="form-control" id="sPhone" value="PHONE_V">
                </div>
                <div class="col-md-6 mb-3">
                    <label class="form-label">Website</label>
                    <input type="url" class="form-control" id="sWebsite" value="WEB_V" placeholder="https://example.com">
                </div>
            </div>
            <div class="mb-3">
                <label class="form-label">Location</label>
                <input type="text" class="form-control" id="sLocation" value="LOC_V" placeholder="City, Country">
            </div>
            <div class="mb-3">
                <label class="form-label">Bio</label>
                <textarea class="form-control" id="sBio" rows="3" placeholder="Tell us about yourself...">BIO_V</textarea>
            </div>
            <div class="mb-3">
                <label class="form-label">Change Password</label>
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

<!-- Notifications Tab -->
<div class="settings-panel" id="tab-notifications" role="tabpanel">
    <div class="glass-card p-4">
        <h5 class="fw-bold mb-3"><i class="bi bi-bell-fill text-warning me-2"></i>Notification Preferences</h5>
        <p class="text-muted small mb-3">Control which notifications you receive</p>
        NOTIF_HTML
    </div>
</div>

<!-- Privacy Tab -->
<div class="settings-panel" id="tab-privacy" role="tabpanel">
    <div class="glass-card p-4">
        <h5 class="fw-bold mb-3"><i class="bi bi-shield-lock-fill text-info me-2"></i>Privacy Settings</h5>
        <div class="mb-3">
            <label class="form-label">Profile Visibility</label>
            <select class="form-select" id="sProfileVis" onchange="saveProfileVisibility(this)">
                VIS_OPTS
            </select>
        </div>
        <p class="text-muted small mb-3">Control what appears on your public profile</p>
        PRIV_HTML
    </div>
</div>

<!-- Appearance Tab -->
<div class="settings-panel" id="tab-appearance" role="tabpanel">
    <div class="glass-card p-4">
        <h5 class="fw-bold mb-3"><i class="bi bi-palette-fill text-purple me-2"></i>Appearance</h5>
        <div class="mb-4">
            <label class="form-label">Theme</label>
            <div class="d-flex gap-3">
                <label class="theme-option%s" onclick="selectTheme('light')">
                    <input type="radio" name="theme" value="light" class="d-none" %s>
                    <i class="bi bi-sun-fill" style="font-size:1.5rem;"></i>
                    <span>Light</span>
                </label>
                <label class="theme-option%s" onclick="selectTheme('dark')">
                    <input type="radio" name="theme" value="dark" class="d-none" %s>
                    <i class="bi bi-moon-fill" style="font-size:1.5rem;"></i>
                    <span>Dark</span>
                </label>
            </div>
        </div>
        <div class="mb-3">
            <label class="form-label">Font Size</label>
            <div class="d-flex gap-2">
                <button class="btn %s" onclick="selectFont('small')" id="fontSmall">A-</button>
                <button class="btn %s" onclick="selectFont('medium')" id="fontMedium">A</button>
                <button class="btn %s" onclick="selectFont('large')" id="fontLarge">A+</button>
            </div>
        </div>
    </div>
</div>

<!-- Reading Tab -->
<div class="settings-panel" id="tab-reading" role="tabpanel">
    <div class="glass-card p-4">
        <h5 class="fw-bold mb-3"><i class="bi bi-book-fill text-success me-2"></i>Reading Preferences</h5>
        <div class="row">
            <div class="col-md-6 mb-3">
                <label class="form-label">Default Rating Label</label>
                <select class="form-select" id="sDefaultRating">RATING_OPTS</select>
            </div>
            <div class="col-md-6 mb-3">
                <label class="form-label">Reading Goal Type</label>
                <select class="form-select" id="sGoalType">GOAL_OPTS</select>
            </div>
        </div>
        <div class="mb-3">
            <label class="form-label">Default Reading Goal</label>
            <input type="number" class="form-control" id="sDefaultGoal" value="GOAL_VAL" min="1" max="365">
            <small class="text-muted">Books or pages per year</small>
        </div>
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

    # Theme/font button styling
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
        light_sel,
        light_chk,
        dark_sel,
        dark_chk,
        font_classes[0],
        font_classes[1],
        font_classes[2],
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
    btn.disabled = true; btn.innerHTML = "<span class=\'spinner-border spinner-border-sm\'></span> Saving...";
    fetch("/api/settings/save", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(data)
    }).then(function(r){ return r.json() }).then(function(d){
        btn.disabled = false; btn.innerHTML = "<i class=\'bi bi-check-lg\'></i> Save Changes";
        if(d.success) { showToast("Profile updated!", "success"); setTimeout(function(){ location.reload(); }, 1000); }
        else showToast(d.error || "Failed", "error");
    }).catch(function(){ btn.disabled = false; btn.innerHTML = "<i class=\'bi bi-check-lg\'></i> Save Changes"; });
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
    document.querySelector(".theme-option input[value=\'"+t+"\']").closest(".theme-option").classList.add("active");
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


@app.route("/api/settings/save", methods=["POST"])
@login_required
# Defense in depth (Phase 4): /api/settings/save hosts password changes, so a
# session-holder could brute-force the current-password field. Only FAILED
# password-change attempts consume the budget (deduct_when); ordinary settings
# toggles (each a separate POST) and successful changes are never throttled.
# key_func=_user_key: the budget is per-account, so a distributed attacker
# cannot evade it by spreading requests across many source IPs.
@_rate_limit(
    "10 per minute",
    key_func=_user_key,
    deduct_when=lambda response: getattr(g, "_pw_change_failed", False),
)
def api_save_settings():
    """Save user settings."""
    uid = session["user_id"]
    data = request.get_json() or {}
    users = storage.load_users()
    user = users.get(uid)
    if not user:
        return jsonify({"success": False, "error": "User not found"})

    # Profile fields
    for key in ["name", "email", "phone", "bio", "website", "location"]:
        if key in data:
            setattr(user, key, data[key])
            if key == "name":
                session["user_name"] = data[key]

    # Toggle/boolean fields
    for key in [
        "email_notifications",
        "push_notifications",
        "notify_on_comment",
        "notify_on_like",
        "notify_on_follow",
        "notify_on_issue_return",
        "notify_on_overdue",
        "notify_on_due_reminder",
        "privacy_show_activity",
        "privacy_show_wishlist",
        "privacy_show_bookmarks",
        "privacy_show_email",
    ]:
        if key in data:
            setattr(user, key, bool(data[key]))

    # String fields
    for key in [
        "theme",
        "font_size",
        "privacy_profile_visibility",
        "reading_default_rating",
        "reading_goal_type",
    ]:
        if key in data:
            setattr(user, key, str(data[key]))

    # Integer fields
    if "reading_default_goal" in data:
        with contextlib.suppress(ValueError, TypeError):
            user.reading_default_goal = int(data["reading_default_goal"])

    # Password change
    if data.get("new_password"):
        from app.services.auth.auth import hash_password as _hp
        from app.services.auth.auth import verify_password as _vp

        cur = data.get("current_password", "")
        if not cur or not _vp(cur, user.password_hash):
            # Flag the failure so the limiter's deduct_when counts THIS
            # attempt (only failed password changes consume the per-IP budget).
            g._pw_change_failed = True
            return jsonify({"success": False, "error": "Current password is incorrect"})
        # Phase 4 (P1): the same >=12 policy enforced on the web forms applies
        # here — the settings API is a server-side password-change surface.
        if len(data["new_password"]) < 12:
            return jsonify({"success": False, "error": "Password must be at least 12 characters"})
        user.password_hash = _hp(data["new_password"])
        log("Password changed via settings", uid)

    storage.save_users(users)
    return jsonify({"success": True, "message": "Settings saved"})


# ──


@app.route("/admin/settings")
@admin_required
def admin_settings_page():
    """Admin settings page for managing system-wide configuration."""
    from app.config.settings import Config as C

    issue_d = C.ISSUE_DAYS
    fine_d = C.FINE_PER_DAY
    max_b = C.MAX_BORROW_LIMIT
    mem_v = C.MEMBERSHIP_VALIDITY_DAYS
    max_u = C.MAX_UPLOAD_SIZE // (1024 * 1024)  # Convert bytes to MB
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
    btn.disabled = true; btn.innerHTML = "<span class=\'spinner-border spinner-border-sm\'></span> Saving...";
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
        btn.disabled = false; btn.innerHTML = "<i class=\'bi bi-check-lg\'></i> Save All Admin Settings";
        return false;
    }
    fetch("/api/admin/settings/save", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(data)
    }).then(function(r){ return r.json() }).then(function(d){
        btn.disabled = false; btn.innerHTML = "<i class=\'bi bi-check-lg\'></i> Save All Admin Settings";
        if(d.success) { showToast("Admin settings saved!", "success"); setTimeout(function(){ location.reload(); }, 1000); }
        else showToast(d.error || "Failed", "error");
    }).catch(function(){ btn.disabled = false; btn.innerHTML = "<i class=\'bi bi-check-lg\'></i> Save All Admin Settings"; });
    return false;
}
</script>
""",
    )


@app.route("/api/admin/settings/save", methods=["POST"])
@admin_required
# Defense in depth: /api/admin/settings/save verifies the admin's current
# password (and can rotate it + write SMTP secrets), so a compromised admin
# session could brute-force the current_admin_password field. Only FAILED
# admin-password verifications consume the budget (deduct_when); successful
# saves are never throttled. key_func=_user_key: per-admin-account budget, so
# distributed source IPs cannot evade the limit.
@_rate_limit(
    "10 per minute",
    key_func=_user_key,
    deduct_when=lambda response: getattr(g, "_admin_pw_failed", False),
)
def api_save_admin_settings():
    """Save admin settings to settings_override.json."""
    data = request.get_json() or {}

    # Verify admin password
    from app.services.auth.auth import hash_password as _hp
    from app.services.auth.auth import verify_password as _vp

    uid = session["user_id"]
    users = storage.load_users()
    admin = users.get(uid)
    if not admin:
        return jsonify({"success": False, "error": "Admin not found"})
    cur_pw = data.get("current_admin_password", "")
    if not cur_pw or not _vp(cur_pw, admin.password_hash):
        # Flag the failure so the limiter's deduct_when counts THIS attempt
        # (only failed admin-password verifications consume the per-IP budget).
        g._admin_pw_failed = True
        # Audit trail: failed admin-password verification (who tried, from where).
        _audit_log(uid, "auth.failed", "admin_password", new_value="attempt rejected")
        return jsonify({"success": False, "error": "Current password is incorrect"})

    # Build override dict, capturing old values for the audit trail.
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
            # Audit trail: record the change (old -> new) per setting key.
            old_val = getattr(Config, cfg_key, None)
            _audit_log(
                uid,
                "settings.update",
                cfg_key,
                old_value=str(old_val) if old_val is not None else None,
                new_value=str(data[key]),
            )

    # SMTP password (only if provided) — value never stored in the audit trail.
    if data.get("smtp_password"):
        override["SMTP_PASSWORD"] = data["smtp_password"]
        _audit_log(
            uid,
            "settings.update",
            "SMTP_PASSWORD",
            old_value=None,
            new_value="[redacted]",
        )

    # Change admin password if requested — value never stored in the audit trail.
    if data.get("new_admin_password"):
        npw = data["new_admin_password"]
        if len(npw) >= 6:
            admin.password_hash = _hp(npw)
            log("Admin password changed via admin settings", uid)
            _audit_log(
                uid,
                "admin.password_change",
                "ADMIN_PASSWORD",
                old_value=None,
                new_value="[redacted]",
            )

    import json

    os.makedirs(Config.DATA_DIR, exist_ok=True)
    override_path = os.path.join(Config.DATA_DIR, "settings_override.json")
    with open(override_path, "w", encoding="utf-8") as f:
        json.dump(override, f, indent=2)

    storage.save_users(users)
    log("Admin settings saved", uid)
    return jsonify(
        {
            "success": True,
            "message": "Admin settings saved. Some changes may require a restart.",
        }
    )


# MISSING API ENDPOINTS (needed by frontend JS modules)


@app.route("/api/books/trending")
@login_required
def api_books_trending():
    """Get trending books based on issue count or seed data."""
    limit = min(int(request.args.get("limit", 10)), 30)
    if recommender:
        try:
            recs = recommender.recommend_trending(top_n=limit)
            return jsonify(recs)
        # Optional sub-feature: degrade gracefully, never break the request.
        except Exception:  # nosec B110
            pass
    books = storage.load_books()
    all_books = [b for b in books.values() if not b.is_deleted]
    sorted_books = sorted(
        all_books, key=lambda b: b.issue_count or b.average_rating or 0, reverse=True
    )[:limit]
    return jsonify(
        [
            {
                "book_id": b.book_id,
                "title": b.title,
                "author": b.author,
                "category": b.category,
                "issue_count": b.issue_count,
                "available": b.available_copies,
            }
            for b in sorted_books
        ]
    )


@app.route("/api/books/random")
@login_required
def api_book_random():
    """Get a random book for the dashboard spotlight."""
    books = storage.load_books()
    all_books = [b for b in books.values() if not b.is_deleted]
    if not all_books:
        return jsonify({"error": "No books available"}), 404
    # Non-security 'surprise me' pick - not used for crypto/tokens.
    b = random.choice(all_books)  # nosec B311
    return jsonify(
        {
            "book_id": b.book_id,
            "title": b.title,
            "author": b.author,
            "category": b.category,
            "available_copies": b.available_copies,
            "issue_count": b.issue_count,
            "description": getattr(b, "description", ""),
        }
    )


@app.route("/api/users/suggested")
@login_required
def api_users_suggested():
    """Get suggested users to follow (excluding current user and already following)."""
    uid = session["user_id"]
    users = storage.load_users()
    following_set = set()
    if social:
        with contextlib.suppress(Exception):
            following_set = set(social.get_following(uid))
    suggested = []
    for u in users.values():
        if u.user_id != uid and u.user_id not in following_set:
            suggested.append({"user_id": u.user_id, "name": u.name, "role": u.role})
            if len(suggested) >= 6:
                break
    return jsonify(suggested)


@app.route("/api/seed/stats")
def api_seed_stats():
    """Get stats including Goodreads seed dataset counts for landing page."""
    s = _library_stats() if "storage" in dir() else {}
    try:
        # Try to load seed data stats
        from app.services.recommendations.seed_data import get_seed_stats

        seed = get_seed_stats()
        total_books = seed.get("total_books", s.get("total_books", 0))
        total_users = max(s.get("total_users", 0), 10000)
        return jsonify(
            {
                "total_books": total_books,
                "total_users": total_users,
                "total_ratings": seed.get("total_ratings", 0),
            }
        )
    except:
        return jsonify(
            {
                "total_books": s.get("total_books", 0),
                "total_users": s.get("total_users", 0),
                "total_ratings": 0,
            }
        )


@app.route("/api/ai/chat", methods=["POST"])
@login_required
# Abuse ceiling: the companion chat can be hammered for spam / load.
@_rate_limit("30 per minute")
def api_ai_chat():
    """AI Reading Companion - TF-IDF based book recommendations and Q&A."""
    data = request.get_json() or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify(
            {
                "error": "No message provided",
                "response": "Please ask me a question about books!",
            }
        )

    msg_lower = message.lower()

    # Simple rule-based responses (TF-IDF integration available with scipy/sklearn)
    if "recommend" in msg_lower or "suggest" in msg_lower or "read next" in msg_lower:
        uid = session["user_id"]
        try:
            recs = recommender.recommend_for_user(uid, top_n=3) if recommender else []
            if recs:
                titles = [r.get("title", "Unknown") for r in recs]
                response = (
                    "Based on your reading history, I recommend: "
                    + ", ".join(titles)
                    + ". Happy reading!"
                )
            else:
                # Fallback to trending
                trending = recommender.recommend_trending(top_n=3) if recommender else []
                if trending:
                    titles = [r.get("title", "Unknown") for r in trending]
                    response = (
                        "Here are some trending books you might enjoy: " + ", ".join(titles) + "."
                    )
                else:
                    response = "I'd recommend checking out our Explore page for trending books!"
        except:
            response = "I'm having trouble finding recommendations right now. Try browsing the Explore page!"
    elif "similar" in msg_lower or "like" in msg_lower:
        response = (
            "Try searching for a book and checking the 'Similar Books' section on its detail page!"
        )
    elif "summary" in msg_lower or "summarize" in msg_lower:
        response = "To get a summary, go to a book's detail page and check the description section!"
    elif "genre" in msg_lower or "category" in msg_lower:
        response = "We have many genres! Browse by category on the Books or Recommendations page."
    elif "hello" in msg_lower or "hi " in msg_lower or msg_lower == "hi":
        response = "Hello! I'm your AI Reading Companion. Ask me for book recommendations, or about specific books!"
    elif "thank" in msg_lower:
        response = "You're welcome! Happy reading! 📚"
    else:
        response = "That's a great question! I can help with book recommendations, finding similar books, or exploring genres. What would you like to know?"

    return jsonify({"response": response, "message": message})


@app.route("/api/reading-streak")
@login_required
def api_reading_streak():
    """Calculate reading streak based on diary entries."""
    uid = session["user_id"]
    try:
        entries, _ = diary_mgr.get_user_diary(uid, page=1, per_page=500) if diary_mgr else ([], 0)
        dates = sorted(
            {e.get("date_read", "")[:10] for e in entries if e.get("date_read")},
            reverse=True,
        )
        streak = 0
        from datetime import date as dt_date
        from datetime import timedelta

        today = dt_date.today()
        check_date = today
        for d in dates:
            try:
                d_date = dt_date.fromisoformat(d)
                if d_date == check_date or d_date == check_date - timedelta(days=1):
                    streak += 1
                    check_date = d_date
                elif d_date < check_date - timedelta(days=1):
                    break
            # Optional sub-feature: degrade gracefully, never break the request.
            except Exception:  # nosec B110
                pass
        return jsonify({"streak": streak, "total_days": len(dates)})
    except:
        return jsonify({"streak": 0, "total_days": 0})


@app.route("/api/analytics/monthly")
def api_analytics_monthly():
    """Get monthly analytics data for charts (no login required for landing page)."""
    books = storage.load_books()
    all_books = [b for b in books.values() if not b.is_deleted]
    months = [
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
    monthly = [0] * 12
    for b in all_books:
        try:
            dt = datetime.fromisoformat(b.added_on)
            monthly[dt.month - 1] += 1
        # Optional sub-feature: degrade gracefully, never break the request.
        except Exception:  # nosec B110
            pass
    return jsonify({"labels": months, "values": monthly})


@app.route("/api/analytics/categories")
def api_analytics_categories():
    """Get category distribution for charts."""
    books = storage.load_books()
    from collections import Counter

    counts = Counter(b.category for b in books.values() if not b.is_deleted)
    return jsonify({"labels": list(counts.keys()), "values": list(counts.values())})


@app.route("/api/analytics/activity")
def api_analytics_activity():
    """Get recent activity for 'Who to Follow' sidebar."""
    txns = storage.load_transactions()
    from collections import Counter

    user_counts = Counter(t.get("user_id", "") for t in txns if t.get("type") == "issue")
    return jsonify([{"user": uid, "count": cnt} for uid, cnt in user_counts.most_common(10)])


@app.route("/api/books")
@login_required
def api_books_search():
    """Search books API - for autocomplete and search overlays."""
    q = request.args.get("q", "").strip()
    sort = request.args.get("sort", "title")
    books = storage.load_books()
    all_books = [b for b in books.values() if not b.is_deleted]
    if q:
        ql = q.lower()
        all_books = [
            b
            for b in all_books
            if ql in b.title.lower() or ql in b.author.lower() or ql in (b.isbn or "").lower()
        ]
    if sort == "popular":
        all_books.sort(key=lambda b: b.issue_count, reverse=True)
    elif sort == "new":
        all_books.sort(key=lambda b: b.added_on, reverse=True)
    else:
        all_books.sort(key=lambda b: b.title.lower())
    return jsonify(
        [
            {
                "book_id": b.book_id,
                "title": b.title,
                "author": b.author,
                "category": b.category,
                "available_copies": b.available_copies,
                "pages": b.pages,
                "isbn": b.isbn,
            }
            for b in all_books[:24]
        ]
    )


@app.route("/admin/fines")
@login_required
@admin_required
def admin_fines_page():
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
