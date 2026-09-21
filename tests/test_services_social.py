"""Tests for Book-Tale SocialFeed.

Rewritten against the real app.services.social.social.SocialFeed API:
- create_post returns the post dict (no empty-content guard at service level)
- like_post toggles and returns (success, message, is_liked)
- follow_user / unfollow_user (not follow / unfollow)
- get_feed returns (enriched_posts, total)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.social.social import SocialFeed

pytestmark = pytest.mark.unit


@pytest.fixture()
def storage() -> MagicMock:
    st = MagicMock()
    st.load_posts.return_value = []
    st.load_comments.return_value = []
    st.load_follows.return_value = []
    st.load_users.return_value = {}
    st.load_books.return_value = {}
    return st


@pytest.fixture()
def feed(storage: MagicMock) -> SocialFeed:
    return SocialFeed(storage)


class TestPosts:
    def test_create_post(self, feed: SocialFeed) -> None:
        result = feed.create_post("u1", "Great book!", post_type="text")
        assert result is not None
        assert result["content"] == "Great book!"
        assert result["user_id"] == "u1"
        assert result["type"] == "text"
        feed.storage.append_post.assert_called_once()

    def test_create_post_strips_whitespace(self, feed: SocialFeed) -> None:
        result = feed.create_post("u1", "  padded  ")
        assert result["content"] == "padded"

    def test_get_post(self, feed: SocialFeed, storage: MagicMock) -> None:
        storage.load_posts.return_value = [{"post_id": "P1", "user_id": "u1"}]
        assert feed.get_post("P1") is not None
        assert feed.get_post("NOPE") is None

    def test_update_post(self, feed: SocialFeed, storage: MagicMock) -> None:
        storage.load_posts.return_value = [{"post_id": "P1", "user_id": "u1", "content": "old"}]
        ok, msg = feed.update_post("P1", "u1", content="new")
        assert ok is True
        assert msg == "Post updated"

    def test_update_post_not_author(self, feed: SocialFeed, storage: MagicMock) -> None:
        storage.load_posts.return_value = [{"post_id": "P1", "user_id": "someone-else"}]
        ok, msg = feed.update_post("P1", "u1", content="new")
        assert ok is False
        assert "own" in msg.lower()

    def test_delete_post(self, feed: SocialFeed, storage: MagicMock) -> None:
        storage.load_posts.return_value = [{"post_id": "P1", "user_id": "u1"}]
        ok, _msg = feed.delete_post("P1", "u1")
        assert ok is True


class TestLikesAndComments:
    def test_like_post(self, feed: SocialFeed, storage: MagicMock) -> None:
        storage.load_posts.return_value = [{"post_id": "P1", "likes": []}]
        ok, _msg, liked = feed.like_post("P1", "u1")
        assert ok is True
        assert liked is True

    def test_like_post_toggles_off(self, feed: SocialFeed, storage: MagicMock) -> None:
        storage.load_posts.return_value = [{"post_id": "P1", "likes": ["u1"]}]
        ok, _msg, liked = feed.like_post("P1", "u1")
        assert ok is True
        assert liked is False

    def test_like_post_not_found(self, feed: SocialFeed) -> None:
        ok, _msg, _liked = feed.like_post("NOPE", "u1")
        assert ok is False

    def test_add_comment(self, feed: SocialFeed, storage: MagicMock) -> None:
        storage.load_posts.return_value = [{"post_id": "P1", "comment_count": 0}]
        ok, _msg, comment = feed.add_comment("P1", "u1", "Nice!")
        assert ok is True
        assert comment is not None
        assert comment["content"] == "Nice!"

    def test_add_comment_missing_post(self, feed: SocialFeed) -> None:
        ok, msg, _comment = feed.add_comment("NOPE", "u1", "Nice!")
        assert ok is False
        assert "not found" in msg.lower()

    def test_add_comment_empty(self, feed: SocialFeed, storage: MagicMock) -> None:
        storage.load_posts.return_value = [{"post_id": "P1"}]
        ok, _msg, _comment = feed.add_comment("P1", "u1", "   ")
        assert ok is False

    def test_get_comments(self, feed: SocialFeed, storage: MagicMock) -> None:
        storage.load_comments.return_value = [
            {"comment_id": "C1", "post_id": "P1", "created_at": "2024-01-01T00:00:00"},
            {"comment_id": "C2", "post_id": "P2", "created_at": "2024-01-02T00:00:00"},
        ]
        result = feed.get_comments("P1")
        assert len(result) == 1


class TestFollows:
    def test_follow_user(self, feed: SocialFeed, storage: MagicMock) -> None:
        ok, _msg = feed.follow_user("u1", "u2")
        assert ok is True

    def test_follow_self(self, feed: SocialFeed) -> None:
        ok, msg = feed.follow_user("u1", "u1")
        assert ok is False
        assert "yourself" in msg.lower()

    def test_follow_duplicate(self, feed: SocialFeed, storage: MagicMock) -> None:
        storage.load_follows.return_value = [
            {"follower_id": "u1", "following_id": "u2"},
        ]
        ok, msg = feed.follow_user("u1", "u2")
        assert ok is False
        assert "already" in msg.lower()

    def test_unfollow_user(self, feed: SocialFeed, storage: MagicMock) -> None:
        storage.load_follows.return_value = [
            {"follower_id": "u1", "following_id": "u2"},
        ]
        ok, _msg = feed.unfollow_user("u1", "u2")
        assert ok is True

    def test_unfollow_not_following(self, feed: SocialFeed) -> None:
        ok, _msg = feed.unfollow_user("u1", "u2")
        assert ok is False

    def test_get_followers_and_counts(self, feed: SocialFeed, storage: MagicMock) -> None:
        storage.load_follows.return_value = [
            {"follower_id": "u2", "following_id": "u1"},
            {"follower_id": "u3", "following_id": "u1"},
            {"follower_id": "u1", "following_id": "u4"},
        ]
        assert feed.get_followers("u1") == ["u2", "u3"]
        assert feed.get_follower_count("u1") == 2
        assert feed.get_following("u1") == ["u4"]
        assert feed.get_following_count("u1") == 1
        assert feed.is_following("u1", "u4") is True
        assert feed.is_following("u4", "u1") is False


class TestFeed:
    def test_get_feed(self, feed: SocialFeed, storage: MagicMock) -> None:
        storage.load_posts.return_value = [
            {"post_id": "P1", "user_id": "u1", "created_at": "2024-01-01T00:00:00", "likes": []},
        ]
        posts, total = feed.get_feed("u1")
        assert total == 1
        assert posts[0]["post_id"] == "P1"

    def test_get_feed_paginates(self, feed: SocialFeed, storage: MagicMock) -> None:
        storage.load_posts.return_value = [
            {"post_id": f"P{i}", "user_id": "u1", "created_at": "2024-01-01T00:00:00", "likes": []}
            for i in range(5)
        ]
        posts, total = feed.get_feed("u1", page=2, per_page=2)
        assert total == 5
        assert len(posts) == 2

    def test_get_user_posts(self, feed: SocialFeed, storage: MagicMock) -> None:
        storage.load_posts.return_value = [
            {"post_id": "P1", "user_id": "u1", "created_at": "2024-01-01T00:00:00"},
            {"post_id": "P2", "user_id": "u2", "created_at": "2024-01-01T00:00:00"},
        ]
        posts, total = feed.get_user_posts("u1", viewer_id="u2")
        assert total == 1
        assert posts[0]["post_id"] == "P1"
