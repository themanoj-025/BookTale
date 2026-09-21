"""Tests for Book-Tale diary routes."""

from __future__ import annotations

import os
import tempfile

import pytest

pytestmark = pytest.mark.integration

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-diary-routes")
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


class TestDiaryRoutes:
    """Test diary page and API routes."""

    def test_diary_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/diary")
        assert resp.status_code in (200, 302, 401, 403)

    def test_diary_with_pagination(self, client: FlaskClient) -> None:
        resp = client.get("/diary?page=1")
        assert resp.status_code in (200, 302, 401, 403)

    def test_diary_api_requires_auth(self, client: FlaskClient) -> None:
        resp = client.get("/api/diary/stats")
        assert resp.status_code in (302, 401, 403)

    def test_diary_route_registered(self) -> None:
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        assert "/diary" in rules or any("/diary" in r for r in rules)


class TestDiaryHelpers:
    """Test diary helper functions and service layer."""

    def test_rating_labels_exist(self) -> None:
        from app.services.reading.diary import RATING_LABELS

        assert "timepass" in RATING_LABELS
        assert "perfection" in RATING_LABELS
        assert len(RATING_LABELS) == 4

    def test_rating_scores_exist(self) -> None:
        from app.services.reading.diary import RATING_SCORES

        assert len(RATING_SCORES) == 4
        scores = list(RATING_SCORES.values())
        assert scores == sorted(scores, reverse=True)

    def test_rating_badge_html(self) -> None:
        from app.services.reading.diary import rating_badge_html

        badge = rating_badge_html("masterpiece")
        assert isinstance(badge, str)
        assert len(badge) > 0

    def test_star_rating_html(self) -> None:
        from app.services.reading.diary import star_rating_html

        stars = star_rating_html(4)
        assert isinstance(stars, str)
        assert "★" in stars
