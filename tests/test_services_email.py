"""Tests for Book-Tale email notifier."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from app.services.email.email_notifier import is_smtp_configured, send_email


class TestSMTPConfig:
    def test_smtp_not_configured(self) -> None:
        with patch("app.services.email.email_notifier.Config") as mock_cfg:
            mock_cfg.SMTP_HOST = ""
            mock_cfg.SMTP_USER = ""
            mock_cfg.SMTP_PASSWORD = ""
            assert is_smtp_configured() is False

    def test_smtp_configured(self) -> None:
        with patch("app.services.email.email_notifier.Config") as mock_cfg:
            mock_cfg.SMTP_HOST = "smtp.example.com"
            mock_cfg.SMTP_USER = "user@example.com"
            mock_cfg.SMTP_PASSWORD = "pass"
            assert is_smtp_configured() is True


class TestSendEmail:
    def test_send_email_smtp_not_configured(self) -> None:
        with patch("app.services.email.email_notifier.is_smtp_configured", return_value=False):
            result = send_email("test@example.com", "Subject", "<b>Hello</b>")
            assert result is False

    def test_send_email_success(self) -> None:
        with patch("app.services.email.email_notifier.is_smtp_configured", return_value=True), \
             patch("app.services.email.email_notifier.smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
            result = send_email("test@example.com", "Subject", "<b>Hello</b>")
            assert result is True

    def test_send_email_failure(self) -> None:
        with patch("app.services.email.email_notifier.is_smtp_configured", return_value=True), \
             patch("app.services.email.email_notifier.smtplib.SMTP", side_effect=OSError("Connection failed")):
            result = send_email("test@example.com", "Subject", "<b>Hello</b>")
            assert result is False
