"""
social.py - Social Feed Engine for Book Social Media Platform

Provides the core social functionality:
- Posts with rich text, book tags, image uploads
- Comments & threaded replies
- Like/unlike system
- Follow/unfollow system
- Feed generation (following, trending, personalized)
- Real-time event triggers
"""

import uuid
from datetime import datetime

from app.core.logger import log
from app.storage.storage import Storage


def _gen_id(prefix: str = "POST") -> str:
    """Generate a unique ID with timestamp for ordering."""
    ts = int(datetime.now().timestamp() * 1000)
    uid = str(uuid.uuid4())[:8]
    return f"{prefix}-{ts}-{uid}"


POST_SCHEMA = {
    "post_id",
    "user_id",
    "content",
    "type",
    "book_ids",
    "image_urls",
    "created_at",
    "updated_at",
    "likes",
    "comment_count",
    "is_pinned",
}

COMMENT_SCHEMA = {
    "comment_id",
    "post_id",
    "user_id",
    "content",
    "parent_id",
    "created_at",
    "likes",
}

FOLLOW_SCHEMA = {"follow_id", "follower_id", "following_id", "created_at"}


class SocialFeed:
    """Core social feed engine — posts, comments, likes, follows."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    # ═══════════════════════════════════════════════════════════════
    # POSTS
    # ═══════════════════════════════════════════════════════════════

    def create_post(
        self,
        user_id: str,
        content: str,
        post_type: str = "post",
        book_ids: list[str] | None = None,
        image_urls: list[str] | None = None,
    ) -> dict:
        """Create a new post. Returns the post dict."""
        now = datetime.now().isoformat()
        post = {
            "post_id": _gen_id("POST"),
            "user_id": user_id,
            "content": content.strip(),
            "type": post_type,  # post, review, discussion, news
            "book_ids": book_ids or [],
            "image_urls": image_urls or [],
            "created_at": now,
            "updated_at": now,
            "likes": [],
            "upvotes": [],
            "downvotes": [],
            "comment_count": 0,
            "is_pinned": False,
        }
        self.storage.append_post(post)
        log(f"Created post: {post['post_id'][:20]}...", user_id, f"type:{post_type}")
        return post

    def get_post(self, post_id: str) -> dict | None:
        """Get a single post by ID."""
        posts = self.storage.load_posts()
        for p in posts:
            if p["post_id"] == post_id:
                return p
        return None

    def update_post(
        self,
        post_id: str,
        user_id: str,
        content: str | None = None,
        image_urls: list[str] | None = None,
    ) -> tuple[bool, str]:
        """Update a post. Only the author can edit."""
        posts = self.storage.load_posts()
        for p in posts:
            if p["post_id"] == post_id:
                if p["user_id"] != user_id:
                    return False, "You can only edit your own posts"
                if content is not None:
                    p["content"] = content.strip()
                if image_urls is not None:
                    p["image_urls"] = image_urls
                p["updated_at"] = datetime.now().isoformat()
                self.storage.save_posts(posts)
                return True, "Post updated"
        return False, "Post not found"

    def delete_post(self, post_id: str, user_id: str) -> tuple[bool, str]:
        """Delete a post. Author or admin can delete."""
        posts = self.storage.load_posts()
        users = self.storage.load_users()
        user = users.get(user_id)
        is_admin = user and user.role == "admin"
        for p in posts:
            if p["post_id"] == post_id:
                if p["user_id"] != user_id and not is_admin:
                    return False, "You can only delete your own posts"
                posts.remove(p)
                self.storage.save_posts(posts)
                log(f"Deleted post {post_id}", user_id)
                return True, "Post deleted"
        return False, "Post not found"

    def like_post(self, post_id: str, user_id: str) -> tuple[bool, str, bool]:
        """Toggle like on a post. Returns (success, message, is_liked)."""
        posts = self.storage.load_posts()
        for p in posts:
            if p["post_id"] == post_id:
                if user_id in p["likes"]:
                    p["likes"].remove(user_id)
                    self.storage.save_posts(posts)
                    return True, "Post unliked", False
                else:
                    p["likes"].append(user_id)
                    # Remove from downvotes if was downvoted
                    if user_id in p.get("downvotes", []):
                        p["downvotes"].remove(user_id)
                    self.storage.save_posts(posts)
                    return True, "Post liked", True
        return False, "Post not found", False

    def vote_post(self, post_id: str, user_id: str, vote: str) -> tuple[bool, str, int | None]:
        """Reddit-style voting: 'up', 'down', or 'none' to remove vote.
        Returns (success, message, net_score)."""
        posts = self.storage.load_posts()
        for p in posts:
            if p["post_id"] == post_id:
                if "upvotes" not in p:
                    p["upvotes"] = []
                    # Remove from opposite vote first
                if vote == "up":
                    if user_id in p["downvotes"]:
                        p["downvotes"].remove(user_id)
                    if user_id not in p["upvotes"]:
                        p["upvotes"].append(user_id)
                    else:
                        p["upvotes"].remove(user_id)
                        vote = "none"
                elif vote == "down":
                    if user_id in p["upvotes"]:
                        p["upvotes"].remove(user_id)
                    if user_id not in p["downvotes"]:
                        p["downvotes"].append(user_id)
                    else:
                        p["downvotes"].remove(user_id)
                        vote = "none"

                self.storage.save_posts(posts)
                net = len(p["upvotes"]) - len(p["downvotes"])
                log(f"Vote {vote} on {post_id}", user_id)
                return True, "Vote recorded", net
        return False, "Post not found", None

    # ═══════════════════════════════════════════════════════════════
    # COMMENTS
    # ═══════════════════════════════════════════════════════════════

    def add_comment(
        self, post_id: str, user_id: str, content: str, parent_id: str | None = None
    ) -> tuple[bool, str, dict | None]:
        """Add a comment to a post. Returns (success, message, comment)."""
        # Verify post exists
        post = self.get_post(post_id)
        if not post:
            return False, "Post not found", None

        if not content.strip():
            return False, "Comment cannot be empty", None

        comment = {
            "comment_id": _gen_id("COMM"),
            "post_id": post_id,
            "user_id": user_id,
            "content": content.strip(),
            "parent_id": parent_id,  # None = top-level, else threaded reply
            "created_at": datetime.now().isoformat(),
            "likes": [],
        }
        self.storage.append_comment(comment)

        # Update comment count on post
        posts = self.storage.load_posts()
        for p in posts:
            if p["post_id"] == post_id:
                p["comment_count"] = len(
                    [c for c in self.storage.load_comments() if c["post_id"] == post_id]
                )
                break
        self.storage.save_posts(posts)

        log(f"Comment on {post_id}", user_id)
        return True, "Comment added", comment

    def get_comments(self, post_id: str) -> list[dict]:
        """Get all comments for a post, threaded."""
        comments = self.storage.load_comments()
        post_comments = [c for c in comments if c["post_id"] == post_id]
        return sorted(post_comments, key=lambda c: c["created_at"])

    def delete_comment(self, comment_id: str, user_id: str) -> tuple[bool, str]:
        """Delete a comment. Author or admin can delete."""
        comments = self.storage.load_comments()
        users = self.storage.load_users()
        user = users.get(user_id)
        is_admin = user and user.role == "admin"
        for c in comments:
            if c["comment_id"] == comment_id:
                if c["user_id"] != user_id and not is_admin:
                    return False, "You can only delete your own comments"
                comments.remove(c)
                self.storage.save_comments(comments)
                return True, "Comment deleted"
        return False, "Comment not found"

    def like_comment(self, comment_id: str, user_id: str) -> tuple[bool, str, bool]:
        """Toggle like on a comment."""
        comments = self.storage.load_comments()
        for c in comments:
            if c["comment_id"] == comment_id:
                if user_id in c["likes"]:
                    c["likes"].remove(user_id)
                    self.storage.save_comments(comments)
                    return True, "Unliked", False
                else:
                    c["likes"].append(user_id)
                    self.storage.save_comments(comments)
                    return True, "Liked", True
        return False, "Comment not found", False

    # ═══════════════════════════════════════════════════════════════
    # FOLLOWS
    # ═══════════════════════════════════════════════════════════════

    def follow_user(self, follower_id: str, following_id: str) -> tuple[bool, str]:
        """Follow a user. Returns (success, message)."""
        if follower_id == following_id:
            return False, "You cannot follow yourself"

        follows = self.storage.load_follows()
        for f in follows:
            if f["follower_id"] == follower_id and f["following_id"] == following_id:
                return False, "Already following this user"

        follow = {
            "follow_id": _gen_id("FOL"),
            "follower_id": follower_id,
            "following_id": following_id,
            "created_at": datetime.now().isoformat(),
        }
        follows.append(follow)
        self.storage.save_follows(follows)
        log(f"{follower_id} followed {following_id}", follower_id)
        return True, f"Now following {following_id}"

    def unfollow_user(self, follower_id: str, following_id: str) -> tuple[bool, str]:
        """Unfollow a user."""
        follows = self.storage.load_follows()
        for f in follows:
            if f["follower_id"] == follower_id and f["following_id"] == following_id:
                follows.remove(f)
                self.storage.save_follows(follows)
                return True, "Unfollowed"
        return False, "Not following this user"

    def get_followers(self, user_id: str) -> list[str]:
        """Get list of user IDs that follow this user."""
        follows = self.storage.load_follows()
        return [f["follower_id"] for f in follows if f["following_id"] == user_id]

    def get_following(self, user_id: str) -> list[str]:
        """Get list of user IDs this user follows."""
        follows = self.storage.load_follows()
        return [f["following_id"] for f in follows if f["follower_id"] == user_id]

    def is_following(self, follower_id: str, following_id: str) -> bool:
        """Check if follower_id follows following_id."""
        follows = self.storage.load_follows()
        return any(
            f["follower_id"] == follower_id and f["following_id"] == following_id for f in follows
        )

    def get_follower_count(self, user_id: str) -> int:
        return len(self.get_followers(user_id))

    def get_following_count(self, user_id: str) -> int:
        return len(self.get_following(user_id))

    # ═══════════════════════════════════════════════════════════════
    # FEED GENERATION
    # ═══════════════════════════════════════════════════════════════

    def get_feed(self, user_id: str, page: int = 1, per_page: int = 20) -> tuple[list[dict], int]:
        """Get the main social feed for a user.

        Feed algorithm:
        1. Posts from users they follow (weighted 3x)
        2. Trending posts (high engagement, weighted 2x)
        3. Recent posts from everyone else (weighted 1x)
        4. Sorted by score (engagement + recency)
        """
        posts = self.storage.load_posts()
        following = set(self.get_following(user_id))
        users = self.storage.load_users()
        books = self.storage.load_books()
        now = datetime.now()

        scored_posts = []
        for p in posts:
            score = 0.0
            created = datetime.fromisoformat(p["created_at"])
            hours_ago = (now - created).total_seconds() / 3600

            # Recency bonus
            recency = max(0, 100 - hours_ago) / 100
            score += recency * 10

            # Following boost (3x)
            if p["user_id"] in following:
                score += 30

            # Engagement bonus
            likes_count = len(p.get("likes", []))
            comments_count = p.get("comment_count", 0)
            score += min(likes_count * 2, 20)
            score += min(comments_count * 3, 15)

            # Trending boost (high engagement in short time)
            if hours_ago < 48 and (likes_count + comments_count) > 5:
                score += (likes_count + comments_count) * 0.5

            scored_posts.append((score, p))

        # Sort by score descending
        scored_posts.sort(key=lambda x: x[0], reverse=True)

        total = len(scored_posts)
        start = (page - 1) * per_page
        end = start + per_page
        page_posts = scored_posts[start:end]

        # Enrich posts with user/book data
        enriched = self._enrich_posts([p for _, p in page_posts], user_id, users, books)
        return enriched, total

    def get_trending_feed(
        self, user_id: str, page: int = 1, per_page: int = 20
    ) -> tuple[list[dict], int]:
        """Trending feed — like Reddit's r/books hot posts."""
        posts = self.storage.load_posts()
        users = self.storage.load_users()
        books = self.storage.load_books()
        now = datetime.now()

        scored_posts = []
        for p in posts:
            created = datetime.fromisoformat(p["created_at"])
            hours_ago = (now - created).total_seconds() / 3600
            likes = len(p.get("likes", []))
            comments = p.get("comment_count", 0)

            # Reddit-style hot ranking
            engagement = likes + comments * 2
            hours_ago = max(hours_ago, 1)
            score = engagement / (hours_ago**0.8)
            scored_posts.append((score, p))

        scored_posts.sort(key=lambda x: x[0], reverse=True)

        total = len(scored_posts)
        start = (page - 1) * per_page
        end = start + per_page
        page_posts = scored_posts[start:end]

        enriched = self._enrich_posts([p for _, p in page_posts], user_id, users, books)
        return enriched, total

    def get_user_posts(
        self, profile_user_id: str, viewer_id: str, page: int = 1, per_page: int = 20
    ) -> tuple[list[dict], int]:
        """Get posts by a specific user for their profile."""
        posts = self.storage.load_posts()
        user_posts = [p for p in posts if p["user_id"] == profile_user_id]
        user_posts.sort(key=lambda p: p["created_at"], reverse=True)

        total = len(user_posts)
        start = (page - 1) * per_page
        end = start + per_page
        page_posts = user_posts[start:end]

        users = self.storage.load_users()
        books = self.storage.load_books()
        enriched = self._enrich_posts(page_posts, viewer_id, users, books)
        return enriched, total

    def get_discover_feed(
        self, user_id: str, page: int = 1, per_page: int = 20
    ) -> tuple[list[dict], int]:
        """Discovery feed — posts from users they DON'T follow, sorted by engagement."""
        posts = self.storage.load_posts()
        following = set(self.get_following(user_id))
        users = self.storage.load_users()
        books = self.storage.load_books()
        now = datetime.now()

        scored_posts = []
        for p in posts:
            if p["user_id"] in following or p["user_id"] == user_id:
                continue
            created = datetime.fromisoformat(p["created_at"])
            hours_ago = (now - created).total_seconds() / 3600
            engagement = len(p.get("likes", [])) + p.get("comment_count", 0) * 2
            score = engagement / max(1, hours_ago**0.7)
            scored_posts.append((score, p))

        scored_posts.sort(key=lambda x: x[0], reverse=True)

        total = len(scored_posts)
        start = (page - 1) * per_page
        end = start + per_page
        page_posts = scored_posts[start:end]

        enriched = self._enrich_posts([p for _, p in page_posts], user_id, users, books)
        return enriched, total

    # ═══════════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════════

    def _enrich_posts(
        self, posts: list[dict], viewer_id: str, users: dict, books: dict
    ) -> list[dict]:
        """Add user and book details to posts."""
        enriched = []
        for p in posts:
            author = users.get(p["user_id"])
            post_books = []
            for bid in p.get("book_ids", []):
                book = books.get(bid)
                if book and not book.is_deleted:
                    post_books.append(
                        {
                            "id": book.book_id,
                            "title": book.title,
                            "author": book.author,
                            "category": book.category,
                        }
                    )

            enriched.append(
                {
                    **p,
                    "author_name": author.name if author else "Unknown",
                    "author_role": author.role if author else "user",
                    "author_avatar": p["user_id"][:2].upper(),
                    "is_liked": viewer_id in p.get("likes", []),
                    "likes_count": len(p.get("likes", [])),
                    "upvotes": p.get("upvotes", []),
                    "downvotes": p.get("downvotes", []),
                    "net_score": len(p.get("upvotes", [])) - len(p.get("downvotes", [])),
                    "user_vote": (
                        "up"
                        if viewer_id in p.get("upvotes", [])
                        else ("down" if viewer_id in p.get("downvotes", []) else "none")
                    ),
                    "books": post_books,
                    "time_ago": self._time_ago(p["created_at"]),
                }
            )
        return enriched

    def _time_ago(self, iso_str: str) -> str:
        """Convert ISO timestamp to human-readable 'time ago' string."""
        try:
            dt = datetime.fromisoformat(iso_str)
            now = datetime.now()
            diff = now - dt
            seconds = int(diff.total_seconds())
            if seconds < 60:
                return "just now"
            minutes = seconds // 60
            if minutes < 60:
                return f"{minutes}m ago"
            hours = minutes // 60
            if hours < 24:
                return f"{hours}h ago"
            days = hours // 24
            if days < 7:
                return f"{days}d ago"
            weeks = days // 7
            if weeks < 4:
                return f"{weeks}w ago"
            months = days // 30
            if months < 12:
                return f"{months}mo ago"
            years = days // 365
            return f"{years}y ago"
        except Exception:
            return iso_str[:10]

    def search_posts(
        self, query: str, user_id: str, page: int = 1, per_page: int = 20
    ) -> tuple[list[dict], int]:
        """Search posts by content."""
        q = query.lower().strip()
        posts = self.storage.load_posts()
        users = self.storage.load_users()
        books = self.storage.load_books()

        results = []
        for p in posts:
            if q in p["content"].lower() or q in p.get("post_id", "").lower():
                results.append(p)
            else:
                # Check if query matches book title in post
                for bid in p.get("book_ids", []):
                    book = books.get(bid)
                    if book and q in book.title.lower():
                        results.append(p)
                        break

        results.sort(key=lambda p: len(p.get("likes", [])), reverse=True)
        total = len(results)
        start = (page - 1) * per_page
        end = start + per_page
        enriched = self._enrich_posts(results[start:end], user_id, users, books)
        return enriched, total
