"""
user.py - User model and management
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

from app.config.settings import Config

ROLES: list[str] = ["admin", "librarian", "user"]
MAX_BORROW_LIMIT: int = Config.MAX_BORROW_LIMIT
MEMBERSHIP_VALIDITY_DAYS: int = Config.MEMBERSHIP_VALIDITY_DAYS


@dataclass
class User:
    user_id: str  # Student ID / Member ID
    name: str
    email: str
    phone: str
    role: str  # admin | librarian | user
    password_hash: str
    membership_status: str = "Active"  # Active | Blocked | Expired
    membership_expiry: str = field(
        default_factory=lambda: (
            datetime.now() + timedelta(days=MEMBERSHIP_VALIDITY_DAYS)
        ).isoformat()
    )
    books_issued: list[str] = field(
        default_factory=list
    )  # list of book_ids currently issued
    unpaid_fine: float = 0.0
    registered_on: str = field(default_factory=lambda: datetime.now().isoformat())
    # ── Social profile fields ──
    bio: str = ""
    profile_picture: str = ""  # base64 data URI or URL
    website: str = ""
    location: str = ""
    email_verified: bool = False
    favorite_genres: list[str] = field(default_factory=list)
    favorite_books: list[str] = field(default_factory=list)  # list of book_ids, max 4
    # ── Security / Rate Limiting fields ──
    failed_login_attempts: int = 0
    lock_until: str | None = None
    # ── Settings fields ──
    theme: str = "light"  # light | dark | system
    font_size: str = "medium"  # small | medium | large
    email_notifications: bool = True
    push_notifications: bool = True
    notify_on_comment: bool = True
    notify_on_like: bool = True
    notify_on_follow: bool = True
    notify_on_issue_return: bool = True
    notify_on_overdue: bool = True
    notify_on_due_reminder: bool = True
    privacy_show_activity: bool = True
    privacy_show_wishlist: bool = True
    privacy_show_bookmarks: bool = True
    privacy_profile_visibility: str = "public"  # public | members | private
    privacy_show_email: bool = False
    reading_default_rating: str = "worth_it"  # perfection | worth_it | timepass | skip
    reading_goal_type: str = "books"  # books | pages
    reading_default_goal: int = 12

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "User":
        # Handle missing new fields gracefully
        if "bio" not in data:
            data["bio"] = ""
        if "profile_picture" not in data:
            data["profile_picture"] = ""
        if "website" not in data:
            data["website"] = ""
        if "location" not in data:
            data["location"] = ""
        if "favorite_genres" not in data:
            data["favorite_genres"] = []
        if "favorite_books" not in data:
            data["favorite_books"] = []
        if "theme" not in data:
            data["theme"] = "light"
        if "font_size" not in data:
            data["font_size"] = "medium"
        if "email_notifications" not in data:
            data["email_notifications"] = True
        if "push_notifications" not in data:
            data["push_notifications"] = True
        if "notify_on_comment" not in data:
            data["notify_on_comment"] = True
        if "notify_on_like" not in data:
            data["notify_on_like"] = True
        if "notify_on_follow" not in data:
            data["notify_on_follow"] = True
        if "notify_on_issue_return" not in data:
            data["notify_on_issue_return"] = True
        if "notify_on_overdue" not in data:
            data["notify_on_overdue"] = True
        if "notify_on_due_reminder" not in data:
            data["notify_on_due_reminder"] = True
        if "privacy_show_activity" not in data:
            data["privacy_show_activity"] = True
        if "privacy_show_wishlist" not in data:
            data["privacy_show_wishlist"] = True
        if "privacy_show_bookmarks" not in data:
            data["privacy_show_bookmarks"] = True
        if "privacy_profile_visibility" not in data:
            data["privacy_profile_visibility"] = "public"
        if "privacy_show_email" not in data:
            data["privacy_show_email"] = False
        if "reading_default_rating" not in data:
            data["reading_default_rating"] = "worth_it"
        if "reading_goal_type" not in data:
            data["reading_goal_type"] = "books"
        if "reading_default_goal" not in data:
            data["reading_default_goal"] = 12
        if "failed_login_attempts" not in data:
            data["failed_login_attempts"] = 0
        if "lock_until" not in data:
            data["lock_until"] = None
        return cls(**data)

    def is_active(self) -> bool:
        if self.membership_status == "Blocked":
            return False
        expiry = datetime.fromisoformat(self.membership_expiry)
        if datetime.now() > expiry:
            self.membership_status = "Expired"
            return False
        return True

    def can_borrow(self) -> bool:
        return self.is_active() and len(self.books_issued) < MAX_BORROW_LIMIT

    def display(self) -> str:
        expiry = datetime.fromisoformat(self.membership_expiry).strftime("%Y-%m-%d")
        return (
            f"  ID         : {self.user_id}\n"
            f"  Name       : {self.name}\n"
            f"  Email      : {self.email}\n"
            f"  Phone      : {self.phone}\n"
            f"  Role       : {self.role.upper()}\n"
            f"  Status     : {self.membership_status}\n"
            f"  Expiry     : {expiry}\n"
            f"  Books Out  : {len(self.books_issued)}/{MAX_BORROW_LIMIT}\n"
            f"  Unpaid Fine: ₹{self.unpaid_fine:.2f}"
        )
