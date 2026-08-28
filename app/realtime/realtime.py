"""
realtime.py - Real-time WebSocket events for the Book Social Media Platform

Uses Flask-SocketIO to provide:
- Live feed updates (new posts appear instantly)
- Real-time notifications (likes, follows, comments)
- Live comment updates
- Typing indicators
- Read receipts
- Online status
"""

from datetime import datetime

from flask import request, session
from flask_socketio import SocketIO, emit, join_room, leave_room

from app.core.logger import log
from app.storage.storage import Storage

# Global socketio instance (initialized in web_app.py)
socketio: SocketIO | None = None


class RealtimeManager:
    """Manages real-time events and connections."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.online_users: dict[str, str] = {}  # user_id -> sid
        self.user_rooms: dict[str, set[str]] = {}  # user_id -> set of rooms
        self.post_viewers: dict[str, set[str]] = {}  # post_id -> set of user_ids viewing comments
        self.post_typing: dict[str, dict[str, float]] = {}  # post_id -> {user_id: timestamp}

    def user_connected(self, user_id: str, sid: str) -> None:
        """Track online users."""
        self.online_users[user_id] = sid
        log(f"User online: {user_id}", user_id)

    def user_disconnected(self, user_id: str) -> None:
        """Remove offline users."""
        if user_id in self.online_users:
            del self.online_users[user_id]
        # Clean up post viewers
        for pid in list(self.post_viewers.keys()):
            self.post_viewers[pid].discard(user_id)
            if not self.post_viewers[pid]:
                del self.post_viewers[pid]
        # Clean up post typing
        for pid in list(self.post_typing.keys()):
            self.post_typing[pid].pop(user_id, None)
            if not self.post_typing[pid]:
                del self.post_typing[pid]
        if user_id in self.user_rooms:
            del self.user_rooms[user_id]

    def is_online(self, user_id: str) -> bool:
        return user_id in self.online_users

    def get_online_count(self) -> int:
        return len(self.online_users)

    # ── Post Viewers (Read Receipts) ────────────────────────────

    def viewer_joined(self, post_id: str, user_id: str) -> list[str]:
        """Track that a user is viewing comments on a post. Returns list of current viewers."""
        if post_id not in self.post_viewers:
            self.post_viewers[post_id] = set()
        self.post_viewers[post_id].add(user_id)
        users = self.storage.load_users()
        viewer_list = []
        for vid in self.post_viewers[post_id]:
            u = users.get(vid)
            if u:
                viewer_list.append(
                    {
                        "user_id": vid,
                        "user_name": u.name,
                        "is_online": vid in self.online_users,
                    }
                )
            else:
                viewer_list.append({"user_id": vid, "user_name": vid, "is_online": False})
        return viewer_list

    def viewer_left(self, post_id: str, user_id: str) -> list[dict]:
        """Remove user from post viewers."""
        if post_id in self.post_viewers:
            self.post_viewers[post_id].discard(user_id)
            if not self.post_viewers[post_id]:
                del self.post_viewers[post_id]
        return self.get_viewer_list(post_id)

    def get_viewer_list(self, post_id: str) -> list[dict]:
        """Get list of users viewing a post's comments."""
        if post_id not in self.post_viewers:
            return []
        users = self.storage.load_users()
        viewer_list = []
        for vid in list(self.post_viewers[post_id]):
            u = users.get(vid)
            if u:
                viewer_list.append(
                    {
                        "user_id": vid,
                        "user_name": u.name,
                        "is_online": vid in self.online_users,
                    }
                )
        return viewer_list

    # ── Event Emitters ──────────────────────────────────────────

    def emit_new_post(self, post: dict) -> None:
        """Broadcast new post to followers."""
        if not socketio:
            return
        socketio.emit("new_post", post, namespace="/social")

    def emit_new_comment(self, post_id: str, comment: dict) -> None:
        """Emit new comment to post viewers."""
        if not socketio:
            return
        socketio.emit(
            "new_comment",
            {"post_id": post_id, "comment": comment},
            namespace="/social",
            room=post_id,
        )

    def emit_like_update(
        self, post_id: str, liked_by: str, is_liked: bool, likes_count: int
    ) -> None:
        """Emit like update to post viewers."""
        if not socketio:
            return
        socketio.emit(
            "like_update",
            {
                "post_id": post_id,
                "liked_by": liked_by,
                "is_liked": is_liked,
                "likes_count": likes_count,
            },
            namespace="/social",
            room=post_id,
        )

    def emit_notification(self, user_id: str, notification: dict) -> None:
        """Send real-time notification to a specific user."""
        if not socketio:
            return
        sid = self.online_users.get(user_id)
        if sid:
            socketio.emit("notification", notification, namespace="/social", to=sid)

    def emit_follow_update(self, follower_id: str, following_id: str, is_following: bool) -> None:
        """Emit follow update to both users."""
        if not socketio:
            return
        socketio.emit(
            "follow_update",
            {
                "follower_id": follower_id,
                "following_id": following_id,
                "is_following": is_following,
            },
            namespace="/social",
        )

    def emit_post_deleted(self, post_id: str) -> None:
        """Notify clients that a post was deleted."""
        if not socketio:
            return
        socketio.emit("post_deleted", {"post_id": post_id}, namespace="/social")


# Global instance
realtime_manager: RealtimeManager | None = None


def init_socketio(app, storage: Storage) -> None:
    """Initialize SocketIO with the Flask app."""
    global socketio, realtime_manager

    socketio = SocketIO(
        app,
        cors_allowed_origins=["http://localhost:5000", "http://127.0.0.1:5000"],
        async_mode="threading",
    )
    realtime_manager = RealtimeManager(storage)

    @socketio.on("connect", namespace="/social")
    def handle_connect() -> dict:
        user_id = session.get("user_id")
        if not user_id:
            return False  # Reject connection
        sid = request.sid
        realtime_manager.user_connected(user_id, sid)
        emit(
            "connected",
            {"user_id": user_id, "online_count": realtime_manager.get_online_count()},
        )
        emit("user_online", {"user_id": user_id}, broadcast=True, include_self=False)

    @socketio.on("disconnect", namespace="/social")
    def handle_disconnect() -> None:
        user_id = session.get("user_id")
        if user_id:
            realtime_manager.user_disconnected(user_id)
            emit("user_offline", {"user_id": user_id}, broadcast=True, include_self=False)

    @socketio.on("join_post", namespace="/social")
    def handle_join_post(data) -> None:
        """Join a post's room to receive live updates."""
        post_id = data.get("post_id")
        if post_id:
            join_room(post_id)
            user_id = session.get("user_id", "?")
            log(f"Joined post room: {post_id}", user_id)

    @socketio.on("leave_post", namespace="/social")
    def handle_leave_post(data) -> None:
        """Leave a post's room."""
        post_id = data.get("post_id")
        if post_id:
            leave_room(post_id)
            user_id = session.get("user_id", "?")
            # Also leave as viewer
            viewers = realtime_manager.viewer_left(post_id, user_id)
            emit(
                "read_receipt_update",
                {"post_id": post_id, "viewers": viewers},
                room=post_id,
                include_self=False,
            )

    @socketio.on("typing", namespace="/social")
    def handle_typing(data) -> None:
        """Broadcast typing indicator to post room."""
        post_id = data.get("post_id")
        user_id = session.get("user_id", "?")
        users = realtime_manager.storage.load_users()
        user = users.get(user_id)
        is_typing = data.get("is_typing", True)
        # Track typing state per post
        if is_typing:
            if post_id not in realtime_manager.post_typing:
                realtime_manager.post_typing[post_id] = {}
            realtime_manager.post_typing[post_id][user_id] = datetime.now().timestamp()
        else:
            if post_id in realtime_manager.post_typing:
                realtime_manager.post_typing[post_id].pop(user_id, None)
                if not realtime_manager.post_typing[post_id]:
                    del realtime_manager.post_typing[post_id]
        emit(
            "user_typing",
            {
                "post_id": post_id,
                "user_id": user_id,
                "user_name": user.name if user else "Someone",
                "is_typing": is_typing,
            },
            room=post_id,
            include_self=False,
        )

    @socketio.on("view_comments", namespace="/social")
    def handle_view_comments(data) -> None:
        """Track that a user is viewing comments (for read receipts)."""
        post_id = data.get("post_id")
        user_id = session.get("user_id")
        if post_id and user_id:
            viewers = realtime_manager.viewer_joined(post_id, user_id)
            emit(
                "read_receipt_update",
                {"post_id": post_id, "viewers": viewers},
                room=post_id,
                include_self=False,
            )
            # Send current viewers to the joining user
            emit(
                "read_receipt_update",
                {
                    "post_id": post_id,
                    "viewers": realtime_manager.get_viewer_list(post_id),
                },
            )

    return socketio


def get_socketio() -> None:
    """Get the socketio instance."""
    return socketio


def get_realtime() -> dict:
    """Get the realtime manager instance."""
    return realtime_manager
