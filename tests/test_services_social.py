"""Tests for Book-Tale SocialFeed."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.social.social import SocialFeed

pytestmark = pytest.mark.unit



@pytest.fixture()
def feed() -> SocialFeed:
    storage = MagicMock()
    storage.load_social.return_value = {
        "posts": [],
        "comments": [],
        "follows": [],
    }
    return SocialFeed(storage)


class TestSocialFeed:
    def test_create_post(self, feed: SocialFeed) -> None:
        result = feed.create_post("u1", "Great book!", post_type="text")
        assert result is not None
        assert result["content"] == "Great book!"
        assert result["user_id"] == "u1"

    def test_create_post_empty_content(self, feed: SocialFeed) -> None:
        result = feed.create_post("u1", "")
        assert result is None

    def test_like_post(self, feed: SocialFeed) -> None:
        post = {"post_id": "P1", "likes": [], "like_count": 0}
        feed.storage.load_social.return_value = {"posts": [post], "comments": [], "follows": []}
        ok = feed.like_post("P1", "u1")
        assert ok is True

    def test_unlike_post(self, feed: SocialFeed) -> None:
        post = {"post_id": "P1", "likes": ["u1"], "like_count": 1}
        feed.storage.load_social.return_value = {"posts": [post], "comments": [], "follows": []}
        ok = feed.unlike_post("P1", "u1")
        assert ok is True

    def test_add_comment(self, feed: SocialFeed) -> None:
        post = {"post_id": "P1", "comment_count": 0}
        feed.storage.load_social.return_value = {"posts": [post], "comments": [], "follows": []}
        result = feed.add_comment("P1", "u1", "Nice!")
        assert result is not None
        assert result["content"] == "Nice!"

    def test_follow_user(self, feed: SocialFeed) -> None:
        feed.storage.load_social.return_value = {"posts": [], "comments": [], "follows": []}
        ok = feed.follow("u1", "u2")
        assert ok is True

    def test_unfollow_user(self, feed: SocialFeed) -> None:
        follow = {"follower_id": "u1", "following_id": "u2"}
        feed.storage.load_social.return_value = {
            "posts": [],
            "comments": [],
            "follows": [follow],
        }
        ok = feed.unfollow("u1", "u2")
        assert ok is True

    def test_get_feed(self, feed: SocialFeed) -> None:
        post = {"post_id": "P1", "user_id": "u1", "created_at": "2024-01-01"}
        feed.storage.load_social.return_value = {"posts": [post], "comments": [], "follows": []}
        result = feed.get_feed("u1")
        assert isinstance(result, list)
