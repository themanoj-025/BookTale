"""
notifications.py - In-app notification system
"""

from datetime import datetime

from app.storage.storage import Storage


class NotificationManager:
    """Manages in-app notifications for users."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def get_unread_count(self, user_id: str) -> int:
        """Get count of unread notifications for a user."""
        notifs = self.storage.load_notifications()
        return sum(1 for n in notifs if n["user_id"] == user_id and not n["read"])

    def get_notifications(self, user_id: str, unread_only: bool = False) -> list[dict]:
        """Get notifications for a user, newest first."""
        notifs = self.storage.load_notifications()
        user_notifs = [n for n in notifs if n["user_id"] == user_id]
        if unread_only:
            user_notifs = [n for n in user_notifs if not n["read"]]
        return sorted(user_notifs, key=lambda n: n["created_at"], reverse=True)

    def mark_as_read(self, notif_id: str) -> None:
        """Mark a single notification as read."""
        notifs = self.storage.load_notifications()
        for n in notifs:
            if n["notif_id"] == notif_id:
                n["read"] = True
                break
        self.storage.save_notifications(notifs)

    def mark_all_read(self, user_id: str) -> None:
        """Mark all notifications for a user as read."""
        notifs = self.storage.load_notifications()
        for n in notifs:
            if n["user_id"] == user_id:
                n["read"] = True
        self.storage.save_notifications(notifs)

    def add_notification(self, user_id: str, notif_type: str, message: str) -> str:
        """Add a new notification for a user."""
        notif_id = f"NOTIF-{int(datetime.now().timestamp())}-{user_id}"
        notif = {
            "notif_id": notif_id,
            "user_id": user_id,
            "type": notif_type,
            "message": message,
            "created_at": datetime.now().isoformat(),
            "read": False,
        }
        self.storage.append_notification(notif)
        return notif_id

    def notify_overdue(
        self, user_id: str, book_title: str, days: int, fine: float
    ) -> str:
        """Notify user about an overdue book."""
        return self.add_notification(
            user_id,
            "overdue",
            f"The book '{book_title}' is {days} day(s) overdue (Fine: ₹{fine:.2f})",
        )

    def notify_reservation_available(self, user_id: str, book_title: str) -> str:
        """Notify user a reserved book is now available."""
        return self.add_notification(
            user_id,
            "reservation_available",
            f"The book '{book_title}' you reserved is now available!",
        )
