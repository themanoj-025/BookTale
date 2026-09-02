"""Tests for Book-Tale NotificationManager."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.notifications.notifications import NotificationManager

pytestmark = pytest.mark.unit



@pytest.fixture()
def mgr() -> NotificationManager:
    storage = MagicMock()
    storage.load_notifications.return_value = []
    return NotificationManager(storage)


class TestNotifications:
    def test_add_notification(self, mgr: NotificationManager) -> None:
        mgr.storage.append_notification = MagicMock()
        nid = mgr.add_notification("u1", "review", "New review!")
        assert "NOTIF-" in nid

    def test_get_unread_count(self, mgr: NotificationManager) -> None:
        mgr.storage.load_notifications.return_value = [
            {"user_id": "u1", "read": False},
            {"user_id": "u1", "read": True},
            {"user_id": "u2", "read": False},
        ]
        assert mgr.get_unread_count("u1") == 1

    def test_get_notifications(self, mgr: NotificationManager) -> None:
        mgr.storage.load_notifications.return_value = [
            {"user_id": "u1", "created_at": "2024-01-01", "read": False},
            {"user_id": "u1", "created_at": "2024-01-02", "read": False},
            {"user_id": "u2", "created_at": "2024-01-03", "read": False},
        ]
        result = mgr.get_notifications("u1")
        assert len(result) == 2

    def test_get_notifications_unread_only(self, mgr: NotificationManager) -> None:
        mgr.storage.load_notifications.return_value = [
            {"user_id": "u1", "created_at": "2024-01-01", "read": True},
            {"user_id": "u1", "created_at": "2024-01-02", "read": False},
        ]
        result = mgr.get_notifications("u1", unread_only=True)
        assert len(result) == 1

    def test_mark_as_read(self, mgr: NotificationManager) -> None:
        notifs = [
            {"notif_id": "N1", "user_id": "u1", "read": False},
            {"notif_id": "N2", "user_id": "u1", "read": False},
        ]
        mgr.storage.load_notifications.return_value = notifs
        mgr.mark_as_read("N1")
        mgr.storage.save_notifications.assert_called_once()
        saved = mgr.storage.save_notifications.call_args[0][0]
        assert saved[0]["read"] is True
        assert saved[1]["read"] is False

    def test_mark_all_read(self, mgr: NotificationManager) -> None:
        notifs = [
            {"notif_id": "N1", "user_id": "u1", "read": False},
            {"notif_id": "N2", "user_id": "u1", "read": False},
            {"notif_id": "N3", "user_id": "u2", "read": False},
        ]
        mgr.storage.load_notifications.return_value = notifs
        mgr.mark_all_read("u1")
        saved = mgr.storage.save_notifications.call_args[0][0]
        assert saved[0]["read"] is True
        assert saved[1]["read"] is True
        assert saved[2]["read"] is False  # different user

    def test_notify_overdue(self, mgr: NotificationManager) -> None:
        mgr.storage.append_notification = MagicMock()
        nid = mgr.notify_overdue("u1", "The Hobbit", 7, 1.50)
        assert "NOTIF-" in nid
