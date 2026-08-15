"""
logger.py - Structured logging with rotation (Phase 7).

Replaces the legacy per-call JSON-rewrite logger (which read and rewrote the
entire log file on every log() call — unbounded growth, no lock, race on
concurrent writes).

Uses Python's built-in logging module with RotatingFileHandler so log files
are automatically rotated at 5 MB with 5 backups, and each line is a single
atomic append — safe for concurrent access.
"""

# ── Module-level setup ──────────────────────────────────────────────────────
import contextvars as _cv
import json
import logging
import os
import sys
import threading
import uuid
from datetime import datetime
from logging.handlers import RotatingFileHandler

from app.config.settings import Config

_logger: logging.Logger | None = None
_logger_lock = threading.RLock()  # guards _logger/_log_file_path reconfiguration
_request_id_ctx: _cv.ContextVar[str] = _cv.ContextVar("_request_id", default="")
_log_file_path: str = getattr(Config, "LOG_FILE", "")  # track for reconfiguration


def _get_logger() -> logging.Logger:
    """Return (and lazily initialise) the application logger.

    Reconfigures file handlers when Config.LOG_FILE / Config.JSON_LOG change
    (e.g. the test fixtures that redirect logs to a temp dir). Closes old
    file handles before reconfiguration so Windows doesn't leak locked files.
    """
    with _logger_lock:
        return _get_logger_locked()


def _get_logger_locked() -> logging.Logger:
    """Actual init/reconfigure logic — must be called under _logger_lock."""
    global _logger, _log_file_path

    current_log = getattr(Config, "LOG_FILE", "")
    current_json = getattr(Config, "JSON_LOG", "")

    # Reconfigure if paths changed (test fixtures redirect Config.LOG_FILE)
    if _logger is not None and current_log and current_log != _log_file_path:
        for h in list(_logger.handlers):
            h.close()
        _logger.handlers.clear()
        _logger = None

    if _logger is not None:
        return _logger

    _logger = logging.getLogger("booktale")
    _logger.setLevel(logging.DEBUG)
    _logger.propagate = False

    # Never trust pre-existing handlers on the registry singleton: they may
    # point at a stale path (e.g. a background worker configured them while
    # Config pointed elsewhere, or a previous test reset the module global
    # without clearing the registry). Drop them and rebuild for the current
    # Config so every record lands in the file get_logs() will read.
    if _logger.handlers:
        for h in list(_logger.handlers):
            h.close()
        _logger.handlers.clear()

    os.makedirs(getattr(Config, "LOGS_DIR", "."), exist_ok=True)
    # Ensure the parent dir of each log file exists even when LOG_FILE /
    # JSON_LOG live outside LOGS_DIR (e.g. the relative "logs/activity.log"
    # default while tests redirect LOGS_DIR to a temp dir).
    for _p in (current_log, current_json):
        if _p:
            os.makedirs(os.path.dirname(_p) or ".", exist_ok=True)

    # ── Text handler (human-readable) ───────────────────────────────────
    text_handler = RotatingFileHandler(
        current_log,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    text_handler.setLevel(logging.INFO)
    text_handler.setFormatter(
        logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    # Force flush after each emit so get_logs() reads current data immediately.
    _orig_emit = text_handler.emit

    def _flushing_emit(record):
        _orig_emit(record)
        text_handler.flush()

    text_handler.emit = _flushing_emit
    _logger.addHandler(text_handler)

    # ── JSON handler (machine-readable) ──────────────────────────────────
    json_handler = RotatingFileHandler(
        current_json,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    json_handler.setLevel(logging.DEBUG)
    json_handler.setFormatter(_JsonFormatter())
    _logger.addHandler(json_handler)

    # ── Console handler (dev convenience) ────────────────────────────────
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.DEBUG if getattr(Config, "FLASK_DEBUG", False) else logging.INFO)
    console.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-5s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    _logger.addHandler(console)

    _log_file_path = current_log
    return _logger


def reset_logger() -> None:
    """Close file handlers and reset the logger (test teardown helper).

    Only closes file-based handlers (RotatingFileHandler) so Windows doesn't
    hold file locks during shutil.rmtree. Console/stderr handlers are left
    alone because pytest owns those streams via its capture machinery.
    """
    with _logger_lock:
        _reset_logger_locked()


def _reset_logger_locked() -> None:
    """Actual reset logic — must be called under _logger_lock."""
    global _logger, _log_file_path
    if _logger:
        for h in list(_logger.handlers):
            try:
                # Only close file-based handlers, not console/stderr.
                if (
                    hasattr(h, "baseFilename")
                    and hasattr(h, "stream")
                    and h.stream
                    and not h.stream.closed
                ):
                    h.stream.close()
                h.close()
            except Exception:
                pass
        _logger.handlers.clear()
    _logger = None
    _log_file_path = getattr(Config, "LOG_FILE", "")


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }
        # Attach request_id if set (set by web middleware)
        req_id = _request_id_ctx.get("")
        if req_id:
            entry["request_id"] = req_id
        # Carry extra fields injected via log(..., extra=...)
        for key in ("actor", "action", "extra", "user_id", "book_id"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val
        return json.dumps(entry, default=str, ensure_ascii=False)


# ── Public API (backward-compatible with the old logger.py) ─────────────────


def log(
    action: str,
    actor: str = "System",
    extra: str = "",
    user_id: str = "",
    book_id: str = "",
) -> None:
    """Log an action — backward-compatible with the legacy call signature.

    Extra structured fields (user_id, book_id) are attached when provided.
    """
    logger = _get_logger()
    message = f"[{actor}] {action}"
    if extra:
        message += f" | {extra}"
    logger.info(
        message,
        extra={
            "actor": actor,
            "action": action,
            "extra": extra,
            "user_id": user_id,
            "book_id": book_id,
        },
    )


def get_logs(limit: int = 50) -> list[str]:
    """Get the last N log lines from the text log file."""
    if not os.path.exists(Config.LOG_FILE):
        return []
    with open(Config.LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return [line.strip() for line in lines[-limit:]]


def set_request_id(request_id: str | None = None) -> str:
    """Set or clear the current request ID (called by web middleware).

    Uses contextvars so each thread/async task gets its own request ID.
    """
    rid = request_id or uuid.uuid4().hex[:12]
    _request_id_ctx.set(rid)
    return rid
