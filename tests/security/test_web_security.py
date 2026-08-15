"""
test_web_security.py - Web-layer security regression tests (Phase 1 hardening).

Covers:
1. Privilege escalation: self-service registration must never create admin/librarian
2. Fail-fast boot: validate_secure_config() rejects insecure SECRET_KEY values
3. Settings override persistence: config.py settings_override.json actually applies
4. Route-level HTTP 200 smoke tests for the malformed %-format crash sites

NOTE: module-level setup redirects all data paths to a temp dir and sets a test
SECRET_KEY BEFORE importing web_app (whose module-level code runs bootstrap and
fail-fast boot validation).
"""

import io
import json
import os
import sys
import tempfile

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

# Must be set before importing web_app (module-level fail-fast boot validation).
os.environ["SECRET_KEY"] = "test-secret-key-for-tests-only"
os.environ["DEFAULT_ADMIN_PASSWORD"] = "TestAdmin123"
# Phase 4: CSRF + rate limiting are ON by default in production. The test
# client has no token plumbing and bursts requests, so the suite explicitly
# opts out (both flags are read at request time / init time — see web_app.py).
os.environ["WTF_CSRF_ENABLED"] = "0"
os.environ["RATELIMIT_ENABLED"] = "0"

import pytest

from app.config.settings import Config

# ── Isolate all data/log/backup paths into a temp dir BEFORE importing web_app,
#    so module-level singletons (storage, bootstrap admin creation) stay sandboxed.
_TMP = tempfile.mkdtemp(prefix="booktale_sec_")
Config.DATA_DIR = os.path.join(_TMP, "data")
Config.LOGS_DIR = os.path.join(_TMP, "logs")
Config.BACKUPS_DIR = os.path.join(_TMP, "backups")
Config.BOOKS_FILE = os.path.join(Config.DATA_DIR, "books.json")
Config.USERS_FILE = os.path.join(Config.DATA_DIR, "users.json")
Config.TRANSACTIONS_FILE = os.path.join(Config.DATA_DIR, "transactions.json")
Config.RESERVATIONS_FILE = os.path.join(Config.DATA_DIR, "reservations.json")
Config.FINES_FILE = os.path.join(Config.DATA_DIR, "fines.json")
Config.NOTIFICATIONS_FILE = os.path.join(Config.DATA_DIR, "notifications.json")
Config.LOG_FILE = os.path.join(Config.LOGS_DIR, "activity.log")
Config.JSON_LOG = os.path.join(Config.LOGS_DIR, "activity.json")
for _d in (Config.DATA_DIR, Config.LOGS_DIR, Config.BACKUPS_DIR):
    os.makedirs(_d, exist_ok=True)

from web_app import app, storage


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _login(client, uid="ADMIN001", password="TestAdmin123"):
    """Log in as the bootstrap-created admin (cookie persists on client)."""
    resp = client.post("/login", data={"user_id": uid, "password": password})
    assert resp.status_code in (200, 302), f"login failed: {resp.status_code}"
    return resp


class TestPrivilegeEscalation:
    def test_register_accepts_only_user_role(self, client):
        """POST /register with role=admin must be silently downgraded to user."""
        resp = client.post(
            "/register",
            data={
                "user_id": "MEM-9001",
                "name": "Escalation Probe",
                "password": "secret123456",
                "confirm_password": "secret123456",
                "role": "admin",
            },
        )
        assert resp.status_code == 200
        users = storage.load_users()
        assert "MEM-9001" in users
        assert (
            users["MEM-9001"].role == "user"
        ), "self-registration must never create an admin account"

    def test_register_with_librarian_role_downgraded(self, client):
        """role=librarian from a public form must also be downgraded."""
        client.post(
            "/register",
            data={
                "user_id": "MEM-9002",
                "name": "Librarian Probe",
                "password": "secret123456",
                "confirm_password": "secret123456",
                "role": "librarian",
            },
        )
        users = storage.load_users()
        assert "MEM-9002" in users
        assert users["MEM-9002"].role == "user"

    def test_register_duplicate_still_rejected(self, client):
        """Downgrade must not break existing duplicate-ID handling."""
        data = {
            "user_id": "MEM-9003",
            "name": "Dup Probe",
            "password": "secret123456",
            "confirm_password": "secret123456",
        }
        client.post("/register", data=data)
        resp = client.post("/register", data=data)
        assert resp.status_code == 200
        users = storage.load_users()
        assert users["MEM-9003"].role == "user"


class TestPasswordPolicy:
    """Phase 4 P1: passwords <12 chars are rejected server-side.

    The old minimum was 6 chars, only enforced in the UI (minlength). The
    policy is now >=12 chars, enforced server-side on every password surface:
    registration, password reset, and the settings password change.
    """

    def test_register_rejects_short_password(self, client):
        """A 9-char password must be rejected and the user never created."""
        resp = client.post(
            "/register",
            data={
                "user_id": "MEM-SHORT1",
                "name": "Short Password",
                "password": "secret123",
                "confirm_password": "secret123",
            },
        )
        assert resp.status_code == 200
        assert "at least 12 characters" in resp.get_data(as_text=True)
        assert "MEM-SHORT1" not in storage.load_users()

    def test_register_accepts_12_char_password(self, client):
        """A 12-char password registers normally."""
        resp = client.post(
            "/register",
            data={
                "user_id": "MEM-LONG1",
                "name": "Long Password",
                "password": "secret123456",
                "confirm_password": "secret123456",
            },
        )
        assert resp.status_code == 200
        assert "MEM-LONG1" in storage.load_users()

    def test_settings_password_change_rejects_short(self, client):
        """Changing your password to <12 chars via /api/settings/save fails."""
        _login(client)
        resp = client.post(
            "/api/settings/save",
            json={"current_password": "TestAdmin123", "new_password": "short1"},
        )
        body = resp.get_json()
        assert body["success"] is False
        assert "12 characters" in body.get("error", "")

    def test_settings_password_change_accepts_long(self, client):
        """A 12+ char password change via settings succeeds."""
        users = storage.load_users()
        original_hash = users["ADMIN001"].password_hash
        try:
            _login(client)
            resp = client.post(
                "/api/settings/save",
                json={
                    "current_password": "TestAdmin123",
                    "new_password": "secret123456",
                },
            )
            assert resp.get_json()["success"] is True
            from app.services.auth.auth import verify_password as _vp

            assert _vp("secret123456", storage.load_users()["ADMIN001"].password_hash)
        finally:
            users = storage.load_users()
            users["ADMIN001"].password_hash = original_hash
            storage.save_users(users)


class TestBootSecurity:
    def test_validate_secure_config_rejects_default_key(self):
        from app.config.settings import validate_secure_config

        original = Config.SECRET_KEY
        try:
            Config.SECRET_KEY = "change-this-secret-key-in-production"
            with pytest.raises(RuntimeError):
                validate_secure_config()
        finally:
            Config.SECRET_KEY = original

    def test_validate_secure_config_rejects_empty_key(self):
        from app.config.settings import validate_secure_config

        original = Config.SECRET_KEY
        try:
            Config.SECRET_KEY = ""
            with pytest.raises(RuntimeError):
                validate_secure_config()
        finally:
            Config.SECRET_KEY = original

    def test_validate_secure_config_accepts_strong_key(self):
        from app.config.settings import validate_secure_config

        original = Config.SECRET_KEY
        try:
            Config.SECRET_KEY = "a-strong-random-secret-32+chars-0123456789abcdef"
            validate_secure_config()  # must not raise
        finally:
            Config.SECRET_KEY = original


class TestSettingsOverride:
    def test_settings_override_applied_after_write(self):
        """Regression: settings_override.json must actually change Config values."""
        from app.config.settings import _load_settings_overrides

        original = Config.FINE_PER_DAY
        override_path = os.path.join(Config.DATA_DIR, "settings_override.json")
        try:
            with open(override_path, "w", encoding="utf-8") as f:
                json.dump({"FINE_PER_DAY": 12.5}, f)
            _load_settings_overrides()
            assert (
                Config.FINE_PER_DAY == 12.5
            ), "settings_override.json values must be applied (was NameError dead code)"
        finally:
            if os.path.exists(override_path):
                os.remove(override_path)
            Config.FINE_PER_DAY = original


class TestCrashSiteRoutes:
    """HTTP 200 regression tests for the malformed %-format crash sites."""

    @pytest.fixture(autouse=True)
    def logged_in_admin_with_book(self, client):
        import uuid

        _login(client)
        from web_app import lib

        # Unique numeric ISBN per test run so re-running the fixture never
        # hits the duplicate-ISBN guard (would fail `assert ok` and error
        # the test). Kept purely numeric in case ISBN validation is added.
        isbn = "978" + str(uuid.uuid4().int)[:10]
        ok, bid = lib.add_book("Regression Book", "Frank Herbert", isbn, "Fiction", 2, actor="test")
        assert ok
        # Give the admin a favorite so the profile page exercises the
        # _render_fav_grid favorites path (regression: social_routes.py:151
        # operator-precedence bug only triggers when favorites exist).
        users = storage.load_users()
        users["ADMIN001"].favorite_books.append(bid)
        storage.save_users(users)
        yield

    def test_reading_calendar_renders(self, client):
        resp = client.get("/reading-calendar")
        assert resp.status_code == 200

    def test_analytics_renders(self, client):
        resp = client.get("/analytics")
        assert resp.status_code == 200

    def test_admin_users_renders(self, client):
        resp = client.get("/admin/users")
        assert resp.status_code == 200

    def test_books_renders(self, client):
        """Exercises the nested BOOKS_GRID %-format path with a real book card."""
        resp = client.get("/books")
        assert resp.status_code == 200

    def test_book_detail_renders(self, client):
        """Regression: /books/<bid> renders the Jinja book_detail template.

        Converting book_detail_page from a hand-built CONTENT string to
        render_template omitted base.html's context contract
        (title/session/notif_count), raising jinja2 UndefinedError
        ('notif_count') -> 500. pytest missed it because no test hit this
        route; the smoke checklist caught it. Asserting 200 + real content
        closes the gap permanently.
        """
        books = storage.load_books()
        bids = [bid for bid, b in books.items() if getattr(b, "title", "") == "Regression Book"]
        assert bids, "fixture should have seeded a Regression Book"
        resp = client.get(f"/books/{bids[0]}")
        body = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "Regression Book" in body
        # Regression: the author link must encode spaces as %20 (path-safe),
        # not '+' (urlencode/quote_plus is query-string semantics and would
        # look up 'Frank+Herbert' -> empty author page for multi-word authors).
        assert "/author/Frank%20Herbert" in body

    def test_reports_renders(self, client):
        """Regression: /reports renders the Jinja reports template.

        Same root cause as test_book_detail_renders (dropped notif_count
        during the render_template conversion) -> 500. Admin-gated, so it
        relies on the fixture's admin login.
        """
        resp = client.get("/reports")
        assert resp.status_code == 200
        assert "Library Health" in resp.get_data(as_text=True)

    def test_profile_renders(self, client):
        resp = client.get("/profile/ADMIN001")
        assert resp.status_code == 200

    def test_welcome_renders(self, client):
        """Regression: /welcome renders its reviews-count stat without NameError.

        The reviews_data definition lives in welcome_page (where it's rendered)
        — the pyflakes cleanup initially misplaced it into features_page, which
        would have 500'd this route at runtime.
        """
        resp = client.get("/welcome")
        assert resp.status_code == 200

    def test_features_renders(self, client):
        """Features page renders without the now-removed unused reviews_data."""
        resp = client.get("/features")
        assert resp.status_code == 200


class TestPhase3JinjaPages:
    """Phase 3: converted pages render via real Jinja2 templates (autoescape ON).

    Regression guards:
    - Every converted route returns HTTP 200 (a template typo 500s immediately).
    - User-supplied data (name/email) is autoescaped on the registered page —
      the old string-concat path was a stored-XSS sink.
    - The asset() helper resolves content-hashed build URLs with a safe fallback.
    """

    def test_login_page_renders(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Welcome Back" in body
        assert 'name="password"' in body
        # No leftover raw string-templating markers.
        assert "auth_content" not in body

    def test_register_page_renders(self, client):
        resp = client.get("/register")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Create Your Account" in body
        assert 'name="role"' in body

    def test_forgot_password_page_renders(self, client):
        resp = client.get("/forgot-password")
        assert resp.status_code == 200
        assert "Forgot Password?" in resp.get_data(as_text=True)

    def test_forgot_password_post_anti_enumeration(self, client):
        """POST /forgot-password always shows the generic success screen."""
        resp = client.post("/forgot-password", data={"identity": "nobody@example.com"})
        assert resp.status_code == 200
        assert "Check Your Email" in resp.get_data(as_text=True)

    def test_registered_page_escapes_name(self, client):
        """XSS round-trip: a <script> payload in the display name must render escaped.

        The pre-Phase-3 code concatenated name/email raw into HTML ('<h2>Welcome, '
        + name + '</h2>') — a stored-XSS sink. With Jinja autoescape the payload
        must appear HTML-entity-escaped and never as a live <script> tag.
        """
        payload = "<script>alert(1)</script>"
        resp = client.post(
            "/register",
            data={
                "user_id": "MEM-9101",
                "name": payload,
                "password": "secret123456",
                "confirm_password": "secret123456",
            },
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        # Autoescaped: angle brackets are entities, so no live script tag.
        assert "&lt;script&gt;" in body
        assert "<script>alert(1)</script>" not in body
        # The stored value is the raw payload (escaping happens at render time,
        # never at write time — defense in depth keeps the data intact).
        users = storage.load_users()
        assert users["MEM-9101"].name == payload

    def test_registered_page_escapes_email(self, client):
        """Email rendered on the registered page is autoescaped too."""
        payload = 'x@y.com" onmouseover="alert(1)'
        resp = client.post(
            "/register",
            data={
                "user_id": "MEM-9102",
                "name": "Email Probe",
                "email": payload,
                "password": "secret123456",
                "confirm_password": "secret123456",
            },
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        # The quote in the payload gets entity-escaped inside the <strong> tag
        # (Jinja/markupsafe escapes " as &#34;), so the onmouseover attribute
        # can never become live HTML.
        assert "&#34; onmouseover=&#34;" in body
        assert 'onmouseover="alert(1)' not in body

    def test_landing_page_renders_for_guests(self, client):
        """GET / and /landing render the Jinja landing template for guests."""
        for path in ("/", "/landing"):
            resp = client.get(path)
            assert resp.status_code == 200, f"{path} returned {resp.status_code}"
            assert "Get Started Free" in resp.get_data(as_text=True)

    def test_landing_page_redirects_logged_in(self, client):
        """A logged-in user is sent to the feed, not the landing page."""
        _login(client)
        resp = client.get("/landing")
        assert resp.status_code == 302
        assert "/feed" in resp.headers.get("Location", "")

    def test_features_and_welcome_render_new_templates(self, client):
        """Converted marketing pages render (and contain template markers)."""
        resp = client.get("/features")
        assert resp.status_code == 200
        assert "One Platform" in resp.get_data(as_text=True)
        resp = client.get("/welcome")
        assert resp.status_code == 200
        assert "Welcome to BookSocial" in resp.get_data(as_text=True)

    def test_asset_helper_resolves_manifest(self):
        """asset() maps logical paths to content-hashed URLs when built."""
        from web_app import asset

        url = asset("js/utils.js")
        # Either a hashed build output (manifest exists) or the safe fallback.
        assert url.startswith("/static/")
        if url.startswith("/static/dist/"):
            assert ".min.js" in url

    def test_asset_helper_fallback_on_missing_manifest(self, monkeypatch):
        """asset() falls back to /static/<path> when the manifest is absent."""
        from web_app import asset

        original = asset._manifest
        try:
            asset._manifest = {}  # simulate "build not run"
            assert asset("js/utils.js") == "/static/js/utils.js"
            assert asset("css/booktale.css") == "/static/css/booktale.css"
        finally:
            asset._manifest = original


class TestXssServerSide:
    """Phase 3: server-rendered pages (Jinja autoescape) keep payloads inert."""

    PAYLOAD = "<script>alert(1)</script>"
    PAYLOAD_ATTR = '"><img src=x onerror=alert(1)>'

    def _seed_book_with_payload(self):
        from app.models.book import Book

        books = storage.load_books()
        books["BK-XSS1"] = Book(
            book_id="BK-XSS1",
            title=self.PAYLOAD,
            author=self.PAYLOAD_ATTR,
            isbn="XSS-0001",
            category='"><svg onload=alert(1)>',
            total_copies=1,
            available_copies=1,
        )
        storage.save_books(books)

    def test_books_page_escapes_payload_title_and_author(self, client):
        """Books page is now a Jinja template (autoescape ON): raw payload must
        never appear; escaped forms must."""
        resp = client.post(
            "/register",
            data={
                "user_id": "MEM-XSS1",
                "name": "XSS Probe",
                "password": "secret123456",
                "confirm_password": "secret123456",
            },
        )
        assert resp.status_code == 200
        _login(client, uid="MEM-XSS1", password="secret123456")
        self._seed_book_with_payload()
        resp = client.get("/books")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
        # Attribute-breakout payload must not survive as raw markup.
        assert "<img src=x onerror=alert(1)>" not in html
        assert "&gt;&lt;img" in html

    def test_books_search_value_is_escaped(self, client):
        """q echoes into the form input value — attribute-escaped by Jinja."""
        resp = client.post(
            "/register",
            data={
                "user_id": "MEM-XSS2",
                "name": "XSS Probe 2",
                "password": "secret123456",
                "confirm_password": "secret123456",
            },
        )
        assert resp.status_code == 200
        _login(client, uid="MEM-XSS2", password="secret123456")
        resp = client.get("/books?q=<script>alert(1)</script>")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html
        assert 'value="&lt;script&gt;alert(1)&lt;/script&gt;"' in html

    def test_notifications_template_renders(self, client):
        """Converted Jinja notifications page renders 200 (template exercised)."""
        _login(client)
        resp = client.get("/notifications")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Notifications" in body


class TestCSRFProtection:
    """Phase 4: CSRF is enabled by default; tokenless state-changing POSTs 400."""

    def test_post_without_csrf_token_rejected(self, client):
        """When CSRF is ON, a POST without a valid token is rejected (400)."""
        app.config["WTF_CSRF_ENABLED"] = True  # suite opted out; force it on
        try:
            resp = client.post("/login", data={"user_id": "ADMIN001", "password": "TestAdmin123"})
            assert (
                resp.status_code == 400
            ), "tokenless state-changing POST must be rejected when CSRF is on"
        finally:
            app.config["WTF_CSRF_ENABLED"] = False

    def test_post_with_csrf_token_accepted(self, client):
        """The same POST succeeds once a session-bound token is included."""
        import re

        app.config["WTF_CSRF_ENABLED"] = True
        try:
            page = client.get("/login")
            assert page.status_code == 200
            m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.get_data(as_text=True))
            assert m, "login form must render a csrf_token hidden input"
            resp = client.post(
                "/login",
                data={
                    "user_id": "ADMIN001",
                    "password": "TestAdmin123",
                    "csrf_token": m.group(1),
                },
            )
            assert resp.status_code in (200, 302)
        finally:
            app.config["WTF_CSRF_ENABLED"] = False

    def test_csrf_flag_defaults_enabled(self):
        """Secure-by-default: booting without WTF_CSRF_ENABLED keeps CSRF ON."""
        import subprocess

        code = (
            "import os, sys, tempfile\n"
            "os.environ['SECRET_KEY'] = 'test-secret-key-for-tests-only'\n"
            "os.environ['DEFAULT_ADMIN_PASSWORD'] = 'TestAdmin123'\n"
            "os.environ.pop('WTF_CSRF_ENABLED', None)\n"
            "os.environ.pop('RATELIMIT_ENABLED', None)\n"
            "tmp = tempfile.mkdtemp(prefix='booktale_csrf_')\n"
            "from app.config.settings import Config\n"
            "for _k in ('DATA_DIR','LOGS_DIR','BACKUPS_DIR'):\n"
            "    setattr(Config, _k, os.path.join(tmp, _k.lower()))\n"
            "for _d in (Config.DATA_DIR, Config.LOGS_DIR, Config.BACKUPS_DIR):\n"
            "    os.makedirs(_d, exist_ok=True)\n"
            "import web_app\n"
            "print('ENABLED' if web_app.app.config['WTF_CSRF_ENABLED'] else 'DISABLED')\n"
        )
        # encoding='utf-8', errors='replace': on Windows the child writes
        # UTF-8 (web_app reconfigures stdout); cp1252 decoding would crash the
        # reader thread with UnicodeDecodeError.
        r = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd=PROJECT_ROOT,
            timeout=120,
        )
        assert "ENABLED" in (
            r.stdout or ""
        ), f"CSRF defaulted OFF! stdout={r.stdout!r} stderr={r.stderr!r}"


class TestReadyz:
    """Phase 7: /readyz must not leak internal error details to clients."""

    def test_readyz_hides_internal_error_details(self, client, monkeypatch):
        """DB failure -> 503 with a generic message, never str(e) internals."""
        import app.db.database as dbmod

        def _boom():
            raise RuntimeError(
                "psycopg2.OperationalError: connection to server at "
                "db.internal:5432 failed: FATAL: password authentication failed"
            )

        monkeypatch.setattr(dbmod, "get_session_factory", _boom)
        resp = client.get("/readyz")
        assert resp.status_code == 503
        body = resp.get_data(as_text=True)
        assert "database unreachable" in body
        # Internal details must never reach the client.
        assert "psycopg2" not in body
        assert "db.internal" not in body
        assert "OperationalError" not in body


class TestRateLimiting:
    """Phase 4: auth endpoints carry per-IP rate limits; limit breach -> 429."""

    def test_auth_routes_have_rate_limit_decorator(self):
        """login/register/forgot/reset must be decorated with @limiter.limit."""
        from web_app import (
            forgot_password_page,
            login_page,
            register_page,
            reset_password_page,
        )

        for view in (
            login_page,
            register_page,
            forgot_password_page,
            reset_password_page,
        ):
            assert hasattr(
                view, "__wrapper-limiter-instance"
            ), f"{view.__name__} is missing a rate-limit decorator"

    def test_rate_limit_returns_429_after_breach(self):
        """The wired limiter returns 429 once a per-route limit is exceeded."""
        from flask import Flask
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address

        probe = Flask(__name__)
        probe.config["RATELIMIT_ENABLED"] = True
        lim = Limiter(key_func=get_remote_address, storage_uri="memory://")
        lim.init_app(probe)

        @probe.route("/login", methods=["POST"])
        @lim.limit("3 per minute")
        def login():
            return "ok"

        with probe.test_client() as c:
            for _ in range(3):
                assert c.post("/login").status_code == 200
            assert c.post("/login").status_code == 429

    # ── Split login limit: only failed credential attempts count ──────────
    # Regression: GET page loads and successful logins must never consume the
    # per-IP budget, so refreshing /login or typing the right password can't
    # lock a user out. Mirrors the real login_page decorator config
    # (methods=["POST"], exempt_when on GET, deduct_when on g._login_failed).

    def _make_split_login_probe(self):
        from flask import Flask, g, request
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address

        probe = Flask(__name__)
        probe.config["RATELIMIT_ENABLED"] = True
        lim = Limiter(key_func=get_remote_address, storage_uri="memory://")
        lim.init_app(probe)

        @probe.route("/login", methods=["GET", "POST"])
        @lim.limit(
            "3 per minute",
            methods=["POST"],
            exempt_when=lambda: request.method == "GET",
            deduct_when=lambda response: getattr(g, "_login_failed", False),
        )
        def login():
            if request.method == "GET":
                return "page", 200
            if request.form.get("pw") == "ok":
                return "ok", 200
            g._login_failed = True
            return "bad", 401

        return probe

    def test_login_get_page_loads_never_rate_limited(self):
        """GET /login page loads must not count toward the POST-only budget."""
        probe = self._make_split_login_probe()
        with probe.test_client() as c:
            for _ in range(25):
                assert c.get("/login").status_code == 200
            # Budget untouched: a failed POST is still allowed.
            assert c.post("/login", data={"pw": "wrong"}).status_code == 401

    def test_login_successful_attempts_do_not_count(self):
        """Successful logins must not consume the per-IP failure budget."""
        probe = self._make_split_login_probe()
        with probe.test_client() as c:
            for _ in range(6):  # 3x the limit — successes must never 429
                assert c.post("/login", data={"pw": "ok"}).status_code == 200
            # Failure budget is still full: 3 failures allowed, 4th is 429.
            for _ in range(3):
                assert c.post("/login", data={"pw": "wrong"}).status_code == 401
            assert c.post("/login", data={"pw": "wrong"}).status_code == 429

    def test_login_only_failed_attempts_breach_limit(self):
        """Failed credential attempts accumulate: 3 allowed, 4th -> 429."""
        probe = self._make_split_login_probe()
        with probe.test_client() as c:
            for _ in range(3):
                assert c.post("/login", data={"pw": "wrong"}).status_code == 401
            assert c.post("/login", data={"pw": "wrong"}).status_code == 429

    # ── /api/settings/save (password-change endpoint) ──────────────────────
    # Defense in depth: an explicit limit exists beyond the global 200/min
    # default, and only FAILED password-change attempts consume the per-IP
    # budget (deduct_when on g._pw_change_failed). Ordinary settings toggles
    # and successful password changes must never throttle the user.

    def test_settings_save_has_explicit_rate_limit(self):
        """api_save_settings must carry a limiter decorator (not just the
        global default)."""
        from web_app import api_save_settings

        assert hasattr(
            api_save_settings, "__wrapper-limiter-instance"
        ), "api_save_settings is missing an explicit rate-limit decorator"

    def _make_settings_save_probe(self):
        from flask import Flask, g, request
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address

        probe = Flask(__name__)
        probe.config["RATELIMIT_ENABLED"] = True
        lim = Limiter(key_func=get_remote_address, storage_uri="memory://")
        lim.init_app(probe)

        @probe.route("/api/settings/save", methods=["POST"])
        @lim.limit(
            "3 per minute",
            deduct_when=lambda response: getattr(g, "_pw_change_failed", False),
        )
        def save_settings():
            data = request.get_json() or {}
            if data.get("new_password"):
                # Mirrors api_save_settings exactly: a wrong current password
                # flags a failed attempt but still returns HTTP 200 with
                # success: False in the body (same as the real endpoint).
                if data.get("current_password") != "ok":
                    g._pw_change_failed = True
                    return {"success": False}
            return {"success": True}

        return probe

    def test_settings_toggles_never_consume_budget(self):
        """Ordinary settings saves (no password change) must not be throttled."""
        probe = self._make_settings_save_probe()
        with probe.test_client() as c:
            for _ in range(15):  # 5x the limit
                resp = c.post("/api/settings/save", json={"email_notifications": True})
                assert resp.status_code == 200
            # Budget untouched: a failed password change is still allowed
            # (HTTP 200 with success: False in the body, per the real endpoint).
            resp = c.post(
                "/api/settings/save",
                json={"new_password": "x", "current_password": "bad"},
            )
            assert resp.status_code == 200
            assert resp.get_json()["success"] is False

    def test_successful_password_change_does_not_count(self):
        """A correct current-password change must not consume the budget."""
        probe = self._make_settings_save_probe()
        with probe.test_client() as c:
            for _ in range(6):  # 2x the limit — successes never 429
                resp = c.post(
                    "/api/settings/save",
                    json={"new_password": "newsecret", "current_password": "ok"},
                )
                assert resp.status_code == 200
                assert resp.get_json()["success"] is True
            # Failure budget still full: 3 failures allowed, 4th is 429.
            for _ in range(3):
                resp = c.post(
                    "/api/settings/save",
                    json={"new_password": "x", "current_password": "bad"},
                )
                assert resp.status_code == 200
                assert resp.get_json()["success"] is False
            resp = c.post(
                "/api/settings/save",
                json={"new_password": "x", "current_password": "bad"},
            )
            assert resp.status_code == 429

    def test_failed_password_changes_breach_limit(self):
        """Failed current-password guesses accumulate: 3 allowed, 4th -> 429."""
        probe = self._make_settings_save_probe()
        with probe.test_client() as c:
            for _ in range(3):
                resp = c.post(
                    "/api/settings/save",
                    json={"new_password": "x", "current_password": "bad"},
                )
                assert resp.status_code == 200
                assert resp.get_json()["success"] is False
            resp = c.post(
                "/api/settings/save",
                json={"new_password": "x", "current_password": "bad"},
            )
            assert resp.status_code == 429

    # ── /api/admin/settings/save (admin password-verified endpoint) ────────
    # Defense in depth: the endpoint verifies the admin's current password
    # (and can rotate it + write SMTP secrets), so a compromised admin session
    # could brute-force current_admin_password. Only FAILED verifications
    # consume the per-IP budget (deduct_when on g._admin_pw_failed);
    # successful saves are never throttled.

    def test_admin_settings_save_has_explicit_rate_limit(self):
        """api_save_admin_settings must carry a limiter decorator."""
        from web_app import api_save_admin_settings

        assert hasattr(
            api_save_admin_settings, "__wrapper-limiter-instance"
        ), "api_save_admin_settings is missing an explicit rate-limit decorator"

    def _make_admin_settings_probe(self):
        from flask import Flask, g, request
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address

        probe = Flask(__name__)
        probe.config["RATELIMIT_ENABLED"] = True
        lim = Limiter(key_func=get_remote_address, storage_uri="memory://")
        lim.init_app(probe)

        @probe.route("/api/admin/settings/save", methods=["POST"])
        @lim.limit(
            "3 per minute",
            deduct_when=lambda response: getattr(g, "_admin_pw_failed", False),
        )
        def save_admin_settings():
            data = request.get_json() or {}
            # Mirrors api_save_admin_settings exactly: a wrong current admin
            # password flags a failed attempt but still returns HTTP 200 with
            # success: False in the body (same as the real endpoint).
            if data.get("current_admin_password") != "ok":
                g._admin_pw_failed = True
                return {"success": False, "error": "Current password is incorrect"}
            return {"success": True}

        return probe

    def test_admin_settings_successful_saves_do_not_count(self):
        """Correct admin-password saves must not consume the budget."""
        probe = self._make_admin_settings_probe()
        with probe.test_client() as c:
            for _ in range(6):  # 2x the limit — successes never 429
                resp = c.post("/api/admin/settings/save", json={"current_admin_password": "ok"})
                assert resp.status_code == 200
                assert resp.get_json()["success"] is True
            # Failure budget still full: 3 failures allowed, 4th is 429.
            for _ in range(3):
                resp = c.post("/api/admin/settings/save", json={"current_admin_password": "bad"})
                assert resp.status_code == 200
                assert resp.get_json()["success"] is False
            resp = c.post("/api/admin/settings/save", json={"current_admin_password": "bad"})
            assert resp.status_code == 429

    def test_admin_settings_failed_verifications_breach_limit(self):
        """Failed admin-password guesses accumulate: 3 allowed, 4th -> 429."""
        probe = self._make_admin_settings_probe()
        with probe.test_client() as c:
            for _ in range(3):
                resp = c.post("/api/admin/settings/save", json={"current_admin_password": "bad"})
                assert resp.status_code == 200
                assert resp.get_json()["success"] is False
            resp = c.post("/api/admin/settings/save", json={"current_admin_password": "bad"})
            assert resp.status_code == 429

    # ── /api/profile/update (email = account-takeover vector) ──────────────
    # Defense in depth: email is a password-reset identity, so changing it is
    # an account-takeover vector. Only requests that actually change the email
    # consume the per-IP budget (deduct_when on g._profile_email_changed);
    # name/bio edits are never throttled.

    def test_profile_update_has_explicit_rate_limit(self):
        """api_profile_update must carry a limiter decorator (via view_functions)."""
        import web_app

        view = web_app.app.view_functions.get("api_profile_update")
        assert view is not None, "api_profile_update not registered"
        assert hasattr(
            view, "__wrapper-limiter-instance"
        ), "api_profile_update is missing an explicit rate-limit decorator"

    def _make_profile_update_probe(self):
        from flask import Flask, g, request
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address

        probe = Flask(__name__)
        probe.config["RATELIMIT_ENABLED"] = True
        lim = Limiter(key_func=get_remote_address, storage_uri="memory://")
        lim.init_app(probe)

        @probe.route("/api/profile/update", methods=["POST"])
        @lim.limit(
            "3 per minute",
            deduct_when=lambda response: getattr(g, "_profile_email_changed", False),
        )
        def profile_update():
            data = request.get_json() or {}
            if "email" in data:
                g._profile_email_changed = True
            return {"success": True}

        return probe

    def test_profile_update_non_email_edits_never_count(self):
        """Name/bio edits must never consume the per-IP budget."""
        probe = self._make_profile_update_probe()
        with probe.test_client() as c:
            for _ in range(15):  # 5x the limit — non-email edits never 429
                resp = c.post("/api/profile/update", json={"name": "New Name"})
                assert resp.status_code == 200
            # Budget untouched: an email change is still allowed.
            resp = c.post("/api/profile/update", json={"email": "a@b.io"})
            assert resp.status_code == 200

    def test_profile_update_email_changes_breach_limit(self):
        """Email changes accumulate: 3 allowed, 4th -> 429."""
        probe = self._make_profile_update_probe()
        with probe.test_client() as c:
            for _ in range(3):
                resp = c.post("/api/profile/update", json={"email": "a@b.io"})
                assert resp.status_code == 200
            resp = c.post("/api/profile/update", json={"email": "a@b.io"})
            assert resp.status_code == 429

    # ── /api/upload + admin destructive ops (plain per-IP limits) ──────────
    # Uploads write files to disk (storage/malware abuse); series delete and
    # wishlist moderate are admin destructive/moderation actions. All carry
    # explicit limits below the global 200/min default.

    def test_upload_has_explicit_rate_limit(self):
        import web_app

        view = web_app.app.view_functions.get("api_upload")
        assert view is not None, "api_upload not registered"
        assert hasattr(
            view, "__wrapper-limiter-instance"
        ), "api_upload is missing an explicit rate-limit decorator"

    def test_series_delete_has_explicit_rate_limit(self):
        import web_app

        view = web_app.app.view_functions.get("api_series_delete")
        assert view is not None, "api_series_delete not registered"
        assert hasattr(
            view, "__wrapper-limiter-instance"
        ), "api_series_delete is missing an explicit rate-limit decorator"

    def test_wishlist_moderate_has_explicit_rate_limit(self):
        import web_app

        view = web_app.app.view_functions.get("api_moderate_suggestion")
        assert view is not None, "api_moderate_suggestion not registered"
        assert hasattr(
            view, "__wrapper-limiter-instance"
        ), "api_moderate_suggestion is missing an explicit rate-limit decorator"

    def test_upload_plain_limit_breaches_429(self):
        """A plain limit on uploads: 3 allowed, 4th -> 429."""
        from flask import Flask
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address

        probe = Flask(__name__)
        probe.config["RATELIMIT_ENABLED"] = True
        lim = Limiter(key_func=get_remote_address, storage_uri="memory://")
        lim.init_app(probe)

        @probe.route("/api/upload", methods=["POST"])
        @lim.limit("3 per minute")
        def upload():
            return {"success": True}

        with probe.test_client() as c:
            for _ in range(3):
                assert c.post("/api/upload").status_code == 200
            assert c.post("/api/upload").status_code == 429

    # ── Per-account keying on password-change endpoints ────────────────────
    # Regression: per-IP limits alone let a distributed attacker (many source
    # IPs) keep brute-forcing a compromised account's password fields. The
    # real /api/settings/save + /api/admin/settings/save decorators pass
    # key_func=_user_key (web_app._user_key -> "user:<user_id>" from the
    # session, IP fallback), so each ACCOUNT gets its own budget regardless of
    # where the requests originate.

    def _make_per_user_pw_probe(self):
        from flask import Flask, g, request, session
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address

        probe = Flask(__name__)
        probe.secret_key = "probe"
        probe.config["RATELIMIT_ENABLED"] = True
        lim = Limiter(key_func=get_remote_address, storage_uri="memory://")
        lim.init_app(probe)

        def user_key():
            uid = session.get("user_id")
            return f"user:{uid}" if uid else f"ip:{request.remote_addr}"

        @probe.route("/api/settings/save", methods=["POST"])
        @lim.limit(
            "3 per minute",
            key_func=user_key,
            deduct_when=lambda response: getattr(g, "_pw_change_failed", False),
        )
        def save_settings():
            data = request.get_json() or {}
            if data.get("current_password") != "ok":
                g._pw_change_failed = True
                return {"success": False}, 200
            return {"success": True}

        return probe

    def test_password_change_budget_is_per_account_not_per_ip(self):
        """User A exhausting its budget must not throttle User B on the same IP."""
        probe = self._make_per_user_pw_probe()
        with probe.test_client() as c:
            with c.session_transaction() as s:
                s["user_id"] = "USER-A"
            # User A burns its budget: 3 failures allowed, 4th is 429.
            for _ in range(3):
                resp = c.post("/api/settings/save", json={"current_password": "bad"})
                assert resp.status_code == 200
                assert resp.get_json()["success"] is False
            assert c.post("/api/settings/save", json={"current_password": "bad"}).status_code == 429
            # User B, SAME IP (same test client), gets a full fresh budget.
            with c.session_transaction() as s:
                s["user_id"] = "USER-B"
            for _ in range(3):
                resp = c.post("/api/settings/save", json={"current_password": "bad"})
                assert resp.status_code == 200
                assert resp.get_json()["success"] is False
            assert c.post("/api/settings/save", json={"current_password": "bad"}).status_code == 429

    def test_password_change_per_user_successes_never_count(self):
        """Successful changes must not consume the per-account budget."""
        probe = self._make_per_user_pw_probe()
        with probe.test_client() as c:
            with c.session_transaction() as s:
                s["user_id"] = "USER-C"
            for _ in range(6):  # 2x the limit — successes never 429
                resp = c.post(
                    "/api/settings/save",
                    json={"current_password": "ok", "new_password": "newsecret"},
                )
                assert resp.status_code == 200
                assert resp.get_json()["success"] is True
            # Failure budget still full: 3 failures allowed, 4th is 429.
            for _ in range(3):
                resp = c.post("/api/settings/save", json={"current_password": "bad"})
                assert resp.status_code == 200
                assert resp.get_json()["success"] is False
            assert c.post("/api/settings/save", json={"current_password": "bad"}).status_code == 429

    def test_user_key_scopes_to_account_inside_request_context(self):
        """_user_key() must embed the session account id (distinct per user).

        Decorator presence on api_save_settings / api_save_admin_settings is
        already asserted by test_settings_save_has_explicit_rate_limit and
        test_admin_settings_save_has_explicit_rate_limit; this test proves the
        shared _user_key() helper itself yields per-account keys. It must run
        inside test_request_context: the module-level flask.session proxy is
        only readable with an active request context.
        """
        from flask import session as fs

        import web_app

        with web_app.app.test_request_context():
            fs["user_id"] = "USER-1"
            k1 = web_app._user_key()
            fs["user_id"] = "USER-2"
            k2 = web_app._user_key()
        assert k1 == "user:USER-1"
        assert k2 == "user:USER-2"
        assert k1 != k2

    # ── Shared-surface content limits (posts/comments/likes/follows/etc.) ──
    # Audit outcome: every POST that writes shared-surface content or moves
    # engagement counters gets an explicit ceiling below the 200/min default.
    # Three tiers: content spam (30/min), engagement manipulation (60/min),
    # create-heavy surfaces like clubs/wishlist suggestions (10/min).

    def test_shared_surface_content_endpoints_have_rate_limits(self):
        """posts/comments/replies/reviews/lists must carry explicit limits."""
        import web_app

        names = [
            "api_create_post",  # 30/min - feed spam
            "api_repost",  # 30/min - amplification
            "api_comments",  # 30/min POST-only - comment spam
            "api_reply_comment",  # 30/min - reply spam
            "api_review_comments",  # 30/min POST-only - review comment spam
            "api_add_review",  # 30/min - review spam
            "api_submit_review",  # 30/min - review spam
            "api_create_list",  # 30/min - public list spam
            "api_create_shelf",  # 30/min - shelf-creation spam
            "api_create_club",  # 10/min - club spam
            "api_suggest_book",  # 10/min - moderation-queue flood
            "api_suggestion_comment",  # 30/min - comment spam
        ]
        for name in names:
            view = web_app.app.view_functions.get(name)
            assert view is not None, f"{name} not registered"
            assert hasattr(
                view, "__wrapper-limiter-instance"
            ), f"{name} is missing an explicit rate-limit decorator"

    def test_engagement_endpoints_have_rate_limits(self):
        """likes/votes/helpful/follows/upvotes: 60/min engagement ceiling."""
        import web_app

        names = [
            "api_like_post",  # 60/min - like-farming
            "api_vote_post",  # 60/min - vote-stuffing
            "api_helpful_review",  # 60/min - helpful-vote manipulation
            "api_follow_user",  # 60/min - mass follow/unfollow churn
            "api_list_follow",  # 60/min - list follow churn
            "api_list_upvote",  # 60/min - upvote-stuffing
            "api_vote_suggestion",  # 60/min - suggestion vote-stuffing
            "api_club_join",  # 60/min - club join/leave churn
        ]
        for name in names:
            view = web_app.app.view_functions.get(name)
            assert view is not None, f"{name} not registered"
            assert hasattr(
                view, "__wrapper-limiter-instance"
            ), f"{name} is missing an explicit rate-limit decorator"

    def test_ai_chat_has_explicit_rate_limit(self):
        """api_ai_chat carries a 30/min ceiling (companion spam / load)."""
        import web_app

        view = web_app.app.view_functions.get("api_ai_chat")
        assert view is not None, "api_ai_chat not registered"
        assert hasattr(
            view, "__wrapper-limiter-instance"
        ), "api_ai_chat is missing an explicit rate-limit decorator"

    def _make_shared_surface_probe(self):
        """Plain-limit probe mirroring the 30/min content endpoints."""
        from flask import Flask
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address

        probe = Flask(__name__)
        probe.config["RATELIMIT_ENABLED"] = True
        lim = Limiter(key_func=get_remote_address, storage_uri="memory://")
        lim.init_app(probe)

        @probe.route("/api/posts", methods=["POST"])
        @lim.limit("3 per minute")
        def create_post():
            return {"success": True}

        return probe

    def test_shared_surface_plain_limit_breaches_429(self):
        """A 30/min-style plain content limit: 3 allowed, 4th -> 429."""
        probe = self._make_shared_surface_probe()
        with probe.test_client() as c:
            for _ in range(3):
                assert c.post("/api/posts").status_code == 200
            assert c.post("/api/posts").status_code == 429

    def _make_comment_get_post_probe(self):
        """GET+POST probe mirroring api_comments (methods=["POST"])."""
        from flask import Flask
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address

        probe = Flask(__name__)
        probe.config["RATELIMIT_ENABLED"] = True
        lim = Limiter(key_func=get_remote_address, storage_uri="memory://")
        lim.init_app(probe)

        @probe.route("/api/posts/<post_id>/comments", methods=["GET", "POST"])
        @lim.limit("3 per minute", methods=["POST"])
        def comments(post_id):
            return "ok", 200

        return probe

    def test_comment_get_loads_never_consume_budget(self):
        """GET fetches on the GET+POST comments route never count toward POST."""
        probe = self._make_comment_get_post_probe()
        with probe.test_client() as c:
            for _ in range(25):  # 8x the limit — GETs must never 429
                assert c.get("/api/posts/P1/comments").status_code == 200
            # Budget untouched: the first 3 POSTs are still allowed.
            for _ in range(3):
                assert c.post("/api/posts/P1/comments").status_code == 200
            assert c.post("/api/posts/P1/comments").status_code == 429

    # ── Auth FORM page loads (register/forgot-password/reset-password) ────
    # Regression found by scripts/smoke_live.py: the three auth form routes
    # used plain @_rate_limit("5 per minute") with no methods=["POST"] or
    # exempt_when, so GET page loads consumed the budget and the 6th page
    # load in a minute returned 429 (a real journey breaker). Fixed to mirror
    # the login route's GET-exempt split. These probes lock the fix in.

    def _make_auth_form_probe(self):
        """GET+POST probe mirroring register/forgot/reset decorator config
        (5/min scoped to POST, GET exempt)."""
        from flask import Flask, request
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address

        probe = Flask(__name__)
        probe.config["RATELIMIT_ENABLED"] = True
        lim = Limiter(key_func=get_remote_address, storage_uri="memory://")
        lim.init_app(probe)

        @probe.route("/auth-form", methods=["GET", "POST"])
        @lim.limit(
            "5 per minute",
            methods=["POST"],
            exempt_when=lambda: request.method == "GET",
        )
        def auth_form():
            return "ok", 200

        return probe

    def test_auth_form_get_page_loads_never_consume_budget(self):
        """GET page loads on register/forgot/reset must never 429 (8x the limit)."""
        probe = self._make_auth_form_probe()
        with probe.test_client() as c:
            for _ in range(40):  # 8x the 5/min limit — GETs must never 429
                assert c.get("/auth-form").status_code == 200
            # Budget untouched: the first 5 POSTs are still allowed.
            for _ in range(5):
                assert c.post("/auth-form").status_code == 200
            assert c.post("/auth-form").status_code == 429

    def test_auth_form_post_budget_breaches_429(self):
        """POST submissions still accumulate: 5 allowed, 6th -> 429."""
        probe = self._make_auth_form_probe()
        with probe.test_client() as c:
            for _ in range(5):
                assert c.post("/auth-form").status_code == 200
            assert c.post("/auth-form").status_code == 429

    def test_auth_form_decorators_scope_to_post(self):
        """The real register/forgot/reset decorators must be POST-scoped with
        GET exempt — otherwise GET page loads burn the anti-spam budget."""
        import inspect

        # Root web_app.py is now a thin re-export wrapper; inspect the real
        # implementation module so the decorator-source assertions still see
        # the actual route definitions.
        from app.routes import web_app as _real_web_app

        src = inspect.getsource(_real_web_app)
        # Each route must carry the split-limit config, not the plain form.
        for marker in [
            "def register_page():",
            "def forgot_password_page():",
            "def reset_password_page():",
        ]:
            # Slice from the preceding @app.route decorator up to the view def
            # (not a fixed char window) so comment growth can never push the
            # limit decorator out of the inspected block.
            idx = src.index(marker)
            start = src.rindex("@app.route", 0, idx)
            block = src[start:idx]
            assert (
                '@_rate_limit("5 per minute", methods=["POST"],' in block
            ), f"{marker} must scope its limit to POST"
            assert (
                'exempt_when=lambda: request.method == "GET"' in block
            ), f"{marker} must exempt GET page loads"


class TestRedisLimiterStorage:
    """Phase 6: rate-limit budgets live in Redis, not process memory.

    Two properties that in-memory storage cannot provide, and the reason for
    the switch: budgets survive process restarts, and multiple gunicorn
    workers share ONE budget. The live tests run against the local Redis
    (Config.REDIS_URL) and skip cleanly when no Redis is reachable.
    """

    @staticmethod
    def _redis_reachable() -> bool:
        try:
            import redis as _redis_client

            _r = _redis_client.Redis.from_url(Config.REDIS_URL, socket_connect_timeout=1.0)
            return bool(_r.ping())
        except Exception:
            return False

    def test_limiter_storage_uri_uses_redis_by_default(self):
        """The app-wide limiter must be Redis-backed, not memory://."""
        import web_app

        uri = web_app.limiter._storage_uri
        assert uri == Config.REDIS_URL, f"limiter storage is {uri!r}, expected Redis"
        assert uri.startswith("redis://"), "storage must be Redis by default"

    def test_limiter_storage_uri_override_to_memory(self, monkeypatch):
        """RATELIMIT_STORAGE_URI=memory:// must force in-process budgets."""
        from web_app import _limiter_storage_uri

        monkeypatch.setenv("RATELIMIT_STORAGE_URI", "memory://")
        assert _limiter_storage_uri() == "memory://"
        monkeypatch.delenv("RATELIMIT_STORAGE_URI", raising=False)
        assert _limiter_storage_uri() == Config.REDIS_URL

    def test_redis_budget_shared_across_limiter_instances(self):
        """Two limiter instances on the same Redis share ONE budget.

        This is the multi-gunicorn-worker property: instance A burning the
        budget must be visible to instance B (same Redis, same key prefix),
        which plain per-process memory storage cannot provide.
        """
        if not self._redis_reachable():
            pytest.skip("Redis not reachable — multi-worker sharing not verified")
        import uuid

        from flask import Flask
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address

        prefix = f"booktale-test-{uuid.uuid4().hex[:8]}"

        def _build():
            probe = Flask(__name__)
            probe.config["RATELIMIT_ENABLED"] = True
            lim = Limiter(
                key_func=get_remote_address,
                storage_uri=Config.REDIS_URL,
                key_prefix=prefix,
            )
            lim.init_app(probe)

            @probe.route("/limited", methods=["POST"])
            @lim.limit("3 per minute")
            def limited():
                return "ok"

            return probe, lim

        app_a, lim_a = _build()
        app_b, lim_b = _build()  # independent instance = a second "worker"

        with app_a.test_client() as c_a, app_b.test_client() as c_b:
            # Worker A burns its budget: 3 allowed, 4th -> 429.
            for _ in range(3):
                assert c_a.post("/limited").status_code == 200
            assert c_a.post("/limited").status_code == 429
            # Worker B, same Redis, sees the SAME exhausted budget.
            assert (
                c_b.post("/limited").status_code == 429
            ), "budget must be shared across limiter instances (multi-worker)"
        # Clean up the unique test keys so later runs start fresh.
        try:
            import redis as _redis_client

            _r = _redis_client.Redis.from_url(Config.REDIS_URL)
            for key in _r.scan_iter(f"limiter/{prefix}/*"):
                _r.delete(key)
        except Exception:
            pass

    def test_redis_budget_survives_limiter_recreation(self):
        """A fresh limiter (simulating a worker restart) inherits the budget.

        In-memory storage resets on restart; Redis must not. Create a limiter,
        burn 3 of 4 requests, then build a brand-new limiter and assert the
        old budget is still enforced (only 1 request left, not 4).
        """
        if not self._redis_reachable():
            pytest.skip("Redis not reachable — restart persistence not verified")
        import uuid

        from flask import Flask
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address

        prefix = f"booktale-restart-{uuid.uuid4().hex[:8]}"

        def _build():
            probe = Flask(__name__)
            probe.config["RATELIMIT_ENABLED"] = True
            lim = Limiter(
                key_func=get_remote_address,
                storage_uri=Config.REDIS_URL,
                key_prefix=prefix,
            )
            lim.init_app(probe)

            @probe.route("/limited", methods=["POST"])
            @lim.limit("4 per minute")
            def limited():
                return "ok"

            return probe

        app_a = _build()
        with app_a.test_client() as c_a:
            for _ in range(3):
                assert c_a.post("/limited").status_code == 200

        # "Restart": a brand-new app + limiter, same Redis, same prefix.
        app_b = _build()
        with app_b.test_client() as c_b:
            assert c_b.post("/limited").status_code == 200  # 4th = last allowed
            assert c_b.post("/limited").status_code == 429  # budget carried over
        try:
            import redis as _redis_client

            _r = _redis_client.Redis.from_url(Config.REDIS_URL)
            for key in _r.scan_iter(f"limiter/{prefix}/*"):
                _r.delete(key)
        except Exception:
            pass


class TestAdminAuditLog:
    """Admin audit trail: /admin/audit page + audit rows written by the save
    endpoint (who/what/when/from-where)."""

    def _audit_rows(self, **kwargs):
        import app.db.database as dbmod
        from app.db.repositories import AuditLogRepository

        with dbmod.session_scope() as db:
            return AuditLogRepository(db).search(**kwargs)

    def test_admin_audit_page_renders_for_admin(self, client):
        """GET /admin/audit renders 200 for an admin with the search UI."""
        _login(client)
        resp = client.get("/admin/audit")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Audit Log" in body
        assert 'name="q"' in body  # search box present

    def test_admin_audit_page_forbidden_for_non_admin(self, client):
        """A regular user is turned away (page_routes' admin_required renders
        the Forbidden page at 200 — same behavior as /admin/users)."""
        client.post(
            "/register",
            data={
                "user_id": "MEM-9201",
                "name": "Audit Probe",
                "password": "secret123456",
                "confirm_password": "secret123456",
            },
        )
        _login(client, uid="MEM-9201", password="secret123456")
        resp = client.get("/admin/audit")
        body = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "Admin Access Required" in body
        # Defense in depth: the audit table markup must never reach a non-admin.
        assert "audit-table" not in body

    def test_admin_settings_save_writes_audit_row(self, client):
        """A successful admin-settings save records an audit row with old/new
        values, the acting admin, and the source IP."""
        _login(client)
        resp = client.post(
            "/api/admin/settings/save",
            json={
                "current_admin_password": "TestAdmin123",
                "fine_per_day": 12.5,
            },
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        rows = self._audit_rows(action="settings.update", query="FINE_PER_DAY")
        assert rows, "save must write an audit row for the changed setting"
        row = rows[0]
        assert row["target"] == "FINE_PER_DAY"
        assert row["admin_id"] == "ADMIN001"
        assert row["new_value"] == "12.5"
        assert row["old_value"] is not None  # previous Config value captured
        assert row["ip_address"]  # from where

    def test_admin_settings_failed_verify_writes_audit_row(self, client):
        """A failed admin-password verification is recorded as auth.failed."""
        _login(client)
        resp = client.post(
            "/api/admin/settings/save",
            json={
                "current_admin_password": "wrong-password",
                "fine_per_day": 1.0,
            },
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is False

        rows = self._audit_rows(action="auth.failed", admin_id="ADMIN001")
        assert rows, "failed verification must write an auth.failed audit row"

    def test_audit_trail_never_stores_secrets(self, client):
        """SMTP/admin passwords are redacted in the audit trail.

        The endpoint rotates ADMIN001's password, which would break later tests
        that log in as ADMIN001/TestAdmin123 — restore the original hash in a
        finally block so this test is side-effect free.
        """
        users = storage.load_users()
        original_hash = users["ADMIN001"].password_hash
        try:
            _login(client)
            resp = client.post(
                "/api/admin/settings/save",
                json={
                    "current_admin_password": "TestAdmin123",
                    "smtp_password": "SuperSecretSmtp99",
                    "new_admin_password": "NewAdminPass99",
                },
            )
            assert resp.status_code == 200
            assert resp.get_json()["success"] is True

            rows = self._audit_rows(query="SuperSecretSmtp99") + self._audit_rows(
                query="NewAdminPass99"
            )
            assert not rows, "raw secret values must never appear in the audit trail"
            smtp = self._audit_rows(action="settings.update", query="SMTP_PASSWORD")
            assert smtp and smtp[0]["new_value"] == "[redacted]"
            pw = self._audit_rows(action="admin.password_change")
            assert pw and pw[0]["new_value"] == "[redacted]"
        finally:
            # Undo the password rotation so later tests can still log in.
            users = storage.load_users()
            users["ADMIN001"].password_hash = original_hash
            storage.save_users(users)


class TestErrorHandlers:
    """Phase 7: centralized error handlers — JSON envelope for API paths, a
    styled error page for browsers, never a raw traceback in production."""

    def test_web_404_renders_error_page(self, client):
        resp = client.get("/this-page-does-not-exist")
        assert resp.status_code == 404
        assert "Page Not Found" in resp.get_data(as_text=True)

    def test_api_404_returns_json_envelope(self, client):
        resp = client.get("/api/does-not-exist")
        assert resp.status_code == 404
        body = resp.get_json()
        assert body["data"] is None
        assert body["error"]["code"] == 404
        assert body["error"]["message"]

    def test_api_405_returns_json_envelope(self, client):
        resp = client.post("/api/search")  # /api/search is GET-only
        assert resp.status_code == 405
        assert resp.get_json()["error"]["code"] == 405

    def test_api_429_returns_json_envelope(self):
        """The centralized handler shapes 429 responses as a JSON envelope.

        Unit-test the shared _error_response helper directly (a real 429 is
        hard to provoke through the suite because RATELIMIT_ENABLED=0); the
        helper is what every status goes through, so the envelope contract is
        what matters here.
        """
        import web_app

        with web_app.app.test_request_context("/api/anything"):
            response = web_app._error_response(429, "too many")
        body = response[0].get_json()
        assert body["data"] is None
        assert body["error"]["code"] == 429
        assert body["error"]["message"]

    def test_api_409_returns_json_envelope(self):
        """The centralized handler shapes 409 responses as a JSON envelope.

        409 is in _ERROR_PAGES (Phase 7 spec list) and the handler loop is
        derived from the dict, so it is registered automatically; this test
        locks in the envelope contract for the code.
        """
        import web_app

        with web_app.app.test_request_context("/api/anything"):
            response = web_app._error_response(409, "conflict")
        body = response[0].get_json()
        assert body["data"] is None
        assert body["error"]["code"] == 409
        assert body["error"]["message"]

    def test_500_returns_generic_page_never_internals(self, client, monkeypatch):
        """An unhandled exception -> 500 page; internal details never leak.

        The failure is injected by monkeypatching a storage call (registering
        a test route is impossible after the app's first request), with
        TESTING off so Flask routes the exception to the 500 handler.
        """
        import web_app

        app = web_app.app

        def _boom(*args, **kwargs):
            raise RuntimeError("secret-internal-detail")

        _login(client)
        monkeypatch.setattr(web_app.storage, "load_books", _boom)
        app.config["TESTING"] = False
        app.config["PROPAGATE_EXCEPTIONS"] = False
        try:
            resp = client.get("/books")
            assert resp.status_code == 500
            body = resp.get_data(as_text=True)
            assert "Server Error" in body
            assert "secret-internal-detail" not in body
        finally:
            app.config["TESTING"] = True
            app.config.pop("PROPAGATE_EXCEPTIONS", None)


class TestApiDocs:
    """Phase 5: a real generated OpenAPI 3.1 spec at /api/openapi.json served
    by Swagger UI at /api/docs — making the README's docs claim true."""

    def test_openapi_json_is_valid_31(self, client):
        resp = client.get("/api/openapi.json")
        assert resp.status_code == 200
        spec = resp.get_json()
        assert spec["openapi"].startswith("3.1")
        assert spec["info"]["title"]
        assert spec["paths"]

    def test_api_docs_swagger_ui_renders(self, client):
        resp = client.get("/api/docs")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "swagger-ui" in body
        assert "/api/openapi.json" in body


class TestUploadValidation:
    """Phase 4 P1: uploads must pass magic-byte verification, not just the
    extension check — a file renamed from HTML/JS to .png is rejected, and a
    genuine image is re-encoded and served back."""

    @pytest.fixture(autouse=True)
    def _isolate_uploads(self, tmp_path):
        from app.config.settings import Config as _C

        original = _C.UPLOADS_DIR
        _C.UPLOADS_DIR = str(tmp_path / "uploads")
        yield
        _C.UPLOADS_DIR = original

    def test_renamed_html_as_png_rejected(self, client):
        """An HTML file renamed to .png must be rejected by content check."""
        _login(client)
        payload = b"<html><script>alert(1)</script></html>"
        resp = client.post(
            "/api/upload",
            data={"file": (io.BytesIO(payload), "evil.png"), "type": "avatar"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200  # endpoint answers 200 + success:False
        body = resp.get_json()
        assert body["success"] is False
        assert "valid image" in body.get("error", "")

    def test_real_png_accepted_and_served(self, client):
        """A genuine 1x1 PNG uploads (re-encoded) and is served back."""
        _login(client)
        import base64

        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
            "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        resp = client.post(
            "/api/upload",
            data={"file": (io.BytesIO(png), "pixel.png"), "type": "avatar"},
            content_type="multipart/form-data",
        )
        body = resp.get_json()
        assert resp.status_code == 200
        assert body["success"] is True, body
        served = client.get(body["url"])
        assert served.status_code == 200


class TestXssClientSideSinks:
    """Phase 3: every client-side innerHTML sink calls the escape guards."""

    def test_search_pickers_escape_title_and_author(self, client):
        """Diary + progress book pickers route display through escapeHtml and
        onclick args through jsStr (JS-string-inside-HTML-attribute escaper)."""
        resp = client.post(
            "/register",
            data={
                "user_id": "MEM-XSS3",
                "name": "XSS Probe 3",
                "password": "secret123456",
                "confirm_password": "secret123456",
            },
        )
        assert resp.status_code == 200
        _login(client, uid="MEM-XSS3", password="secret123456")
        for path in ("/diary", "/reading-progress"):
            resp = client.get(path)
            assert resp.status_code == 200, f"{path} did not render"
            html = resp.get_data(as_text=True)
            assert "booktaleUtils.escapeHtml(b.title)" in html, f"{path}: title display not escaped"
            assert (
                "booktaleUtils.escapeHtml(b.author)" in html
            ), f"{path}: author display not escaped"
            assert (
                "booktaleUtils.jsStr(b.title)" in html
            ), f"{path}: onclick title not jsStr-escaped"
            assert (
                "booktaleUtils.jsStr(b.book_id)" in html
            ), f"{path}: onclick book_id not jsStr-escaped"

    def test_bookmarks_list_escapes_note_and_title(self, client):
        """Reading-progress bookmarks interpolate book_title/note into innerHTML."""
        _login(client)
        resp = client.get("/reading-progress")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "booktaleUtils.escapeHtml(b.book_title)" in html
        assert "booktaleUtils.escapeHtml(b.note)" in html

    def test_diary_selected_message_escapes_title(self, client):
        """The 'Selected: <title>' echo goes through innerHTML — must escape."""
        _login(client)
        resp = client.get("/diary")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "booktaleUtils.escapeHtml(title)" in html

    def test_base_sidebar_sinks_use_escape_guards(self, client):
        """Trending sidebar (book titles) and who-to-follow (usernames) fetch via
        /api and interpolate into innerHTML — both must escape."""
        _login(client)
        resp = client.get("/profile/ADMIN001")
        assert resp.status_code in (200, 302)
        html = resp.get_data(as_text=True) if resp.status_code == 200 else ""
        if html:
            assert "booktaleUtils.escapeHtml(l)" in html
            assert "booktaleUtils.escapeHtml(u)" in html
            assert "booktaleUtils.jsStr(u)" in html
