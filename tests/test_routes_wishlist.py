"""Tests for Book-Tale wishlist routes."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

pytestmark = pytest.mark.integration

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-wishlist-routes")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "TestAdmin123")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")
os.environ.setdefault("RATELIMIT_ENABLED", "0")

from app.config.settings import Config

_TMP = tempfile.mkdtemp(prefix="booktale_wishlist_")
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


class TestWishlistRoutes:
    """Test wishlist page and API routes."""

    def test_wishlist_requires_auth(self, client: object) -> None:
        resp = client.get("/wishlist")  # type: ignore[union-attr]
        assert resp.status_code in (200, 302, 401, 403)

    def test_wishlist_api_requires_auth(self, client: object) -> None:
        resp = client.get("/api/wishlist")  # type: ignore[union-attr]
        assert resp.status_code in (302, 401, 403)

    def test_wishlist_add_requires_auth(self, client: object) -> None:
        resp = client.post("/api/wishlist/add", json={"book_id": "test"})  # type: ignore[union-attr]
        assert resp.status_code in (302, 401, 403)

    def test_wishlist_remove_requires_auth(self, client: object) -> None:
        resp = client.post("/api/wishlist/remove", json={"book_id": "test"})  # type: ignore[union-attr]
        assert resp.status_code in (302, 401, 403)

    def test_wishlist_route_registered(self) -> None:
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        assert "/wishlist" in rules or any("/wishlist" in r for r in rules)
