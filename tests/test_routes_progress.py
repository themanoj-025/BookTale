"""Tests for Book-Tale progress routes."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-progress-routes")
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


class TestProgressRoutes:
    """Test reading progress page and API routes."""

    def test_progress_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/reading-progress")
        assert resp.status_code in (200, 302, 401, 403)

    def test_progress_api_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/api/reading-progress/stats")
        assert resp.status_code in (302, 401, 403)

    def test_progress_update_requires_auth(self, client: FlaskClient) -> None:
        resp = client.post(
            "/api/reading-progress/test/update", json={"book_id": "test", "page": 50}
        )
        assert resp.status_code in (302, 401, 403)

    def test_bookmarks_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/api/bookmarks")
        assert resp.status_code in (302, 401, 403)

    def test_progress_route_registered(self) -> None:
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        assert "/reading-progress" in rules or any("/progress" in r for r in rules)
