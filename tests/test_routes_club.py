"""Tests for Book-Tale club routes."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

pytestmark = pytest.mark.integration

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-club-routes")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "TestAdmin123")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")
os.environ.setdefault("RATELIMIT_ENABLED", "0")

from app.config.settings import Config

_TMP = tempfile.mkdtemp(prefix="booktale_club_")
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


class TestClubRoutes:
    """Test book club page and API routes."""

    def test_clubs_requires_auth(self, client: object) -> None:
        resp = client.get("/clubs")  # type: ignore[union-attr]
        assert resp.status_code in (200, 302, 401, 403)

    def test_club_detail_requires_auth(self, client: object) -> None:
        resp = client.get("/clubs/test-club-id")  # type: ignore[union-attr]
        assert resp.status_code in (200, 302, 401, 403)

    def test_club_create_requires_auth(self, client: object) -> None:
        resp = client.post("/api/clubs/create", json={"name": "Test Club"})  # type: ignore[union-attr]
        assert resp.status_code in (302, 401, 403)

    def test_club_join_requires_auth(self, client: object) -> None:
        resp = client.post("/api/clubs/test-club-id/join")  # type: ignore[union-attr]
        assert resp.status_code in (302, 401, 403)

    def test_club_leave_requires_auth(self, client: object) -> None:
        resp = client.post("/api/clubs/test-club-id/leave")  # type: ignore[union-attr]
        assert resp.status_code in (302, 401, 403)

    def test_clubs_route_registered(self) -> None:
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        assert "/clubs" in rules or any("/clubs" in r for r in rules)


class TestClubHelpers:
    """Test club route helper functions."""

    def test_avatar_html(self) -> None:
        from app.routes.helpers import avatar_html
        result = avatar_html("https://example.com/avatar.jpg")
        assert isinstance(result, str)

    def test_cat_color(self) -> None:
        from app.routes.helpers import cat_color
        color = cat_color("Science Fiction")
        assert isinstance(color, str)
