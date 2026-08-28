"""
feature_shared.py - Shared state, helpers, dashboard widgets, and HTML templates
for feature routes. Extracted from feature_routes.py for focused maintenance.
"""

import html
import json
import zlib
from datetime import datetime

from flask import session

from app.services.reading.diary import (
    RATING_LABELS,
    RATING_SCORES,
    rating_badge_html,
    star_rating_html,
)

# ── Module-level shared state (populated by init_feature_routes) ──

_series = None
_challenge = None
_progress = None
_wishlist = None
_storage = None
_lib = None
_notif_mgr = None
_diary = None
_h = None
_avatar_html = None


def init_shared_state(
    app, storage, lib, auth, notif_mgr, series, challenge, progress, wishlist, diary
) -> None:
    """Populate module-level globals from init_feature_routes."""
    global _series, _challenge, _progress, _wishlist, _storage, _lib, _notif_mgr
    global _diary, _h, _avatar_html
    _storage = storage
    _lib = lib
    _notif_mgr = notif_mgr
    _series = series
    _challenge = challenge
    _progress = progress
    _wishlist = wishlist
    _diary = diary

    def h(text) -> str:
        return html.escape(str(text))

    def _js_str(value) -> str:
        return str(value).replace("\\", "\\\\").replace("'", "\\'").replace('"', "&quot;")

    def _initials(name) -> str:
        parts = name.strip().split()
        if not parts:
            return "?"
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return parts[0][:2].upper()

    def _avatar_color(name) -> str:
        colors = [
            "#4f46e5", "#059669", "#d97706", "#dc2626",
            "#0891b2", "#7c3aed", "#db2777", "#ca8a04",
        ]
        return colors[zlib.crc32(str(name).encode("utf-8")) % len(colors)]

    def avatar_html(name, size=32) -> str:
        i = _initials(name)
        c = _avatar_color(name)
        return f'<div class="avatar" style="width:{size}px;height:{size}px;background:{c}20;color:{c};font-size:{size // 2}px;font-weight:700;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;" title="{h(name)}">{h(i)}</div>'

    _h = h
    _avatar_html = avatar_html


# ── Helpers ──


def h(text) -> str:
    """HTML-escape helper."""
    return html.escape(str(text))


def _js_str(value) -> str:
    """Escape a value for a single-quoted JS string inside a double-quoted
    HTML attribute (onclick="...").
    """
    return str(value).replace("\\", "\\\\").replace("'", "\\'").replace('"', "&quot;")


def cat_color(c) -> str:
    """Category color lookup."""
    colors = {
        "Fiction": "#4f46e5", "Non-Fiction": "#059669", "Science": "#0891b2",
        "Technology": "#7c3aed", "History": "#d97706", "Philosophy": "#be185d",
        "Art": "#db2777", "Biography": "#ca8a04", "Children": "#16a34a",
        "Comics": "#e11d48", "Poetry": "#9333ea", "Drama": "#ea580c",
        "Education": "#2563eb", "Reference": "#64748b", "Religion": "#78716c",
        "Self-Help": "#0d9488", "Cooking": "#f97316", "Travel": "#0ea5e9",
        "Music": "#8b5cf6", "Sports": "#22c55e", "Other": "#6b7280",
    }
    return colors.get(c, colors["Other"])


# ── Dashboard widget HTML ──


def get_dashboard_widgets_html(user_id) -> str:
    """Get HTML snippets for dashboard widgets."""
    out = ""

    # Reading Challenge widget
    year = datetime.now().year
    goal = _challenge.get_goal(user_id, year)
    if goal.get("goal", 0) > 0:
        pct = goal.get("percentage", 0)
        out += f"""
        <div class="col-md-6 mb-3 animate-d4">
            <div class="glass-card p-3" onclick="window.location.href='/reading-challenge'" style="cursor:pointer;">
                <div class="section-title"><i class="bi bi-trophy-fill text-warning"></i> {year} Reading Goal</div>
                <div class="d-flex justify-content-between align-items-center">
                    <div><span class="fw-bold" style="font-size:1.3rem;">{goal.get("progress", 0)}</span><small class="text-muted">/{goal.get("goal", 0)} books</small></div>
                    <div class="text-end"><span class="fw-bold" style="font-size:1.3rem;color:var(--primary);">{pct}%</span></div>
                </div>
                <div class="progress-thin mt-2" style="height:8px;border-radius:4px;">
                    <div class="bar" style="width:{pct}%;background:{"var(--success)" if pct >= 100 else "var(--primary)"};height:8px;border-radius:4px;"></div>
                </div>
                <div class="d-flex justify-content-between mt-1"><small class="text-muted">📈 {goal.get("pace", 0)}/mo</small><small class="text-muted">⏱️ {goal.get("days_remaining", 0)}d left</small></div>
            </div>
        </div>"""

    # Currently Reading widget
    rl = _progress.get_user_reading_list(user_id)
    reading = rl.get("currently_reading", [])
    if reading:
        books_html = ""
        for b in reading[:3]:
            cc = cat_color(b.get("book_category", ""))
            pct = b.get("percentage", 0)
            books_html += f"""
            <div class="d-flex align-items-center gap-2 mb-2">
                <div style="width:32px;height:32px;border-radius:8px;background:{cc}20;display:flex;align-items:center;justify-content:center;flex-shrink:0;"><i class="bi bi-book-fill" style="color:{cc};"></i></div>
                <div class="flex-grow-1" style="min-width:0;"><span class="fw-bold small">{h(b.get("book_title", ""))[:30]}</span>
                    <div class="progress-thin mt-1"><div class="bar" style="width:{pct}%;background:var(--primary);"></div></div></div>
                <a href="/reading-progress/{h(b["book_id"])}" class="btn btn-sm btn-outline"><i class="bi bi-arrow-right"></i></a>
            </div>"""
        out += f"""
        <div class="col-md-6 mb-3 animate-d4">
            <div class="glass-card p-3" onclick="window.location.href='/reading-progress'" style="cursor:pointer;">
                <div class="section-title"><i class="bi bi-bookmark-check-fill text-primary"></i> Currently Reading ({len(reading)})</div>
                {books_html}
                {f'<small class="text-muted">+{len(reading) - 3} more</small>' if len(reading) > 3 else ""}
            </div>
        </div>"""

    return out
