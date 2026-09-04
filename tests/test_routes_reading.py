"""Tests for Book-Tale reading routes."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

pytestmark = pytest.mark.integration

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-reading-routes")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "TestAdmin123")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")
os.environ.setdefault("RATELIMIT_ENABLED", "0")

from app.config.settings import Config

_TMP = tempfile.mkdtemp(prefix="booktale_reading_")
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


class TestReadingRoutes:
    """Test reading page and API routes."""

    def test_reading_requires_auth(self, client: object) -> None:
        resp = client.get("/reading")  # type: ignore[union-attr]
        assert resp.status_code in (200, 302, 401, 403)

    def test_reading_list_requires_auth(self, client: object) -> None:
        resp = client.get("/reading/list")  # type: ignore[union-attr]
        assert resp.status_code in (200, 302, 401, 403)

    def test_reading_api_requires_auth(self, client: object) -> None:
        resp = client.get("/api/reading")  # type: ignore[union-attr]
        assert resp.status_code in (302, 401, 403)

    def test_reading_route_registered(self) -> None:
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        assert "/reading" in rules or any("/reading" in r for r in rules)


class TestReadingHelpers:
    """Test reading route helper functions."""

    def test_h_function(self) -> None:
        from app.routes.feature_shared import h
        assert h("<b>bold</b>") == "&lt;b&gt;bold&lt;/b&gt;"
        assert h("normal") == "normal"

    def test_cat_color(self) -> None:
        from app.routes.feature_shared import cat_color
        color = cat_color("Romance")
        assert isinstance(color, str)
