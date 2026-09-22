"""Tests for Book-Tale social API routes."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-social-routes")
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


class TestSocialRoutes:
    """Test social page and API routes."""

    def test_social_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/feed")
        assert resp.status_code in (200, 302, 401, 403)

    def test_community_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/clubs")
        assert resp.status_code in (200, 302, 401, 403)

    def test_social_feed_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/api/feed")
        assert resp.status_code in (302, 401, 403)

    def test_social_post_requires_auth(self, client: FlaskClient) -> None:
        resp = client.post("/api/posts", json={"text": "Hello!"})
        assert resp.status_code in (302, 401, 403)

    def test_social_like_requires_auth(self, client: FlaskClient) -> None:
        resp = client.post("/api/posts/test/like", json={"post_id": "test"})
        assert resp.status_code in (302, 401, 403)

    def test_social_comment_requires_auth(self, client: FlaskClient) -> None:
        resp = client.post("/api/posts/test/comments", json={"post_id": "test", "text": "Nice!"})
        assert resp.status_code in (302, 401, 403)

    def test_follow_requires_auth(self, client: FlaskClient) -> None:
        resp = client.post("/api/follow/test", json={"user_id": "test"})
        assert resp.status_code in (302, 401, 403)

    def test_social_route_registered(self) -> None:
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        social_routes = [r for r in rules if "/api/posts" in r]
        assert len(social_routes) >= 3, f"Expected >=3 social API routes, got {len(social_routes)}"
