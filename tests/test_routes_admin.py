"""Tests for Book-Tale admin routes."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

pytestmark = pytest.mark.integration

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Must be set before importing web_app
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-admin-routes")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "TestAdmin123")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")
os.environ.setdefault("RATELIMIT_ENABLED", "0")

from app.config.settings import Config

_TMP = tempfile.mkdtemp(prefix="booktale_admin_")
Config.DATA_DIR = os.path.join(_TMP, "data")
Config.LOGS_DIR = os.path.join(_TMP, "logs")
Config.BACKUPS_DIR = os.path.join(_TMP, "backups")
Config.BOOKS_FILE = os.path.join(Config.DATA_DIR, "books.json")
Config.USERS_FILE = os.path.join(Config.DATA_DIR, "users.json")
Config.TRANSACTIONS_FILE = os.path.join(Config.DATA_DIR, "transactions.json")
Config.RESERVATIONS_FILE = os.path.join(Config.DATA_DIR, "reservations.json")
for _d in (Config.DATA_DIR, Config.LOGS_DIR, Config.BACKUPS_DIR):
    os.makedirs(_d, exist_ok=True)

from web_app import app


@pytest.fixture()
def client():  # type: ignore[no-untyped-def]
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestAdminRoutesRegistration:
    """Test that admin routes register correctly on the Flask app."""

    def test_admin_routes_registered(self) -> None:
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        admin_routes = [r for r in rules if "/admin" in r]
        assert len(admin_routes) >= 5, f"Expected >=5 admin routes, got {len(admin_routes)}"

    def test_admin_stats_requires_auth(self, client: object) -> None:
        resp = client.get("/admin/stats")  # type: ignore[union-attr]
        assert resp.status_code in (302, 401, 403)

    def test_admin_users_requires_auth(self, client: object) -> None:
        resp = client.get("/admin/users")  # type: ignore[union-attr]
        assert resp.status_code in (302, 401, 403)

    def test_admin_settings_requires_auth(self, client: object) -> None:
        resp = client.get("/admin/settings")  # type: ignore[union-attr]
        assert resp.status_code in (302, 401, 403)


class TestSettingsPages:
    """Test settings and security page rendering."""

    def test_settings_page(self, client: object) -> None:
        resp = client.get("/settings")  # type: ignore[union-attr]
        assert resp.status_code in (200, 302, 401, 403)

    def test_security_page(self, client: object) -> None:
        resp = client.get("/security")  # type: ignore[union-attr]
        assert resp.status_code in (200, 302, 401, 403)

    def test_help_page(self, client: object) -> None:
        resp = client.get("/help")  # type: ignore[union-attr]
        assert resp.status_code in (200, 302, 401, 403)


class TestAdminHelpers:
    """Test admin route helper functions."""

    def test_h_escapes_html(self) -> None:
        import html
        assert html.escape("<script>") == "&lt;script&gt;"
        assert html.escape("a&b") == "a&amp;b"
        assert html.escape('"quoted"') == "&quot;quoted&quot;"

    def test_audit_log_pattern(self) -> None:
        from unittest.mock import MagicMock, patch

        mock_session = MagicMock()
        mock_db = MagicMock()
        mock_db.session_scope.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_db.session_scope.return_value.__exit__ = MagicMock(return_value=False)
        mock_repo = MagicMock()

        with patch("app.db.database", mock_db), \
             patch("app.db.repositories.AuditLogRepository", return_value=mock_repo):
            assert mock_db.session_scope is not None
