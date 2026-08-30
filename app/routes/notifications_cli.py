"""
notifications_cli.py - In-app and Email Notification CLI.
"""

from app.config.settings import Config
from app.core.logger import log
from app.core.utils import (
    confirm,
    format_date,
    header,
    menu,
    pause,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from app.services.books.library import Library
from app.services.notifications.notifications import NotificationManager
import logging

logger = logging.getLogger(__name__)



def show_notification_badge(notif_mgr: NotificationManager, user_id: str) -> None:
    """Show notification badge if there are unread notifications."""
    count = notif_mgr.get_unread_count(user_id)
    if count > 0:
        print_info(f"You have {count} unread notification{'s' if count > 1 else ''}!")


def notifications_menu(notif_mgr: NotificationManager, user_id: str) -> None:
    """View and manage in-app notifications."""
    while True:
        count = notif_mgr.get_unread_count(user_id)
        choice = menu(
            f"🔔 NOTIFICATIONS ({count} unread)",
            ["View All Notifications", "View Unread Only", "Mark All as Read", "Back"],
        )
        if choice == "1":
            _show_notifications(notif_mgr, user_id, unread_only=False)
        elif choice == "2":
            _show_notifications(notif_mgr, user_id, unread_only=True)
        elif choice == "3":
            notif_mgr.mark_all_read(user_id)
            print_success("All notifications marked as read.")
            pause()
        elif choice == "4":
            break


def _show_notifications(notif_mgr: NotificationManager, user_id: str, unread_only: bool) -> None:
    """Display notifications for a user."""
    notifs = notif_mgr.get_notifications(user_id, unread_only=unread_only)
    if not notifs:
        print_info("No notifications.")
        pause()
        return
    for n in notifs:
        read_status = "[bold]NEW[/bold]" if not n["read"] else "  "
        ts = format_date(n["created_at"])
        type_icons = {"overdue": "⏰", "reservation_available": "📢", "fine": "💰"}
        icon = type_icons.get(n["type"], "📌")
        logger.info(f"  {read_status} {icon} {n['message']}")
        logger.info(f"              {ts}")
        print()
    if not unread_only and confirm("Mark all as read?"):
        notif_mgr.mark_all_read(user_id)
        print_success("Marked as read.")
    pause()


def email_overdue_alerts(lib: Library) -> None:
    """Send email notifications for all overdue books."""
    try:
        from app.services.email.email_notifier import send_overdue_batch

        _EMAIL_ENABLED = True
    except ImportError:
        _EMAIL_ENABLED = False

    header("📧 SEND OVERDUE EMAIL ALERTS")
    if not _EMAIL_ENABLED:
        print_warning("❌ email_notifier module not available.")
        print_info(
            "   The email_notifier.py module is required. Make sure it exists in the project directory."
        )
        pause()
        return

    # Check SMTP config (Config already imported at top of file)
    if not Config.SMTP_HOST or not Config.SMTP_USER or not Config.SMTP_PASSWORD:
        print_warning("❌ SMTP is not configured.")
        print_info(
            "   Set SMTP_HOST, SMTP_USER, and SMTP_PASSWORD in your .env file or environment."
        )
        if not confirm("Continue anyway (shows what would be sent)?"):
            pause()
            return

    overdue = lib.get_overdue_list()
    if not overdue:
        print_success("🎉 No overdue books — nothing to send!")
        pause()
        return

    print_info(f"Found {len(overdue)} overdue book(s).")
    if confirm(f"Send email alerts for {len(overdue)} overdue book(s)?"):
        print_info("Sending email notifications...")
        result = send_overdue_batch(overdue)
        print()
        print_success(f"✅ Sent: {result['sent']}")
        if result["failed"] > 0:
            print_error(f"❌ Failed: {result['failed']}")
        if result["skipped"] > 0:
            print_warning(f"⏭️ Skipped: {result['skipped']} (no email on file or user not found)")
        print_info(f"📊 Total processed: {result['total']}")
        log(
            f"Overdue email alerts sent: {result['sent']} sent, {result['failed']} failed, {result['skipped']} skipped",
            "Admin",
        )
    else:
        print_info("Cancelled.")
    pause()
