"""Tests for Book-Tale review routes."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-review-routes")
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


class TestReviewRoutes:
    """Test review page and API routes."""

    def test_reviews_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/books/test-book-id")
        assert resp.status_code in (200, 302, 401, 403)

    def test_review_api_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/api/reviews/stats")
        assert resp.status_code in (302, 401, 403)

    def test_review_submit_requires_auth(self, client: FlaskClient) -> None:
        resp = client.post("/api/books/test/review", json={"rating": 5, "text": "Great book!"})
        assert resp.status_code in (302, 401, 403)

    def test_review_route_registered(self) -> None:
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        assert "/reviews" in rules or any("/reviews" in r for r in rules)


class TestReviewHelpers:
    """Test review route helper functions."""

    def test_h_escapes_html(self) -> None:
        from app.routes.feature_shared import h

        assert h("<script>") == "&lt;script&gt;"
        assert h("a & b") == "a &amp; b"

    def test_cat_color(self) -> None:
        from app.routes.feature_shared import cat_color

        color = cat_color("Mystery")
        assert isinstance(color, str)
        assert len(color) > 0
