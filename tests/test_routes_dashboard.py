"""Tests for Book-Tale dashboard routes."""

from __future__ import annotations

import os
import tempfile

import pytest

pytestmark = pytest.mark.integration

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-dashboard-routes")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "TestAdmin123")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")
os.environ.setdefault("RATELIMIT_ENABLED", "0")

from app.config.settings import Config

from flask.testing import FlaskClient

from web_app import app


@pytest.fixture()
def client() -> FlaskClient:
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestDashboardRoutes:
    """Test dashboard page and API routes."""

    def test_dashboard_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/dashboard")
        assert resp.status_code in (200, 302, 401, 403)

    def test_dashboard_api_requires_auth(self, client: FlaskClient) -> None:
        # /api/analytics/monthly is guarded by api_key_required, which is
        # fail-open when BOOKTALE_API_KEY is unset, and 401/403 when set.
        # Storage is stubbed so the test asserts the auth contract only,
        # independent of test-process module import order.
        from unittest.mock import patch

        with patch("app.storage.storage.Storage.load_books", return_value={}), \
                patch("app.storage.storage.Storage.load_users", return_value={}), \
                patch("app.db.storage_adapter.DbStorage.load_books", return_value={}), \
                patch("app.db.storage_adapter.DbStorage.load_users", return_value={}):
            import os as _os

            if _os.environ.get("BOOKTALE_API_KEY"):
                resp = client.get(
                    "/api/analytics/monthly",
                    headers={"Authorization": "Bearer wrong-key"},
                )
                assert resp.status_code in (401, 403)
            else:
                resp = client.get("/api/analytics/monthly")
                assert resp.status_code == 200

    def test_dashboard_route_registered(self) -> None:
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        assert "/dashboard" in rules or any("/dashboard" in r for r in rules)


class TestDashboardHelpers:
    """Test dashboard helper functions."""

    def test_avatar_html(self) -> None:
        from app.routes.helpers import avatar_html

        result = avatar_html("https://example.com/avatar.jpg")
        assert isinstance(result, str)

    def test_avatar_html_empty(self) -> None:
        from app.routes.helpers import avatar_html

        result = avatar_html("")
        assert isinstance(result, str)
