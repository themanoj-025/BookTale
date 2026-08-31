"""Tests for app.config.settings (Config class)."""

import os
from unittest.mock import patch

import pytest

from app.config.settings import Config, _INSECURE_SECRET_KEYS, validate_secure_config


class TestConfigDefaults:
    """Test Config class defaults."""

    def test_default_values(self) -> None:
        assert Config.ISSUE_DAYS == 14
        assert Config.FINE_PER_DAY == 5.0
        assert Config.MAX_BORROW_LIMIT == 3
        assert Config.MEMBERSHIP_VALIDITY_DAYS == 365

    def test_directories_exist(self) -> None:
        assert isinstance(Config.DATA_DIR, str)
        assert isinstance(Config.LOGS_DIR, str)
        assert isinstance(Config.UPLOADS_DIR, str)

    def test_upload_settings(self) -> None:
        assert Config.MAX_UPLOAD_SIZE > 0
        assert isinstance(Config.ALLOWED_EXTENSIONS, set)

    def test_data_files(self) -> None:
        assert Config.BOOKS_FILE.endswith("books.json")
        assert Config.USERS_FILE.endswith("users.json")
        assert Config.TRANSACTIONS_FILE.endswith("transactions.json")

    def test_redis_default(self) -> None:
        assert "redis" in Config.REDIS_URL

    def test_smtp_defaults(self) -> None:
        assert Config.SMTP_PORT == 587
        assert Config.SMTP_USE_TLS is True

    def test_flask_defaults(self) -> None:
        assert Config.FLASK_PORT == 5000
        assert isinstance(Config.FLASK_DEBUG, bool)


class TestValidateSecureConfig:
    """Test validate_secure_config function."""

    def test_empty_secret_raises(self) -> None:
        with (
            patch.object(Config, "SECRET_KEY", ""),
            patch.dict(os.environ, {"SECRET_KEY": ""}, clear=False),
            patch("app.config.settings.Config.SECRET_KEY", ""),
            pytest.raises(RuntimeError, match="SECRET_KEY"),
        ):
            validate_secure_config()

    def test_known_insecure_keys(self) -> None:
        assert "" in _INSECURE_SECRET_KEYS
        assert "change-this-secret-key-in-production" in _INSECURE_SECRET_KEYS


class TestSettingsOverrides:
    """Test _load_settings_overrides function."""

    def test_missing_override_file(self, tmp_path: object) -> None:
        from app.config.settings import _load_settings_overrides

        # Should not raise when file doesn't exist
        _load_settings_overrides()
