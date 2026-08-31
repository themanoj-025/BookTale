"""Tests for User model (app/models/user.py)."""

from datetime import datetime, timedelta

from app.models.user import (
    MAX_BORROW_LIMIT,
    MEMBERSHIP_VALIDITY_DAYS,
    ROLES,
    User,
)


class TestUserCreation:
    """Test User instantiation."""

    def test_minimal_user(self) -> None:
        u = User(
            user_id="U001", name="John", email="j@x.com",
            phone="1234567890", role="user", password_hash="hashed",
        )
        assert u.user_id == "U001"
        assert u.name == "John"
        assert u.membership_status == "Active"
        assert u.books_issued == []
        assert u.unpaid_fine == 0.0
        assert u.theme == "light"

    def test_roles_constant(self) -> None:
        assert "admin" in ROLES
        assert "librarian" in ROLES
        assert "user" in ROLES

    def test_config_constants(self) -> None:
        assert isinstance(MAX_BORROW_LIMIT, int)
        assert isinstance(MEMBERSHIP_VALIDITY_DAYS, int)


class TestUserSerialization:
    """Test to_dict and from_dict round-trip."""

    def test_to_dict(self) -> None:
        u = User(
            user_id="U001", name="John", email="j@x.com",
            phone="123", role="user", password_hash="h",
        )
        d = u.to_dict()
        assert d["user_id"] == "U001"
        assert isinstance(d, dict)

    def test_from_dict_minimal(self) -> None:
        data = {
            "user_id": "U001", "name": "John", "email": "j@x.com",
            "phone": "123", "role": "user", "password_hash": "h",
        }
        u = User.from_dict(data)
        assert u.bio == ""
        assert u.theme == "light"
        assert u.favorite_genres == []
        assert u.privacy_profile_visibility == "public"
        assert u.reading_default_goal == 12

    def test_from_dict_full(self) -> None:
        data = {
            "user_id": "U001", "name": "John", "email": "j@x.com",
            "phone": "123", "role": "admin", "password_hash": "h",
            "bio": "Reader", "theme": "dark", "font_size": "large",
            "favorite_genres": ["fiction"], "favorite_books": ["B001"],
        }
        u = User.from_dict(data)
        assert u.bio == "Reader"
        assert u.theme == "dark"
        assert u.favorite_genres == ["fiction"]
        assert u.favorite_books == ["B001"]

    def test_roundtrip(self) -> None:
        u1 = User(
            user_id="U001", name="John", email="j@x.com",
            phone="123", role="user", password_hash="h",
        )
        u2 = User.from_dict(u1.to_dict())
        assert u1.user_id == u2.user_id
        assert u1.name == u2.name


class TestUserActivity:
    """Test is_active and can_borrow."""

    def test_active_user(self) -> None:
        u = User(
            user_id="U001", name="J", email="j@x.com",
            phone="123", role="user", password_hash="h",
            membership_expiry=(datetime.now() + timedelta(days=30)).isoformat(),
        )
        assert u.is_active() is True

    def test_blocked_user(self) -> None:
        u = User(
            user_id="U001", name="J", email="j@x.com",
            phone="123", role="user", password_hash="h",
            membership_status="Blocked",
            membership_expiry=(datetime.now() + timedelta(days=30)).isoformat(),
        )
        assert u.is_active() is False

    def test_expired_user(self) -> None:
        u = User(
            user_id="U001", name="J", email="j@x.com",
            phone="123", role="user", password_hash="h",
            membership_expiry=(datetime.now() - timedelta(days=1)).isoformat(),
        )
        assert u.is_active() is False
        assert u.membership_status == "Expired"

    def test_can_borrow_active(self) -> None:
        u = User(
            user_id="U001", name="J", email="j@x.com",
            phone="123", role="user", password_hash="h",
            membership_expiry=(datetime.now() + timedelta(days=30)).isoformat(),
        )
        assert u.can_borrow() is True

    def test_cannot_borrow_at_limit(self) -> None:
        u = User(
            user_id="U001", name="J", email="j@x.com",
            phone="123", role="user", password_hash="h",
            membership_expiry=(datetime.now() + timedelta(days=30)).isoformat(),
            books_issued=["B001", "B002", "B003"],
        )
        assert u.can_borrow() is False


class TestUserDisplay:
    """Test display output."""

    def test_display(self) -> None:
        u = User(
            user_id="U001", name="John", email="j@x.com",
            phone="123", role="user", password_hash="h",
        )
        d = u.display()
        assert "U001" in d
        assert "John" in d
        assert "j@x.com" in d
