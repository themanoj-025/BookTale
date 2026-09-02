"""Tests for Book-Tale authentication service."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.exceptions import AuthenticationError
from app.services.auth.auth import (

pytestmark = pytest.mark.unit

    AuthManager,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    """Test hash_password and verify_password."""

    def test_hash_and_verify(self) -> None:
        pwd = "MyStr0ng!"
        hashed = hash_password(pwd)
        assert verify_password(pwd, hashed) is True

    def test_wrong_password(self) -> None:
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_hash_is_bcrypt(self) -> None:
        hashed = hash_password("test")
        assert hashed.startswith("$2")

    def test_different_hashes(self) -> None:
        h1 = hash_password("same")
        h2 = hash_password("same")
        # bcrypt uses random salt — hashes should differ
        assert h1 != h2

    def test_verify_empty_password(self) -> None:
        hashed = hash_password("notempty")
        assert verify_password("", hashed) is False

    def test_verify_invalid_hash(self) -> None:
        assert verify_password("test", "not-a-hash") is False


class TestAuthManager:
    """Test AuthManager login/logout logic."""

    def _make_manager(self, users: dict | None = None) -> AuthManager:
        storage = MagicMock()
        storage.load_users.return_value = users or {}
        return AuthManager(storage)

    def test_login_success(self) -> None:
        pwd = "pass123"
        hashed = hash_password(pwd)
        user = MagicMock()
        user.password_hash = hashed
        user.lock_until = None
        user.failed_login_attempts = 0
        user.membership_expiry = "2099-01-01T00:00:00"
        user.is_active = True

        mgr = self._make_manager({"user1": user})
        result = mgr.login("user1", pwd)
        assert result is user

    def test_login_wrong_password(self) -> None:
        hashed = hash_password("correct")
        user = MagicMock()
        user.password_hash = hashed
        user.lock_until = None
        user.failed_login_attempts = 0

        mgr = self._make_manager({"user1": user})
        with pytest.raises(AuthenticationError):
            mgr.login("user1", "wrong")

    def test_login_nonexistent_user(self) -> None:
        mgr = self._make_manager({})
        with pytest.raises(AuthenticationError):
            mgr.login("ghost", "pwd")

    def test_login_locked_account(self) -> None:
        from datetime import datetime, timedelta

        future = (datetime.now() + timedelta(hours=1)).isoformat()
        user = MagicMock()
        user.lock_until = future
        user.failed_login_attempts = 5

        mgr = self._make_manager({"user1": user})
        with pytest.raises(AuthenticationError):
            mgr.login("user1", "any")

    def test_login_expired_lock_resets(self) -> None:
        from datetime import datetime, timedelta

        past = (datetime.now() - timedelta(hours=1)).isoformat()
        hashed = hash_password("pwd")
        user = MagicMock()
        user.password_hash = hashed
        user.lock_until = past
        user.failed_login_attempts = 5
        user.membership_expiry = "2099-01-01T00:00:00"
        user.is_active = True

        mgr = self._make_manager({"user1": user})
        result = mgr.login("user1", "pwd")
        assert result is user

    def test_logout(self) -> None:
        mgr = self._make_manager()
        mgr.current_user = MagicMock()
        mgr.logout()
        assert mgr.current_user is None
