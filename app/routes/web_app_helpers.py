"""Helper functions for web_app.py — avatar, initials, colors."""

from __future__ import annotations

import html
import zlib


def _initials(name: str) -> str:
    parts = name.strip().split()
    if not parts:
        return "?"
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return parts[0][:2].upper()


def _avatar_color(name) -> dict:
    colors = [
        "#4f46e5", "#059669", "#d97706", "#dc2626",
        "#0891b2", "#7c3aed", "#db2777", "#ca8a04",
    ]
    return colors[zlib.crc32(str(name).encode("utf-8")) % len(colors)]


def _avatar_html(name: str, size: int = 32) -> str:
    i = _initials(name)
    c = _avatar_color(name)
    return (
        f'<div class="avatar" style="width:{size}px;height:{size}px;background:{c}20;color:{c};'
        f'font-size:{size // 2}px;font-weight:700;border-radius:50%;display:inline-flex;'
        f'align-items:center;justify-content:center;flex-shrink:0;" title="{html.escape(name)}">{html.escape(i)}</div>'
    )


CAT_COLORS = {
    "Fiction": "#4f46e5", "Non-Fiction": "#059669", "Science": "#0891b2",
    "Technology": "#7c3aed", "History": "#d97706", "Philosophy": "#be185d",
    "Art": "#db2777", "Biography": "#ca8a04", "Children": "#16a34a",
    "Comics": "#e11d48", "Poetry": "#9333ea", "Drama": "#ea580c",
    "Education": "#2563eb", "Reference": "#64748b", "Religion": "#78716c",
    "Self-Help": "#0d9488", "Cooking": "#f97316", "Travel": "#0ea5e9",
    "Music": "#8b5cf6", "Sports": "#22c55e", "Other": "#6b7280",
}


def cat_color(c: str) -> str:
    return CAT_COLORS.get(c, CAT_COLORS["Other"])





# ════════════════════════════════════════════════════════════════════════════
# Error handlers
# ════════════════════════════════════════════════════════════════════════════

_ERROR_PAGES = {
    400: ("400", "Bad Request", "⚠️", "The request could not be understood. Check the submitted data and try again."),
    401: ("401", "Unauthorized", "🔒", "You need to sign in to access this page."),
    403: ("403", "Forbidden", "⛔", "You don't have permission to access this resource."),
    404: ("404", "Page Not Found", "🔍", "The page you're looking for doesn't exist or was moved."),
    405: ("405", "Method Not Allowed", "🚫", "This URL doesn't accept that request method."),
    409: ("409", "Conflict", "⚔️", "The request conflicts with the current state of the resource."),
    413: ("413", "Request Too Large", "📦", "The uploaded file or request is too large."),
    415: ("415", "Unsupported Media Type", "🧩", "The request payload is in an unsupported format."),
    422: ("422", "Unprocessable Entity", "📋", "The request was well-formed but could not be processed."),
    429: ("429", "Too Many Requests", "🐌", "You've made too many requests. Please slow down and try again shortly."),
    500: ("500", "Server Error", "🛠️", "Something went wrong on our end. Please try again later."),
}


