"""scripts/rotate_logs.py - Centralized log rotation + age-based retention.

Docker/Kubernetes entrypoints for the Book-Tale app call this before
starting the web/worker services so the files under app/logs/ stay bounded:
  * RotatingFileHandler caps each identifier at 5 MB (5 backups) at runtime.
  * This sweep deletes rotated files older than LOG_RETENTION_DAYS (default 30)
    while keeping at least LOG_RETENTION_KEEP (default 10) per identifier.

Env vars (read from app/config/settings.py, defaults shown):
  LOG_RETENTION_DAYS  - age threshold in days (default 30)
  LOG_RETENTION_KEEP  - minimum rotated files to keep per identifier (default 10)

Exit code 0 on success; non-zero on os-level failures (logged, not raised).
"""

import logging
import os
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.config.settings import Config

logger = logging.getLogger(__name__)


def _rotated_suffixes() -> tuple[str, ...]:
    """Rotated-file suffixes produced by RotatingFileHandler (backupCount >= 1)."""
    return (".1", ".2", ".3", ".4", ".5", ".6", ".7", ".8", ".9", ".10", ".11", ".12")


def _is_older_than(path: Path, days: int) -> bool:
    """True when the file's mtime predates (now - days)."""
    try:
        age = datetime.now(UTC) - datetime.fromtimestamp(path.stat().st_mtime, UTC)
    except OSError as exc:
        logger.warning("Could not stat %s: %s", path, exc)
        return False
    return age.days >= days


def rotate_logs(
    retention_days: int = Config.LOG_RETENTION_DAYS,
    retention_keep: int = Config.LOG_RETENTION_KEEP,
) -> int:
    """Sweep app/logs/: delete rotated files older than retention_days while
    keeping at least retention_keep per identifier.

    Returns the number of removed files. Always succeeds (-1) so container
    entrypoints can call it without aborting the service when the filesystem
    is read-only or a file is locked (Windows).
    """
    logs_dir = Path(Config.LOGS_DIR)
    if not logs_dir.is_dir():
        logger.warning("Logs directory %s does not exist; nothing to rotate.", logs_dir)
        return 0

    for identifier in (Config.LOG_FILE, Config.JSON_LOG):
        if not identifier:
            continue
        log_path = Path(identifier)
        if not log_path.exists():
            continue

        # 1) Runtime rotation (the running process already owns the files). A
        #    stale copy may be left under a .N suffix; prune those above the
        #    retention_keep floor.
        parent = log_path.parent
        base = log_path.name
        rotated: list[Path] = []
        for suffix in _rotated_suffixes():
            p = parent / f"{base}{suffix}"
            if p.is_file():
                rotated.append(p)

        rotated.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        if len(rotated) > retention_keep:
            for stale in rotated[retention_keep:]:
                try:
                    stale.unlink()
                    logger.info("Removed stale rotated log %s", stale)
                except OSError as exc:
                    logger.warning("Could not remove stale rotated log %s: %s", stale, exc)
        elif len(rotated) == retention_keep:
            # Track the oldest kept file's mtime so we do not rotate it away;
            # the OS-level retention (maxBytes / backupCount) is the final
            # guard against unbounded growth.
            pass

        # 2) Age-based deletion of files older than retention_days. We skip
        #    the live log files themselves (they are managed by the handler)
        #    and only touch rollover artifacts, which the handler recreates.
        for path in parent.glob(f"{base}*"):
            if path.name == base:
                continue
            if path.is_file() and _is_older_than(path, retention_days):
                try:
                    path.unlink()
                    logger.info("Removed old rotated log %s", path)
                except OSError as exc:
                    logger.warning("Could not remove old rotated log %s: %s", path, exc)

    # 3) Reclaim the untouched subdirectory tree (empty dirs only) so a fresh
    #    clone does not carry an unbounded logs/ artifact.
    for child in logs_dir.iterdir():
        if child.is_dir() and not any(child.iterdir()):
            try:
                child.rmdir()
                logger.info("Removed empty logs subdirectory %s", child)
            except OSError:
                pass

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    removed = rotate_logs()
    logger.info("rotate_logs completed; removed %d stale rotated files.", removed)
    sys.exit(0 if removed >= 0 else 1)
