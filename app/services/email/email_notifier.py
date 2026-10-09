"""
email_notifier.py - SMTP Email Notification System
Sends email alerts for overdue books, reservation availability, and fine notices.
Gracefully degrades if SMTP is not configured.
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

try:
    from app.config.settings import Config
except ImportError:
    # Fallback for standalone use
    class Config:
        SMTP_HOST = os.getenv("SMTP_HOST", "")
        SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
        SMTP_USER = os.getenv("SMTP_USER", "")
        SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
        SMTP_FROM = os.getenv("SMTP_FROM", "noreply@libraryms.com")
        SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "True").lower() == "true"
        LIBRARY_NAME = os.getenv("LIBRARY_NAME", "Library Management System")


def is_smtp_configured() -> bool:
    """Check if SMTP settings are configured."""
    return bool(Config.SMTP_HOST and Config.SMTP_USER and Config.SMTP_PASSWORD)


def send_email(to_email: str, subject: str, html_body: str, text_body: str | None = None) -> bool:
    """
    Send an email via SMTP. Returns True if sent successfully, False otherwise.
    Gracefully fails if SMTP is not configured.
    """
    if not is_smtp_configured():
        logger.warning("SMTP not configured — email skipped: to=%s subject=%s", to_email, subject)
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = Config.SMTP_FROM
        msg["To"] = to_email

        # Plain text fallback
        if text_body:
            msg.attach(MIMEText(text_body, "plain", "utf-8"))

        # HTML body
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=15) as server:
            if Config.SMTP_USE_TLS:
                server.starttls()
            server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
            server.send_message(msg)

        return True
    except (smtplib.SMTPException, ConnectionRefusedError, TimeoutError, OSError) as e:
        logger.error("Email send failed to %s: %s", to_email, e)
        return False


# ──


def _base_html(content: str) -> str:
    """Wrap content in a branded email template."""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
body{{font-family:'Segoe UI',Arial,sans-serif;margin:0;padding:0;background:#f4f4f5;color:#1f2937}}
.container{{max-width:560px;margin:20px auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08)}}
.header{{background:linear-gradient(135deg,#4f46e5,#7c3aed);padding:24px 32px;color:white}}
.header h1{{margin:0;font-size:1.3rem;font-weight:700}}
.body{{padding:24px 32px;line-height:1.6}}
.footer{{padding:16px 32px;background:#f9fafb;font-size:.8rem;color:#6b7280;text-align:center;border-top:1px solid #e5e7eb}}
.btn{{display:inline-block;padding:10px 24px;background:linear-gradient(135deg,#4f46e5,#7c3aed);color:white!important;text-decoration:none;border-radius:8px;font-weight:600;font-size:.9rem;margin:8px 0}}
.alert{{background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:12px 16px;margin:12px 0}}
.alert-danger{{border-left:4px solid #ef4444}}
.alert-success{{border-left:4px solid #10b981}}
.fine{{font-size:1.2rem;font-weight:700;color:#ef4444}}
table{{width:100%;border-collapse:collapse;margin:12px 0}}
th,td{{padding:8px 12px;text-align:left;border-bottom:1px solid #e5e7eb;font-size:.85rem}}
th{{background:#f5f3ff;color:#4f46e5}}
@media(max-width:480px){{.body,.header,.footer{{padding:16px}}}}
</style></head><body>
<div class="container"><div class="header"><h1>📚 {Config.LIBRARY_NAME}</h1></div>
<div class="body">{content}</div>
<div class="footer">
<p style="margin:0;">📚 {Config.LIBRARY_NAME} &bull; Automated Notification</p>
<p style="margin:4px 0 0;font-size:.75rem;">This is an automated message. Please do not reply directly.</p>
</div></div></body></html>"""


def _overdue_email_html(
    user_name: str,
    book_title: str,
    days_overdue: int,
    accrued_fine: float,
    due_date: str,
    book_id: str,
) -> str:
    """Generate HTML for an overdue book notification."""
    return _base_html(
        f"""
<h2 style="margin-top:0;">⏰ Book Overdue Notice</h2>
<p>Dear <strong>{user_name}</strong>,</p>
<p>This is a reminder that the following book is <strong>overdue</strong> and needs to be returned immediately.</p>

<div class="alert alert-danger">
<table><tr><td style="border:none;padding:4px 8px;"><strong>Book:</strong></td><td style="border:none;">{book_title}</td></tr>
<tr><td style="border:none;padding:4px 8px;"><strong>Due Date:</strong></td><td style="border:none;">{due_date}</td></tr>
<tr><td style="border:none;padding:4px 8px;"><strong>Days Overdue:</strong></td><td style="border:none;">{days_overdue} day{"s" if days_overdue != 1 else ""}</td></tr>
<tr><td style="border:none;padding:4px 8px;"><strong>Accrued Fine:</strong></td><td style="border:none;"><span class="fine">₹{accrued_fine:.2f}</span></td></tr></table>
</div>

<p><strong>What to do:</strong> Please return the book at your earliest convenience to avoid additional fines. The fine accrues at <strong>₹{Config.FINE_PER_DAY:.0f}/day</strong>.</p>
<p style="text-align:center;"><a href="#" class="btn">View My Account</a></p>
<p class="text-muted" style="font-size:.8rem;color:#6b7280;">Book ID: {book_id}</p>
"""
    )


def _reservation_email_html(user_name: str, book_title: str, book_id: str) -> str:
    """Generate HTML for a reservation available notification."""
    return _base_html(
        f"""
<h2 style="margin-top:0;">📢 Book Available for Pickup</h2>
<p>Dear <strong>{user_name}</strong>,</p>
<p>Great news! The book you reserved is now <strong>available</strong> for borrowing.</p>
<div class="alert alert-success">
<p style="margin:0;font-size:1.1rem;"><strong>{book_title}</strong></p>
<p style="margin:4px 0 0;color:#6b7280;">Book ID: {book_id}</p>
</div>
<p>Please visit the library to borrow this book. If not collected within <strong>3 days</strong>, the reservation may be offered to the next person in queue.</p>
<p style="text-align:center;"><a href="#" class="btn">View Book Details</a></p>
"""
    )


def _fine_email_html(user_name: str, fine_amount: float, book_title: str, reason: str) -> str:
    """Generate HTML for a fine notification."""
    return _base_html(
        f"""
<h2 style="margin-top:0;">💰 Fine Notice</h2>
<p>Dear <strong>{user_name}</strong>,</p>
<p>A fine has been applied to your account:</p>
<div class="alert alert-danger">
<table><tr><td style="border:none;padding:4px 8px;"><strong>Amount:</strong></td><td style="border:none;"><span class="fine">₹{fine_amount:.2f}</span></td></tr>
<tr><td style="border:none;padding:4px 8px;"><strong>Book:</strong></td><td style="border:none;">{book_title}</td></tr>
<tr><td style="border:none;padding:4px 8px;"><strong>Reason:</strong></td><td style="border:none;">{reason}</td></tr></table>
</div>
<p>Please clear your outstanding fines at the library counter or through your account portal.</p>
"""
    )


# ──


def notify_overdue(
    user_email: str,
    user_name: str,
    book_title: str,
    days_overdue: int,
    accrued_fine: float,
    due_date: str,
    book_id: str,
) -> bool:
    """Send an overdue book notification via email."""
    subject = f"⏰ Overdue Notice: '{book_title}' — {days_overdue} day(s) late"
    html = _overdue_email_html(user_name, book_title, days_overdue, accrued_fine, due_date, book_id)
    text = (
        f"Dear {user_name},\n\n"
        f"The book '{book_title}' is OVERDUE by {days_overdue} day(s).\n"
        f"Due date: {due_date}\n"
        f"Accrued fine: ₹{accrued_fine:.2f}\n\n"
        f"Please return the book immediately to avoid additional fines.\n"
        f"Fine rate: ₹{Config.FINE_PER_DAY:.0f}/day"
    )
    return send_email(user_email, subject, html, text)


def notify_reservation_available(
    user_email: str, user_name: str, book_title: str, book_id: str
) -> bool:
    """Send a reservation available notification via email."""
    subject = f"📢 Reservation Ready: '{book_title}' is now available"
    html = _reservation_email_html(user_name, book_title, book_id)
    text = (
        f"Dear {user_name},\n\n"
        f"The book '{book_title}' (ID: {book_id}) you reserved is now available!\n"
        f"Please collect it from the library within 3 days."
    )
    return send_email(user_email, subject, html, text)


def notify_fine(
    user_email: str,
    user_name: str,
    fine_amount: float,
    book_title: str,
    reason: str = "Late return",
) -> bool:
    """Send a fine notification via email."""
    subject = f"💰 Fine Notice: ₹{fine_amount:.2f} for '{book_title}'"
    html = _fine_email_html(user_name, fine_amount, book_title, reason)
    text = (
        f"Dear {user_name},\n\n"
        f"A fine of ₹{fine_amount:.2f} has been applied for '{book_title}'.\n"
        f"Reason: {reason}\n"
        f"Please clear your fines at the library counter."
    )
    return send_email(user_email, subject, html, text)


def send_overdue_batch(overdue_list: list[dict]) -> dict:
    """
    Send email notifications for all overdue books.
    Returns a summary dict with counts of sent/failed/skipped.
    """
    try:
        from app.db.storage_adapter import create_storage

        storage = create_storage()
        users = storage.load_users()
    except ImportError:
        return {
            "sent": 0,
            "failed": 0,
            "skipped": len(overdue_list),
            "total": len(overdue_list),
            "error": "Could not load storage",
        }

    sent = 0
    failed = 0
    skipped = 0
    results = []

    for overdue in overdue_list:
        user_id = overdue.get("user_id", "")
        user = users.get(user_id)
        if not user:
            skipped += 1
            results.append(
                {
                    "user_id": user_id,
                    "book": overdue.get("book", ""),
                    "status": "skipped",
                    "reason": "User not found",
                }
            )
            continue

        if not user.email:
            skipped += 1
            results.append(
                {
                    "user_id": user_id,
                    "book": overdue.get("book", ""),
                    "user_name": user.name,
                    "status": "skipped",
                    "reason": "No email on file",
                }
            )
            continue

        ok = notify_overdue(
            user_email=user.email,
            user_name=user.name,
            book_title=overdue.get("book", ""),
            days_overdue=overdue.get("days_overdue", 0),
            accrued_fine=overdue.get("accrued_fine", 0),
            due_date=overdue.get("due_date", ""),
            book_id=overdue.get("book_id", ""),
        )
        if ok:
            sent += 1
            results.append(
                {
                    "user_id": user_id,
                    "book": overdue.get("book", ""),
                    "user_name": user.name,
                    "status": "sent",
                }
            )
        else:
            failed += 1
            results.append(
                {
                    "user_id": user_id,
                    "book": overdue.get("book", ""),
                    "user_name": user.name,
                    "status": "failed",
                }
            )

    return {
        "sent": sent,
        "failed": failed,
        "skipped": skipped,
        "total": len(overdue_list),
        "results": results,
    }
