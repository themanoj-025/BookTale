"""Tests for realtime module."""

from unittest.mock import MagicMock

import pytest

from app.realtime.realtime import RealtimeManager


@pytest.fixture
def mock_storage() -> MagicMock:
    storage = MagicMock()
    storage.load_users.return_value = {}
    return storage


@pytest.fixture
def manager(mock_storage: MagicMock) -> RealtimeManager:
    return RealtimeManager(mock_storage)


class TestRealtimeManager:
    """Tests for RealtimeManager."""

    def test_user_connected(self, manager: RealtimeManager) -> None:
        manager.user_connected("u1", "sid1")
        assert manager.is_online("u1")
        assert manager.get_online_count() == 1

    def test_user_disconnected(self, manager: RealtimeManager) -> None:
        manager.user_connected("u1", "sid1")
        manager.user_disconnected("u1")
        assert not manager.is_online("u1")
        assert manager.get_online_count() == 0

    def test_get_online_count(self, manager: RealtimeManager) -> None:
        assert manager.get_online_count() == 0
        manager.user_connected("u1", "sid1")
        manager.user_connected("u2", "sid2")
        assert manager.get_online_count() == 2

    def test_is_online(self, manager: RealtimeManager) -> None:
        assert not manager.is_online("u1")
        manager.user_connected("u1", "sid1")
        assert manager.is_online("u1")

    def test_viewer_joined(self, manager: RealtimeManager, mock_storage: MagicMock) -> None:
        mock_storage.load_users.return_value = {"u1": MagicMock(name="User1")}
        viewers = manager.viewer_joined("p1", "u1")
        assert len(viewers) == 1
        assert viewers[0]["user_id"] == "u1"

    def test_viewer_left(self, manager: RealtimeManager) -> None:
        manager.viewer_joined("p1", "u1")
        manager.viewer_left("p1", "u1")
        assert "p1" not in manager.post_viewers

    def test_disconnected_cleans_viewers(self, manager: RealtimeManager) -> None:
        manager.viewer_joined("p1", "u1")
        manager.user_disconnected("u1")
        assert "p1" not in manager.post_viewers

    def test_disconnected_cleans_typing(self, manager: RealtimeManager) -> None:
        manager.post_typing["p1"] = {"u1": 1.0}
        manager.user_disconnected("u1")
        assert "p1" not in manager.post_typing
