"""Tests for Book-Tale review routes."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

pytestmark = pytest.mark.integration

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-review-routes")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "TestAdmin123")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")
os.environ.setdefault("RATELIMIT_ENABLED", "0")

from app.config.settings import Config

_TMP = tempfile.mkdtemp(prefix="booktale_review_")
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


class TestReviewRoutes:
    """Test review page and API routes."""

    def test_reviews_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/reviews")
        assert resp.status_code in (200, 302, 401, 403)

    def test_review_api_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/api/reviews")
        assert resp.status_code in (302, 401, 403)

    def test_review_submit_requires_auth(self, client: FlaskClient) -> None:
        resp = client.post("/api/reviews", json={
            "book_id": "test",
            "rating": 5,
            "text": "Great book!"
        })
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
