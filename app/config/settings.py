"""
config.py - Centralized configuration with .env support
"""

import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration - all tunable constants in one place."""

    # ── Loan & Fine Settings ────────────────────────────────────
    ISSUE_DAYS: int = int(os.getenv("ISSUE_DAYS", "14"))
    FINE_PER_DAY: float = float(os.getenv("FINE_PER_DAY", "5.0"))
    MAX_BORROW_LIMIT: int = int(os.getenv("MAX_BORROW_LIMIT", "3"))
    MEMBERSHIP_VALIDITY_DAYS: int = int(os.getenv("MEMBERSHIP_VALIDITY_DAYS", "365"))

    # ── Data Directories ────────────────────────────────────────
    BASE_DIR: str = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    DATA_DIR: str = os.path.join(BASE_DIR, "data")
    LOGS_DIR: str = os.path.join(BASE_DIR, "logs")
    BACKUPS_DIR: str = os.path.join(BASE_DIR, "backups")
    UPLOADS_DIR: str = os.path.join(BASE_DIR, "uploads")

    # ── Upload Settings ─────────────────────────────────────────
    MAX_UPLOAD_SIZE: int = int(
        os.getenv("MAX_UPLOAD_SIZE", str(5 * 1024 * 1024))
    )  # 5 MB
    ALLOWED_EXTENSIONS: set = set(
        os.getenv("ALLOWED_EXTENSIONS", ".jpg,.jpeg,.png,.gif,.webp").split(",")
    )

    # ── JSON Data Files ─────────────────────────────────────────
    BOOKS_FILE: str = os.path.join(DATA_DIR, "books.json")
    USERS_FILE: str = os.path.join(DATA_DIR, "users.json")
    TRANSACTIONS_FILE: str = os.path.join(DATA_DIR, "transactions.json")
    RESERVATIONS_FILE: str = os.path.join(DATA_DIR, "reservations.json")
    FINES_FILE: str = os.path.join(DATA_DIR, "fines.json")
    NOTIFICATIONS_FILE: str = os.path.join(DATA_DIR, "notifications.json")

    # ── Logging ─────────────────────────────────────────────────
    LOG_FILE: str = os.path.join(LOGS_DIR, "activity.log")
    JSON_LOG: str = os.path.join(LOGS_DIR, "activity.json")

    # ── Default Admin ───────────────────────────────────────────
    DEFAULT_ADMIN_ID: str = os.getenv("DEFAULT_ADMIN_ID", "ADMIN001")
    # WARNING: DEFAULT_ADMIN_PASSWORD must be set via environment variable!
    # The fallback is a cryptographically random string that is printed at startup.
    # Never leave this unset in production.
    DEFAULT_ADMIN_PASSWORD: str = os.getenv("DEFAULT_ADMIN_PASSWORD", "")

    # ── Database ────────────────────────────────────────────────
    # Empty default -> SQLite at <DATA_DIR>/booktale.db (dev parity with the
    # JSON files). Set DATABASE_URL=postgresql://... in production; the schema
    # is identical via Alembic migrations.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # ── Redis ───────────────────────────────────────────────────
    # Shared backend for Flask-Limiter (rate-limit budgets survive restarts
    # and hold across multiple gunicorn workers), Socket.IO's message queue,
    # and RQ background jobs. The docker-compose stack already runs
    # redis:7-alpine and passes REDIS_URL to the app/worker services; this
    # is the default for local dev without the stack.
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # ── Background jobs (Phase 6: RQ + Redis) ───────────────────
    # RQ queue name; worker service consumes it (docker-compose runs
    # `python worker.py`, which starts the RQ worker + cron scheduler).
    RQ_QUEUE: str = os.getenv("RQ_QUEUE", "booktale")
    # When Redis is unreachable the jobs facade degrades to a bounded local
    # thread pool (never unbounded raw threads) so the app still works.
    BACKGROUND_JOBS_ENABLED: bool = (
        os.getenv("BACKGROUND_JOBS_ENABLED", "True").lower() == "true"
    )
    COVER_FETCH_WORKERS: int = int(os.getenv("COVER_FETCH_WORKERS", "4"))
    COVER_FETCH_TIMEOUT_SECONDS: int = int(
        os.getenv("COVER_FETCH_TIMEOUT_SECONDS", "120")
    )
    # Overdue-email batches send SMTP sequentially (15 s each) — a large batch
    # needs a much longer budget than a single cover fetch. 30 min default.
    EMAIL_BATCH_TIMEOUT_SECONDS: int = int(
        os.getenv("EMAIL_BATCH_TIMEOUT_SECONDS", "1800")
    )
    # Cron schedules for the scheduler thread in worker.py (croniter format).
    CRON_OVERDUE_EMAILS: str = os.getenv("CRON_OVERDUE_EMAILS", "0 9 * * *")
    CRON_TOKEN_PURGE: str = os.getenv("CRON_TOKEN_PURGE", "30 * * * *")

    # ── Web Server ──────────────────────────────────────────────
    # SECRET_KEY must be set via environment; the empty default makes boot-time
    # validation (validate_secure_config) fail fast instead of running with a
    # forgeable session key.
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    FLASK_HOST: str = os.getenv("FLASK_HOST", "0.0.0.0")  # nosec B104 - container/dev server default
    FLASK_PORT: int = int(os.getenv("FLASK_PORT", "5000"))
    FLASK_DEBUG: bool = os.getenv("FLASK_DEBUG", "False").lower() == "true"

    # ── OpenLibrary API ─────────────────────────────────────────
    OPENLIBRARY_BASE_URL: str = "https://openlibrary.org"

    # ── SMTP Email Settings ─────────────────────────────────────
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "noreply@libraryms.com")
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "True").lower() == "true"
    LIBRARY_NAME: str = os.getenv("LIBRARY_NAME", "Library Management System")

    EMAIL_NOTIFICATIONS_ENABLED: bool = (
        os.getenv("EMAIL_NOTIFICATIONS_ENABLED", "True").lower() == "true"
    )


# ── Settings Override File ───────────────────────────────────────────
# Load settings from settings_override.json (written by admin settings UI).
# This runs AFTER the class body so references to Config are valid
# (previously the class referenced itself mid-definition -> NameError).


def _load_settings_overrides() -> None:
    """Apply runtime overrides from data/settings_override.json, if present."""
    override_path = os.path.join(Config.DATA_DIR, "settings_override.json")
    if not os.path.exists(override_path):
        return
    try:
        import json as _json

        with open(override_path, "r", encoding="utf-8") as _f:
            _overrides = _json.load(_f)
        for _key, _val in _overrides.items():
            if not hasattr(Config, _key):
                continue
            _attr_type = type(getattr(Config, _key))
            if _attr_type == bool:
                setattr(Config, _key, str(_val).lower() == "true")
            elif _attr_type == int:
                try:
                    setattr(Config, _key, int(_val))
                except (TypeError, ValueError):
                    pass
            elif _attr_type == float:
                try:
                    setattr(Config, _key, float(_val))
                except (TypeError, ValueError):
                    pass
            elif _attr_type == set:
                if isinstance(_val, list):
                    setattr(Config, _key, set(_val))
                elif isinstance(_val, str):
                    setattr(Config, _key, set(_val.split(",")))
                else:
                    setattr(Config, _key, _val)
            else:
                setattr(Config, _key, _val)
    except Exception as _e:
        import sys as _sys

        print(
            "[Config] Warning: Could not load settings override:", _e, file=_sys.stderr
        )


# Known-insecure defaults that must never be used in any environment.
_INSECURE_SECRET_KEYS = {
    "",
    "change-this-secret-key-in-production",
    "change-this-to-a-random-secret-key-in-production",
}


def validate_secure_config() -> None:
    """Refuse to boot with known-insecure secret configuration.

    Raises RuntimeError if SECRET_KEY is unset or equal to a known default.
    Called at web-app startup so misconfiguration fails fast instead of
    shipping forgeable session cookies.
    """
    if Config.SECRET_KEY in _INSECURE_SECRET_KEYS:
        raise RuntimeError(
            "Refusing to start: SECRET_KEY is unset or set to a known-insecure default. "
            "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))' "
            "and set it in your environment / .env file."
        )


_load_settings_overrides()
