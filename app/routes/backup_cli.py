"""
backup_cli.py - Backup, Restore, and Activity Logs CLI.
"""

from app.core.logger import get_logs, log
from app.core.utils import (
    header,
    menu,
    pause,
    print_error,
    print_success,
    print_warning,
    confirm,
)
from app.services.auth.auth import AuthManager
from app.services.books.backup import create_backup, list_backups, restore_backup
import logging

logger = logging.getLogger(__name__)



def backup_restore_menu(auth: AuthManager) -> None:
    while True:
        choice = menu(
            "💾 BACKUP & RESTORE",
            ["Create Backup Now", "List Backups", "Restore Backup", "Back"],
        )
        if choice == "1":
            path = create_backup(triggered_by=auth.current_user.user_id)
            log("Manual backup created", auth.current_user.user_id, path)
            print_success(f"Backup saved to: {path}")
            pause()
        elif choice == "2":
            backups = list_backups()
            header("📂 AVAILABLE BACKUPS")
            if not backups:
                logger.info("  No backups found.")
            for i, b in enumerate(backups, 1):
                ts = b.get("timestamp", b["name"])
                by = b.get("triggered_by", "?")
                logger.info(f"  {i}. {ts}  (by: {by})")
            pause()
        elif choice == "3":
            backups = list_backups()
            if not backups:
                print_warning("No backups to restore.")
                pause()
                continue
            for i, b in enumerate(backups, 1):
                logger.info(f"  {i}. {b.get('timestamp', b['name'])}")
            try:
                idx = int(input("  Restore backup #: ").strip()) - 1
                bk = backups[idx]
            except (ValueError, IndexError):
                print_error("Invalid choice.")
                pause()
                continue
            if confirm(f"Restore '{bk['name']}'? Current data will be archived."):
                ok = restore_backup(bk["path"])
                if ok:
                    print_success("Restore successful.")
                else:
                    print_error("Restore failed.")
                log("Backup restored", auth.current_user.user_id, bk["name"])
            pause()
        elif choice == "4":
            break


def logs_menu() -> None:
    header("📜 ACTIVITY LOGS (Last 50 entries)")
    lines = get_logs(50)
    if not lines:
        logger.info("  No logs yet.")
    for line in lines:
        logger.info(f"  {line}")
    pause()
