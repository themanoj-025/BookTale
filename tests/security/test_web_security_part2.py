"""test_web_security.py - Web-layer security regression tests (Phase 1 hardening).

Covers:
1. Privilege escalation: self-service registration must never create admin/librarian
2. Fail-fast boot: validate_secure_config() rejects insecure SECRET_KEY values
3. Settings override persistence: config.py settings_override.json actually applies
4. Route-level HTTP 200 smoke tests for the malformed %-format crash sites

NOTE: module-level setup redirects all data paths to a temp dir and sets a test
SECRET_KEY BEFORE importing web_app (whose module-level code runs bootstrap and
fail-fast boot validation). — Part 2."""

import io
import pytest
from app.config.settings import Config
from web_app import storage


def _login(client, uid="ADMIN001", password="TestAdmin123") -> None:
    """Log in as the bootstrap-created admin (cookie persists on client)."""
    resp = client.post("/login", data={"user_id": uid, "password": password})
    assert resp.status_code in (200, 302), f"login failed: {resp.status_code}"
    return resp


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
        except (OSError, ConnectionError, TimeoutError):
            return False

    def test_limiter_storage_uri_uses_redis_by_default(self) -> None:
        """The app-wide limiter must be Redis-backed, not memory://."""
        import web_app

        uri = web_app.limiter._storage_uri
        assert uri == Config.REDIS_URL, f"limiter storage is {uri!r}, expected Redis"
        assert uri.startswith("redis://"), "storage must be Redis by default"

    def test_limiter_storage_uri_override_to_memory(self, monkeypatch) -> None:
        """RATELIMIT_STORAGE_URI=memory:// must force in-process budgets."""
        from web_app import _limiter_storage_uri

        monkeypatch.setenv("RATELIMIT_STORAGE_URI", "memory://")
        assert _limiter_storage_uri() == "memory://"
        monkeypatch.delenv("RATELIMIT_STORAGE_URI", raising=False)
        assert _limiter_storage_uri() == Config.REDIS_URL

    def test_redis_budget_shared_across_limiter_instances(self) -> None:
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

        def _build() -> None:
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
            def limited() -> None:
                return "ok"

            return probe, lim

        app_a, _lim_a = _build()
        app_b, _lim_b = _build()  # independent instance = a second "worker"

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
        except (OSError, ConnectionError, TimeoutError):
            pass

    def test_redis_budget_survives_limiter_recreation(self) -> None:
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

        def _build() -> None:
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
            def limited() -> None:
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
        except (OSError, ConnectionError, TimeoutError):
            pass


class TestAdminAuditLog:
    """Admin audit trail: /admin/audit page + audit rows written by the save
    endpoint (who/what/when/from-where)."""

    def _audit_rows(self, **kwargs) -> None:
        import app.db.database as dbmod
        from app.db.repositories import AuditLogRepository

        with dbmod.session_scope() as db:
            return AuditLogRepository(db).search(**kwargs)

    def test_admin_audit_page_renders_for_admin(self, client) -> None:
        """GET /admin/audit renders 200 for an admin with the search UI."""
        _login(client)
        resp = client.get("/admin/audit")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Audit Log" in body
        assert 'name="q"' in body  # search box present

    def test_admin_audit_page_forbidden_for_non_admin(self, client) -> None:
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

    def test_admin_settings_save_writes_audit_row(self, client) -> None:
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

    def test_admin_settings_failed_verify_writes_audit_row(self, client) -> None:
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

    def test_audit_trail_never_stores_secrets(self, client) -> None:
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

    def test_web_404_renders_error_page(self, client) -> None:
        resp = client.get("/this-page-does-not-exist")
        assert resp.status_code == 404
        assert "Page Not Found" in resp.get_data(as_text=True)

    def test_api_404_returns_json_envelope(self, client) -> None:
        resp = client.get("/api/does-not-exist")
        assert resp.status_code == 404
        body = resp.get_json()
        assert body["data"] is None
        assert body["error"]["code"] == 404
        assert body["error"]["message"]

    def test_api_405_returns_json_envelope(self, client) -> None:
        resp = client.post("/api/search")  # /api/search is GET-only
        assert resp.status_code == 405
        assert resp.get_json()["error"]["code"] == 405

    def test_api_429_returns_json_envelope(self) -> None:
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

    def test_api_409_returns_json_envelope(self) -> None:
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

    def test_500_returns_generic_page_never_internals(self, client, monkeypatch) -> None:
        """An unhandled exception -> 500 page; internal details never leak.

        The failure is injected by monkeypatching a storage call (registering
        a test route is impossible after the app's first request), with
        TESTING off so Flask routes the exception to the 500 handler.
        """
        import web_app

        app = web_app.app

        def _boom(*args, **kwargs) -> None:
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

    def test_openapi_json_is_valid_31(self, client) -> None:
        resp = client.get("/api/openapi.json")
        assert resp.status_code == 200
        spec = resp.get_json()
        assert spec["openapi"].startswith("3.1")
        assert spec["info"]["title"]
        assert spec["paths"]

    def test_api_docs_swagger_ui_renders(self, client) -> None:
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
    def _isolate_uploads(self, tmp_path) -> None:
        from app.config.settings import Config as _C

        original = _C.UPLOADS_DIR
        _C.UPLOADS_DIR = str(tmp_path / "uploads")
        yield
        _C.UPLOADS_DIR = original

    def test_renamed_html_as_png_rejected(self, client) -> None:
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

    def test_real_png_accepted_and_served(self, client) -> None:
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

    def test_search_pickers_escape_title_and_author(self, client) -> None:
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

    def test_bookmarks_list_escapes_note_and_title(self, client) -> None:
        """Reading-progress bookmarks interpolate book_title/note into innerHTML."""
        _login(client)
        resp = client.get("/reading-progress")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "booktaleUtils.escapeHtml(b.book_title)" in html
        assert "booktaleUtils.escapeHtml(b.note)" in html

    def test_diary_selected_message_escapes_title(self, client) -> None:
        """The 'Selected: <title>' echo goes through innerHTML — must escape."""
        _login(client)
        resp = client.get("/diary")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "booktaleUtils.escapeHtml(title)" in html

    def test_base_sidebar_sinks_use_escape_guards(self, client) -> None:
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
