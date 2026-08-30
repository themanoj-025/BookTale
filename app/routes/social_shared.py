"""
social_shared.py - Shared state, helpers, and utilities for social routes.
Extracted from social_routes.py to support the split into focused modules.
"""

import html
import io
import zlib
from datetime import datetime, timedelta
from functools import wraps

from flask import redirect, session, url_for


# ── Module-level shared state (populated by init_social_routes) ──

storage = None
lib = None
auth = None
social = None
review_mgr = None
recommender = None
notif_mgr = None
book_lists = None
communities = None
gamification = None


def init_shared_state(
    _storage,
    _lib,
    _auth,
    _social,
    _review_mgr,
    _recommender,
    _notif_mgr,
    _book_lists=None,
    _communities=None,
    _gamification=None,
) -> None:
    """Populate module-level globals from init_social_routes."""
    global storage, lib, auth, social, review_mgr, recommender, notif_mgr
    global book_lists, communities, gamification
    storage = _storage
    lib = _lib
    auth = _auth
    social = _social
    review_mgr = _review_mgr
    recommender = _recommender
    notif_mgr = _notif_mgr
    book_lists = _book_lists
    communities = _communities
    gamification = _gamification


# ── Image verification (Phase 4 P1 upload hardening) ──


def _verify_and_reencode_image(file) -> tuple[bool, bytes | None, str]:
    """Verify image content; return (ok, reencoded_bytes, dot_extension).

    Phase 4 (P1) upload hardening: extension-only checks let an attacker
    rename HTML/JS to .png. We verify the actual bytes with Pillow
    (Image.open().verify() + decode) and re-encode server-side, stripping any
    embedded payload (EXIF, trailing HTML/JS). GIF/WEBP are re-encoded as
    static PNG — the guaranteed-safe path (animation is a fair trade for
    never storing attacker-controlled bytes). Falls back to a pure-Python
    magic-byte signature check (no re-encode) when Pillow is unavailable.
    """
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        return _magic_signature_ok(file), None, None

    try:
        with Image.open(file) as im:
            im.verify()  # raises UnidentifiedImageError for non-images
        file.seek(0)
        with Image.open(file) as im:
            im.load()  # decode pixels; raises on truncated/corrupt files
            fmt = (im.format or "PNG").upper()
            if fmt not in ("JPEG", "PNG"):
                fmt = "PNG"
            if fmt == "JPEG" and im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            buf = io.BytesIO()
            im.save(buf, format=fmt)
        file.seek(0)
        return True, buf.getvalue(), "." + fmt.lower()
    except (UnidentifiedImageError, OSError, ValueError):
        return False, None, None


def _magic_signature_ok(file) -> bool:
    """Pure-Python fallback: reject files whose leading bytes aren't an image.

    Still blocks renamed HTML/JS/text files (the P1 attack) without Pillow;
    it just cannot strip payloads embedded inside a genuinely valid image.
    """
    head = file.read(16)
    file.seek(0)
    if (
        head.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a"))
    ):
        return True
    return head[:4] == b"RIFF" and head[8:12] == b"WEBP"


# ── Template rendering helpers ──


def render_page(title, content, **kw) -> str:
    from flask import render_template

    user = get_current_user()
    return render_template(
        "base.html",
        title=title,
        content=content,
        session=session,
        notif_count=notif_mgr.get_unread_count(user.user_id) if user else 0,
        **kw,
    )


def get_current_user() -> dict:
    if "user_id" not in session:
        return None
    return storage.load_users().get(session["user_id"])


def login_required(f) -> None:
    @wraps(f)
    def d(*a, **k) -> dict:
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        return f(*a, **k)

    return d


def avatar_html(name, size=32) -> str:
    parts = name.strip().split()
    if not parts:
        initials = "?"
    elif len(parts) >= 2:
        initials = (parts[0][0] + parts[-1][0]).upper()
    else:
        initials = parts[0][:2].upper()
    from app.routes.helpers import h

    colors = [
        "#4f46e5",
        "#059669",
        "#d97706",
        "#dc2626",
        "#0891b2",
        "#7c3aed",
        "#db2777",
        "#ca8a04",
    ]
    c = colors[zlib.crc32(str(name).encode("utf-8")) % len(colors)]
    return (
        '<div class="avatar" style="width:%dpx;height:%dpx;background:%s20;color:%s;font-size:%dpx;font-weight:700;border-radius:50%%;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;" title="%s">%s</div>'
        % (size, size, c, c, size // 2, h(name), h(initials))
    )


def time_ago(iso_str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str)
        now = datetime.now()
        diff = now - dt
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return "just now"
        minutes = seconds // 60
        if minutes < 60:
            return "%dm ago" % minutes
        hours = minutes // 60
        if hours < 24:
            return "%dh ago" % hours
        days = hours // 24
        if days < 7:
            return "%dd ago" % days
        weeks = days // 7
        if weeks < 4:
            return "%dw ago" % weeks
        months = days // 30
        if months < 12:
            return "%dmo ago" % months
        years = days // 365
        return "%dy ago" % years
    except (ValueError, TypeError, OverflowError):
        return iso_str[:10]


def cat_color(c) -> str:
    colors = {
        "Fiction": "#4f46e5",
        "Non-Fiction": "#059669",
        "Science": "#0891b2",
        "Technology": "#7c3aed",
        "History": "#d97706",
        "Philosophy": "#be185d",
        "Art": "#db2777",
        "Biography": "#ca8a04",
        "Children": "#16a34a",
        "Comics": "#e11d48",
        "Poetry": "#9333ea",
        "Drama": "#ea580c",
        "Education": "#2563eb",
        "Reference": "#64748b",
        "Religion": "#78716c",
        "Self-Help": "#0d9488",
        "Cooking": "#f97316",
        "Travel": "#0ea5e9",
        "Music": "#8b5cf6",
        "Sports": "#22c55e",
        "Other": "#6b7280",
    }
    return colors.get(c, colors["Other"])


# ── SVG / grid renderers (used by profile page) ──


def _render_heatmap_svg(heatmap_data: list, total: int) -> str:
    """Render a GitHub-style reading heatmap."""
    from datetime import date

    today = date.today()
    hm = {}
    for item in heatmap_data:
        hm[item["date"]] = item["count"]
    start = today - timedelta(days=364)
    start = start - timedelta(days=start.weekday() + 1 if start.weekday() < 6 else 0)
    cell_size, cell_gap = 12, 2
    cw, rh = cell_size + cell_gap, cell_size + cell_gap
    svg_w, svg_h = 52 * cw + 30, 7 * rh + 20
    intensity_colors = {
        0: "#1a1a22",
        1: "rgba(124,106,247,0.15)",
        2: "rgba(124,106,247,0.35)",
        3: "rgba(124,106,247,0.55)",
        4: "rgba(124,106,247,0.75)",
    }
    cells = []
    current = start
    for week in range(52):
        for day in range(7):
            ds = current.isoformat()
            count = hm.get(ds, 0)
            intensity = min(count, 4)
            color = intensity_colors[intensity]
            x = week * cw + 15
            y = day * rh + 15
            t = "%s - %d entries" % (ds, count) if count else ds
            cells.append(
                '<rect x="%d" y="%d" width="%d" height="%d" rx="2" fill="%s"><title>%s</title></rect>'
                % (x, y, cell_size, cell_size, color, t)
            )
            current += timedelta(days=1)
            if current > today:
                break
        if current > today:
            break
    ml, dl, months = (
        "",
        "",
        [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ],
    )
    cur_m = start
    for i in range(52):
        if cur_m.month != (cur_m - timedelta(weeks=1)).month or i == 0:
            ml += '<text x="%d" y="12" font-size="8" fill="var(--bt-text-muted)">%s</text>' % (
                i * cw + 15,
                months[cur_m.month - 1],
            )
        cur_m += timedelta(weeks=1)
    for i, dlbl in enumerate(["", "Mon", "", "Wed", "", "Fri", ""]):
        dl += '<text x="2" y="%d" font-size="7" fill="var(--bt-text-muted)">%s</text>' % (
            i * rh + 17,
            dlbl,
        )
    lg = ""
    lcs = [
        "#1a1a22",
        "rgba(124,106,247,0.15)",
        "rgba(124,106,247,0.35)",
        "rgba(124,106,247,0.55)",
        "rgba(124,106,247,0.75)",
    ]
    lx = svg_w - 130
    lg += '<text x="%d" y="%d" font-size="7" fill="var(--bt-text-muted)">Less</text>' % (
        lx - 25,
        svg_h - 5,
    )
    for li, lc in enumerate(lcs):
        xx = lx + li * (cell_size + 2)
        lg += '<rect x="%d" y="%d" width="%d" height="%d" rx="2" fill="%s"></rect>' % (
            xx,
            svg_h - cell_size - 8,
            cell_size,
            cell_size,
            lc,
        )
    lg += '<text x="%d" y="%d" font-size="7" fill="var(--bt-text-muted)">More</text>' % (
        lx + 5 * (cell_size + 2) + 2,
        svg_h - 5,
    )
    svg = (
        '<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" style="width:100%%;max-width:700px;height:auto;"><g>%s%s%s%s</g></svg>'
        % (svg_w, svg_h, ml, dl, "".join(cells), lg)
    )
    return svg


def _render_fav_grid(fav_books: list, is_own: bool) -> str:
    """Render favorite 4 books grid."""

    _esc = html.escape
    books_data = storage.load_books()
    favs = []
    for bid in fav_books:
        b = books_data.get(bid)
        if b and not b.is_deleted:
            favs.append(b)
    drag_attrs = (
        'draggable="true" ondragstart="onFavDragStart(event)" ondrop="onFavDrop(event)" ondragover="onFavDragOver(event)"'
        if is_own
        else ""
    )
    drop_attrs = 'ondrop="onFavDrop(event)" ondragover="onFavDragOver(event)"' if is_own else ""
    h_out = '<div class="bt-fav-grid" id="favGrid">'
    for idx in range(4):
        if idx < len(favs):
            b = favs[idx]
            cc = cat_color(b.category)
            if b.cover_url:
                cover = f'<img src="{_esc(b.cover_url)}" alt="{_esc(b.title)}" class="bt-cover-img" loading="lazy">'
            else:
                cover = (
                    f'<div class="bt-cover-placeholder" style="background:linear-gradient(135deg,{cc},{cc}dd);font-size:1.2rem;">{_esc(b.title[:2].upper())}</div>'
                )
            rm = (
                '<button class="bt-fav-remove" onclick="removeFav(\'{}\')" aria-label="Remove {}">&times;</button>'.format(b.book_id.replace("'", "\\'").replace('"', "&quot;"), _esc(b.title))
                if is_own
                else ""
            )
            h_out += (
                '<div class="bt-fav-slot" data-id="%s" data-index="%d" %s>'
                '<div class="bt-fav-rank">%d</div>'
                '<a href="/books/%s" class="bt-fav-link">%s</a>'
                "%s"
                "</div>"
            ) % (b.book_id, idx, drag_attrs, idx + 1, b.book_id, cover, rm)
        else:
            h_out += (
                '<div class="bt-fav-slot bt-fav-slot-empty" data-id="" data-index="%d" %s onclick="openFavSearch()">'
                '<div class="bt-fav-empty-icon"><i class="bi bi-plus-lg"></i></div>'
                '<div class="bt-fav-empty-label">Search to add</div>'
                "</div>"
            ) % (idx, drop_attrs)
    h_out += "</div>"
    return h_out


def _render_badges_grid(badges: list) -> str:
    _esc = html.escape
    h_out = '<div class="bt-badges-grid">'
    for badge in badges:
        unlocked = badge.get("unlocked", False)
        cls = "bt-badge-item" if unlocked else "bt-badge-item bt-badge-locked"
        icon = badge.get("icon", "award")
        name = badge.get("name", "")
        desc = badge.get("desc", "")
        h_out += (
            f'<div class="{cls}" title="{_esc(desc)}">'
            f'<div class="bt-badge-icon"><i class="bi bi-{_esc(icon)}-fill"></i></div>'
            f'<div class="bt-badge-name">{_esc(name)}</div>'
            "</div>"
        )
    h_out += "</div>"
    return h_out


def _render_diary_entries(entries: list) -> str:
    if not entries:
        return '<div class="text-center text-muted small py-3">No diary entries yet.</div>'
    _esc = html.escape
    h_out = ""
    for e in entries:
        dt = e.get("date_read", "")[:10]
        bt = e.get("book_title", "Unknown")
        dtxt = e.get("diary_text", "")
        rbadge = e.get("rating_badge", "")
        cov = e.get("book_cover", "")
        cov_html = (
            f'<img src="{_esc(cov)}" alt="" class="bt-diary-cover" loading="lazy">'
            if cov
            else f'<div class="bt-diary-cover bt-diary-cover-placeholder">{_esc(bt[:2].upper())}</div>'
        )
        tp = _esc(dtxt[:120]) + "..." if len(dtxt) > 120 else _esc(dtxt)
        h_out += (
            '<div class="bt-diary-entry">'
            f"{cov_html}"
            '<div class="bt-diary-body">'
            f'<div class="bt-diary-date">{dt}</div>'
            f'<a href="/diary" class="bt-diary-book-title">{_esc(bt)}</a>'
            f'<div class="bt-diary-meta">{rbadge}</div>'
            f'<div class="bt-diary-text">{tp}</div>'
            "</div></div>"
        )
    return h_out
