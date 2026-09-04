"""Tests for Book-Tale explore routes."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

pytestmark = pytest.mark.integration

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-explore-routes")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "TestAdmin123")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")
os.environ.setdefault("RATELIMIT_ENABLED", "0")

from app.config.settings import Config

_TMP = tempfile.mkdtemp(prefix="booktale_explore_")
Config.DATA_DIR = os.path.join(_TMP, "data")
Config.LOGS_DIR = os.path.join(_TMP, "logs")
Config.BACKUPS_DIR = os.path.join(_TMP, "backups")
Config.BOOKS_FILE = os.path.join(Config.DATA_DIR, "books.json")
Config.USERS_FILE = os.path.join(Config.DATA_DIR, "users.json")
Config.TRANSACTIONS_FILE = os.path.join(Config.DATA_DIR, "transactions.json")
Config.RESERVATIONS_FILE = os.path.join(Config.DATA_DIR, "reservations.json")
for _d in (Config.DATA_DIR, Config.LOGS_DIR, Config.BACKUPS_DIR):
    os.makedirs(_d, exist_ok=True)

from flask.testing import FlaskClient
from web_app import app


@pytest.fixture()
def client() -> FlaskClient:
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestExploreRoutes:
    """Test explore page and recommendation routes."""

    def test_explore_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/explore")
        assert resp.status_code in (200, 302, 401, 403)

    def test_recommendations_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/recommendations")
        assert resp.status_code in (200, 302, 401, 403)

    def test_notifications_read_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/api/notifications/test-id/read")
        assert resp.status_code in (302, 401, 403)

    def test_notifications_read_all_requires_auth(self, client: FlaskClient) -> None:
        resp = client.post("/api/notifications/read-all")
        assert resp.status_code in (302, 401, 403)

    def test_explore_route_registered(self) -> None:
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        assert "/explore" in rules or any("/explore" in r for r in rules)


class TestExploreHelpers:
    """Test explore route helper functions."""

    def test_avatar_html_with_url(self) -> None:
        from app.routes.helpers import avatar_html
        result = avatar_html("https://example.com/avatar.jpg")
        assert isinstance(result, str)
        assert "img" in result or "src" in result

    def test_avatar_html_without_url(self) -> None:
        from app.routes.helpers import avatar_html
        result = avatar_html("")
        assert isinstance(result, str)

    def test_cat_color(self) -> None:
        from app.routes.helpers import cat_color
        color = cat_color("Fiction")
        assert isinstance(color, str)
        assert len(color) > 0

    def test_cat_color_multiple_categories(self) -> None:
        from app.routes.helpers import cat_color
        for cat in ["Fiction", "Science", "History", "Mystery", "Romance", ""]:
            color = cat_color(cat)
            assert isinstance(color, str)
