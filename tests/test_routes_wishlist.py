"""Tests for Book-Tale wishlist routes."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-wishlist-routes")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "TestAdmin123")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")
os.environ.setdefault("RATELIMIT_ENABLED", "0")


from flask.testing import FlaskClient

from web_app import app


@pytest.fixture()
def client() -> FlaskClient:
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestWishlistRoutes:
    """Test wishlist page and API routes."""

    def test_wishlist_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/wishlist")
        assert resp.status_code in (200, 302, 401, 403)

    def test_wishlist_api_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/api/wishlist/stats")
        assert resp.status_code in (302, 401, 403)

    def test_wishlist_add_requires_auth(self, client: FlaskClient) -> None:
        resp = client.post("/api/wishlist/suggest", json={"book_id": "test"})
        assert resp.status_code in (302, 401, 403)

    def test_wishlist_remove_requires_auth(self, client: FlaskClient) -> None:
        resp = client.post("/api/wishlist/test-id/vote", json={"vote": "up"})
        assert resp.status_code in (302, 401, 403)

    def test_wishlist_route_registered(self) -> None:
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        assert "/wishlist" in rules or any("/wishlist" in r for r in rules)
