"""
backup.py - Backup and restore system
"""

import json
import os
import shutil
from datetime import datetime
from typing import Any

from app.config.settings import Config


def create_backup(triggered_by: str = "manual") -> str:
    """Backup all data files to a timestamped folder."""
    os.makedirs(Config.BACKUPS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(Config.BACKUPS_DIR, f"backup_{ts}")
    if os.path.exists(Config.DATA_DIR):
        shutil.copytree(Config.DATA_DIR, dest)
    # Save metadata
    meta: dict[str, Any] = {"timestamp": ts, "triggered_by": triggered_by, "path": dest}
    meta_file = os.path.join(dest, "_meta.json")
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return dest


def list_backups() -> list[dict[str, Any]]:
    """List all available backups."""
    if not os.path.exists(Config.BACKUPS_DIR):
        return []
    entries: list[dict[str, Any]] = []
    for name in sorted(os.listdir(Config.BACKUPS_DIR), reverse=True):
        full = os.path.join(Config.BACKUPS_DIR, name)
        if os.path.isdir(full):
            meta_file = os.path.join(full, "_meta.json")
            meta: dict[str, Any] = {}
            if os.path.exists(meta_file):
                with open(meta_file, encoding="utf-8") as f:
                    meta = json.load(f)
            entries.append({"name": name, "path": full, **meta})
    return entries


def restore_backup(backup_path: str) -> bool:
    """Restore a backup to the data directory."""
    if not os.path.exists(backup_path):
        return False
    if os.path.exists(Config.DATA_DIR):
        # Archive current data before restoring
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.move(Config.DATA_DIR, os.path.join(Config.BACKUPS_DIR, f"pre_restore_{ts}"))
    shutil.copytree(backup_path, Config.DATA_DIR, ignore=shutil.ignore_patterns("_meta.json"))
    return True
