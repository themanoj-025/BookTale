"""
db/models.py - SQLAlchemy 2.0 ORM models.

Every table maps 1:1 to a JSON entity previously stored by storage.py or the
social modules. List-valued JSON fields are stored as JSON columns (portable
across SQLite and PostgreSQL). Indexes cover every FK and every field used in
WHERE / ORDER BY by the hot paths (search, overdue list, stats, reports).
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _now() -> str:
    return datetime.now().isoformat()


# ════════════════════════════════════════════════════════════════════
# CORE LIBRARY
# ════════════════════════════════════════════════════════════════════


class Book(Base):
    __tablename__ = "books"

    book_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    author: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    isbn: Mapped[str] = mapped_column(String(32), nullable=False, default="", index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    total_copies: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    available_copies: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    added_on: Mapped[str] = mapped_column(String(32), nullable=False, default=_now, index=True)

    # Extended metadata (BookTale fields)
    publisher: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    language: Mapped[str] = mapped_column(String(32), nullable=False, default="English")
    release_date: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    cover_image: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    series_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    series_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cover_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cover_fetched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cover_source: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    dominant_color: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    genres: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    __table_args__ = (
        Index("ix_books_title", "title"),
        Index("ix_books_author", "author"),
        Index("ix_books_category_avail", "category", "available_copies"),
    )

    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="book", foreign_keys="Transaction.book_id"
    )


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, default="", index=True)
    phone: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user", index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    membership_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="Active", index=True
    )
    membership_expiry: Mapped[str] = mapped_column(String(32), nullable=False, default=_now)
    books_issued: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    unpaid_fine: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, index=True)
    registered_on: Mapped[str] = mapped_column(String(32), nullable=False, default=_now, index=True)

    # Social profile
    bio: Mapped[str] = mapped_column(Text, nullable=False, default="")
    profile_picture: Mapped[str] = mapped_column(Text, nullable=False, default="")
    website: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    location: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    favorite_genres: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    favorite_books: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Security / rate limiting
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lock_until: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)

    # Settings
    theme: Mapped[str] = mapped_column(String(16), nullable=False, default="light")
    font_size: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    email_notifications: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    push_notifications: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_on_comment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_on_like: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_on_follow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_on_issue_return: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_on_overdue: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_on_due_reminder: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    privacy_show_activity: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    privacy_show_wishlist: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    privacy_show_bookmarks: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    privacy_profile_visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, default="public"
    )
    privacy_show_email: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reading_default_rating: Mapped[str] = mapped_column(
        String(16), nullable=False, default="worth_it"
    )
    reading_goal_type: Mapped[str] = mapped_column(String(16), nullable=False, default="books")
    reading_default_goal: Mapped[int] = mapped_column(Integer, nullable=False, default=12)

    __table_args__ = (
        Index("ix_users_name", "name"),
        Index("ix_users_role_status", "role", "membership_status"),
    )

    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="user", foreign_keys="Transaction.user_id"
    )


class Transaction(Base):
    __tablename__ = "transactions"

    txn_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False, default="issue")
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.book_id"), nullable=False, index=True)
    issue_date: Mapped[str] = mapped_column(String(32), nullable=False, default=_now, index=True)
    due_date: Mapped[str] = mapped_column(String(32), nullable=False, default=_now, index=True)
    return_date: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default=None, index=True
    )
    fine: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    __table_args__ = (
        # Overdue scan: open issues past due date.
        Index("ix_txns_open_due", "return_date", "due_date"),
        # Active loans per user.
        Index("ix_txns_user_open", "user_id", "return_date"),
    )

    user: Mapped["User"] = relationship(back_populates="transactions", foreign_keys=[user_id])
    book: Mapped["Book"] = relationship(back_populates="transactions", foreign_keys=[book_id])


class Reservation(Base):
    """reservations.json was {book_id: [user_ids]} — normalized to rows."""

    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.book_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint("book_id", "user_id", name="uq_reservation_book_user"),
        Index("ix_reservations_book_pos", "book_id", "position"),
    )


class Fine(Base):
    __tablename__ = "fines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    book_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    fine: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    date: Mapped[str] = mapped_column(String(32), nullable=False, default=_now)
    paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    __table_args__ = (Index("ix_fines_user_paid", "user_id", "paid"),)


class Notification(Base):
    __tablename__ = "notifications"

    notif_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=_now, index=True)
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    __table_args__ = (Index("ix_notifs_user_read", "user_id", "read"),)


# ════════════════════════════════════════════════════════════════════
# SOCIAL
# ════════════════════════════════════════════════════════════════════


class Post(Base):
    __tablename__ = "posts"

    post_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="post")
    book_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    image_urls: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=_now, index=True)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False, default=_now)
    likes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Social extras (mirror the JSON post shape from social.py)
    upvotes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    downvotes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    comment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (Index("ix_posts_user_created", "user_id", "created_at"),)


class Comment(Base):
    __tablename__ = "comments"

    comment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    post_id: Mapped[str] = mapped_column(ForeignKey("posts.post_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    parent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=_now, index=True)
    likes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    __table_args__ = (Index("ix_comments_post_created", "post_id", "created_at"),)


class Follow(Base):
    __tablename__ = "follows"

    follow_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    follower_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id"), nullable=False, index=True
    )
    following_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id"), nullable=False, index=True
    )
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint("follower_id", "following_id", name="uq_follow_pair"),
        Index("ix_follows_following", "following_id"),
    )


class Review(Base):
    __tablename__ = "reviews"

    review_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.book_id"), nullable=False, index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    spoiler: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    helpful_votes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=_now, index=True)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint("user_id", "book_id", name="uq_review_user_book"),
        Index("ix_reviews_book_rating", "book_id", "rating"),
    )


class Bookshelf(Base):
    __tablename__ = "bookshelves"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    book_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    shelf: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=_now)

    __table_args__ = (UniqueConstraint("user_id", "book_id", name="uq_shelf_user_book"),)


class DiaryEntry(Base):
    __tablename__ = "diary_entries"

    entry_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    book_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    date_read: Mapped[str] = mapped_column(String(32), nullable=False, default="", index=True)
    rating_label: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    star_rating: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    diary_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    pages_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=_now)

    __table_args__ = (Index("ix_diary_user_date", "user_id", "date_read"),)


class WishlistSuggestion(Base):
    __tablename__ = "wishlist_suggestions"

    suggestion_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    author: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    isbn: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    upvotes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    downvotes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    comments: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    admin_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=_now, index=True)


class Series(Base):
    __tablename__ = "series"

    series_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    total_books: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=_now)


class Community(Base):
    __tablename__ = "communities"

    community_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    members: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    max_members: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=_now)


class ReadingChallenge(Base):
    __tablename__ = "reading_challenges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    goal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("user_id", "year", name="uq_challenge_user_year"),)


class GamificationState(Base):
    __tablename__ = "gamification"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    badges: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False, default=_now)


class AuthToken(Base):
    """One-time security tokens (password-reset, email-verify), DB-persisted.

    Replaces the AuthManager in-memory token dicts (lost on every restart;
    verify tokens never expired). Every row carries a purpose and an explicit
    expires_at so purge_expired_tokens() can reap stale rows. See auth.py.
    """

    __tablename__ = "auth_tokens"

    token: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(
        String(16), nullable=False, index=True
    )  # "reset" | "verify"
    expires_at: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=_now)


class AuditLog(Base):
    """Append-only admin audit trail.

    Records WHO changed WHAT admin configuration, WHEN, and FROM WHERE (IP +
    user agent), so admin-settings changes are attributable and searchable —
    turns "admin settings are broken" into "admin settings have a full audit
    trail" (portfolio-enhancement item). Rows are never updated or deleted by
    the app; new writes are plain INSERTs.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False, default="", index=True)
    target: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    old_value: Mapped[str] = mapped_column(Text, nullable=True, default=None)
    new_value: Mapped[str] = mapped_column(Text, nullable=True, default=None)
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    user_agent: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=_now, index=True)

    __table_args__ = (
        # Admin-dashboard filters: who did what, newest first.
        Index("ix_audit_admin_created", "admin_id", "created_at"),
        Index("ix_audit_action_created", "action", "created_at"),
    )
