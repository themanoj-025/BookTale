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


def _rate_limit(limit_value: str, **kwargs: Any) -> Any:
    """Rate-limit decorator; no-op fallback if flask-limiter is not installed."""
    if limiter is None:
        return lambda f: f
    return limiter.limit(limit_value, **kwargs)


def _user_key() -> dict[str, str]:
    uid = session.get("user_id")
    if uid:
        return f"user:{uid}"
    return f"ip:{request.remote_addr}"


def _audit_log(admin_id: str, action: str, target: str = "", old_value: Any = None, new_value: Any = None) -> None:
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

def h(text: object) -> str:
    return html.escape(str(text))


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


def api_key_required(f: Callable[..., Any]) -> Callable[..., Any]:
    import secrets as _secrets

    @wraps(f)
    def d(*a: Any, **k: Any) -> Any:
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


def render_auth_page(title: str, content: str, **kw: Any) -> str:
    """Render an auth page using the split-screen auth_base.html template."""
    return render_template("auth_base.html", title=title, auth_content=content, session={}, **kw)


def _initials(name: str) -> str:
    parts = name.strip().split()
    if not parts:
        return "?"
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return parts[0][:2].upper()


def _avatar_color(name) -> dict:
    colors = [
        "#4f46e5", "#059669", "#d97706", "#dc2626",
        "#0891b2", "#7c3aed", "#db2777", "#ca8a04",
    ]
    return colors[zlib.crc32(str(name).encode("utf-8")) % len(colors)]


def _avatar_html(name: str, size: int = 32) -> str:
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


def cat_color(c: str) -> str:
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
def healthz() -> dict[str, str]:
    return jsonify({"status": "ok"}), 200


@app.route("/readyz")
def readyz() -> dict:
    try:
        from sqlalchemy import text as _sqltext
        import app.db.database as _dbmod

        with _dbmod.get_session_factory()() as db_session:
            db_session.execute(_sqltext("SELECT 1"))
        return jsonify({"status": "ok", "database": "connected"}), 200
    except (ValueError, KeyError, OSError) as e:
        from app.core.logger import log as _log
        _log(f"readyz probe failed: {e}", "health")
        return jsonify({"status": "not_ready", "error": "database unreachable"}), 503


# ════════════════════════════════════════════════════════════════════════════
# Prometheus metrics
# ════════════════════════════════════════════════════════════════════════════

try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

    BOOKTALE_REQUEST_COUNT = Counter(
        "booktale_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status"],
    )
    BOOKTALE_REQUEST_LATENCY = Histogram(
        "booktale_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "endpoint"],
        buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )
    BOOKTALE_ACTIVE_SESSIONS = Gauge(
        "booktale_active_sessions",
        "Number of active user sessions",
    )
    BOOKTALE_BOOKS_TOTAL = Gauge(
        "booktale_books_total", "Total books in the library"
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False


@app.before_request
def _prometheus_before_request() -> None:
    if not _PROMETHEUS_AVAILABLE:
        return
    from time import time as _time
    g._prom_start = _time()


@app.after_request
def _prometheus_after_request(response):
    if not _PROMETHEUS_AVAILABLE:
        return response
    # Skip the /metrics endpoint itself to avoid recursive counting
    if request.path == "/metrics":
        return response
    from time import time as _time

    endpoint = request.path
    # Normalise dynamic path segments to avoid high-cardinality labels
    if endpoint.startswith("/api/"):
        parts = endpoint.split("/")
        if len(parts) > 3 and parts[3].isdigit():
            endpoint = "/".join(parts[:3]) + "/{id}"
    method = request.method
    status = response.status_code

    BOOKTALE_REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=str(status)).inc()
    latency = _time() - getattr(g, "_prom_start", _time())
    BOOKTALE_REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(latency)
    return response


@app.route("/metrics")
def prometheus_metrics():
    """Prometheus scrape endpoint."""
    if not _PROMETHEUS_AVAILABLE:
        return jsonify({"status": "prometheus_client not installed"}), 501
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


# ════════════════════════════════════════════════════════════════════════════
# OpenAPI / Swagger UI
# ════════════════════════════════════════════════════════════════════════════


@app.route("/api/openapi.json")
def api_openapi_json() -> str:
    from app.api.api_spec import build_openapi_spec
    return jsonify(build_openapi_spec())


@app.route("/api/docs")
def api_docs() -> dict:
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
# Security / Help / Settings pages — content extracted to settings_pages.py
# ════════════════════════════════════════════════════════════════════════════

from app.routes.settings_pages import (
    security_page as _security_page,
    help_page as _help_page,
    settings_page as _settings_page,
)


@app.route("/security")
def security_page() -> str:
    return _security_page(render_page)


@app.route("/help")
@login_required
def help_page() -> str:
    return _help_page(render_page)


# ════════════════════════════════════════════════════════════════════════════
# User Settings page (large inline HTML — stays in web_app)
# ════════════════════════════════════════════════════════════════════════════


@app.route("/settings")
@login_required
@app.route("/settings")
@login_required
def settings_page() -> str:
    """User settings page with Profile, Notifications, Privacy, Appearance, and Reading tabs."""
    return _settings_page(render_page, storage, notif_mgr)

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
