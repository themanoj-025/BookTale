"""
auth.py - Authentication and session management
"""

import bcrypt

from app.core.exceptions import AuthenticationError
from app.models.user import User

# ─
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 15


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except (ValueError, AttributeError):
        return False


class AuthManager:
    """Handles user login/logout and session state."""

    def __init__(self, storage) -> None:
        self.storage = storage
        self.current_user: User | None = None

    def login(self, user_id: str, password: str) -> User | None:
        from datetime import datetime, timedelta

        users = self.storage.load_users()
        user = users.get(user_id)
        if not user:
            raise AuthenticationError()

        # ── Persistent rate limiting check ─────────────────────
        lock_until = getattr(user, "lock_until", None)
        if lock_until:
            try:
                lock_dt = datetime.fromisoformat(lock_until)
                if datetime.now() < lock_dt:
                    raise AuthenticationError()
            except (ValueError, TypeError):
                pass  # Malformed timestamp — treat as not locked

        # Reset lock if lockout period has expired
        if lock_until:
            try:
                lock_dt = datetime.fromisoformat(lock_until)
                if datetime.now() >= lock_dt:
                    user.failed_login_attempts = 0
                    user.lock_until = None
            except (ValueError, TypeError):
                pass

        if not verify_password(password, user.password_hash):
            # Track failed attempt
            failed = getattr(user, "failed_login_attempts", 0) + 1
            user.failed_login_attempts = failed
            if failed >= MAX_LOGIN_ATTEMPTS:
                lock_time = datetime.now() + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
                user.lock_until = lock_time.isoformat()
                self.storage.save_users(users)
            else:
                self.storage.save_users(users)
            raise AuthenticationError()

        # Successful login — reset attempts
        user.failed_login_attempts = 0
        user.lock_until = None

        # Auto-check membership expiry
        expiry = datetime.fromisoformat(user.membership_expiry)
        if datetime.now() > expiry and user.membership_status == "Active":
            user.membership_status = "Expired"
            self.storage.save_users(users)
        self.current_user = user
        return user

    def logout(self) -> None:
        self.current_user = None

    def is_logged_in(self) -> bool:
        return self.current_user is not None

    def require_role(self, *roles: str) -> bool:
        if not self.current_user:
            return False
        return self.current_user.role in roles


import secrets as _secrets
from datetime import datetime, timedelta

# ── DB-backed one-time tokens (Phase 4 P1 fix) ─────────────────────────────
# Reset/verify tokens used to live in class-level in-memory dicts on
# AuthManager: lost on every restart (users stranded with a valid-but-dead
# link after a deploy) and verify tokens never expired. They now persist in
# the auth_tokens table with an explicit purpose + expires_at, so they
# survive process restarts, expire (15 min reset / 24 h verify), and stale
# rows are reaped opportunistically on every token mint (_store_token) and
# in bulk by purge_expired_tokens().
# NOTE: tokens require the DB backend (the app default since Phase 2). In
# the legacy STORAGE_BACKEND=json fallback the table does not exist, so
# token generation raises inside the caller's try/except and the feature
# degrades gracefully (no silent data corruption).
RESET_TOKEN_TTL_MINUTES = 15
VERIFY_TOKEN_TTL_HOURS = 24


def _now_iso() -> str:
    return datetime.now().isoformat()


def _store_token(token: str, user_id: str, purpose: str, ttl: timedelta) -> None:
    from sqlalchemy import delete as _sa_delete

    from app.db.database import session_scope
    from app.db.models import AuthToken

    with session_scope() as db:
        db.add(
            AuthToken(
                token=token,
                user_id=user_id,
                purpose=purpose,
                expires_at=(datetime.now() + ttl).isoformat(),
                created_at=_now_iso(),
            )
        )
        # Opportunistic reap: every token mint also removes already-expired
        # rows (expires_at is indexed; mints are rare). Keeps the table
        # bounded without a separate scheduled job; purge_expired_tokens()
        # remains the public batch API for the future RQ worker.
        db.execute(_sa_delete(AuthToken).where(AuthToken.expires_at < _now_iso()))


def _find_token(token: str, purpose: str):
    """Look up a live token row, or None (does NOT consume).

    Expired / malformed rows are deleted here (same session, committed on
    clean exit) — tokens are garbage-collected on first touch after expiry.
    NOTE: relies on the session factory's expire_on_commit=False — the row is
    read after its session closes, so attributes must stay loaded.
    """
    from sqlalchemy import select

    from app.db.database import session_scope
    from app.db.models import AuthToken

    with session_scope() as db:
        row = db.scalar(
            select(AuthToken).where(AuthToken.token == token, AuthToken.purpose == purpose)
        )
        if row is None:
            return None
        try:
            expired = datetime.fromisoformat(row.expires_at) < datetime.now()
        except (ValueError, TypeError):
            expired = True  # malformed expiry -> treat as invalid, delete
        if expired:
            db.delete(row)
            return None
        return row


def _consume_token(token: str, purpose: str) -> str | None:
    """Atomically verify-and-consume a one-time token (no TOCTOU).

    The expiry-checked read and the DELETE run inside a single transaction;
    the DELETE's rowcount decides the winner. If a concurrent consumer
    already removed the row, this DELETE deletes 0 rows and returns None —
    exactly one caller ever receives the uid, even on Postgres READ COMMITTED
    where two readers could otherwise both see the row.
    """
    from sqlalchemy import delete as _sa_delete
    from sqlalchemy import select

    from app.db.database import session_scope
    from app.db.models import AuthToken

    with session_scope() as db:
        row = db.scalar(
            select(AuthToken).where(AuthToken.token == token, AuthToken.purpose == purpose)
        )
        if row is None:
            return None
        try:
            expired = datetime.fromisoformat(row.expires_at) < datetime.now()
        except (ValueError, TypeError):
            expired = True  # malformed expiry -> treat as invalid
        if expired:
            db.execute(_sa_delete(AuthToken).where(AuthToken.token == token))
            return None
        uid = row.user_id
        result = db.execute(_sa_delete(AuthToken).where(AuthToken.token == token))
        return uid if result.rowcount else None


def generate_reset_token(user_id: str) -> str:
    "Generate a password reset token and return it (DB-backed, 15 min TTL)."
    token = _secrets.token_urlsafe(32)
    _store_token(token, user_id, "reset", timedelta(minutes=RESET_TOKEN_TTL_MINUTES))
    return token


def verify_reset_token(token: str) -> str | None:
    "Verify a reset token and return the user_id if valid (not consumed)."
    row = _find_token(token, "reset")
    return row.user_id if row else None


def consume_reset_token(token: str) -> str | None:
    "Verify and consume a reset token (single-use, atomic)."
    return _consume_token(token, "reset")


def generate_verify_token(user_id: str) -> str:
    "Generate an email verification token (DB-backed, 24 h TTL)."
    token = _secrets.token_urlsafe(32)
    _store_token(token, user_id, "verify", timedelta(hours=VERIFY_TOKEN_TTL_HOURS))
    return token


def verify_email_token(token: str) -> str | None:
    "Verify an email token and return the user_id if valid (not consumed)."
    row = _find_token(token, "verify")
    return row.user_id if row else None


def consume_verify_token(token: str) -> str | None:
    "Verify and consume an email verification token (single-use, atomic)."
    return _consume_token(token, "verify")


def purge_expired_tokens() -> int:
    "Delete every expired token row; return the number removed."
    from sqlalchemy import delete as _sa_delete

    from app.db.database import session_scope
    from app.db.models import AuthToken

    with session_scope() as db:
        result = db.execute(_sa_delete(AuthToken).where(AuthToken.expires_at < _now_iso()))
        return result.rowcount or 0
