"""
social_routes.py - Social Platform Routes & Pages
Integrates with the existing Flask web_app.py by registering routes on the app.
Uses .replace() for Python variables instead of f-strings to avoid JS template literal conflicts.
"""

import html
import io
import json
import os
import uuid
import zlib
from datetime import datetime, timedelta
from functools import wraps

from flask import g, jsonify, redirect, request, session, url_for

from app.config.settings import Config
from app.core.logger import log
from app.realtime.realtime import get_realtime

# BASE_HTML/FOOTER_HTML imported lazily in render_page

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


def h(text):
    return html.escape(str(text))


def _verify_and_reencode_image(file):
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
        head.startswith(b"\x89PNG\r\n\x1a\n")
        or head.startswith(b"\xff\xd8\xff")
        or head.startswith(b"GIF87a")
        or head.startswith(b"GIF89a")
    ):
        return True
    return head[:4] == b"RIFF" and head[8:12] == b"WEBP"


def render_page(title, content, **kw):
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


def get_current_user():
    if "user_id" not in session:
        return None
    return storage.load_users().get(session["user_id"])


def login_required(f):
    @wraps(f)
    def d(*a, **k):
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        return f(*a, **k)

    return d


def avatar_html(name, size=32):
    parts = name.strip().split()
    if not parts:
        initials = "?"
    elif len(parts) >= 2:
        initials = (parts[0][0] + parts[-1][0]).upper()
    else:
        initials = parts[0][:2].upper()
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


def time_ago(iso_str):
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
    except:
        return iso_str[:10]


def cat_color(c):
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
            ml += (
                '<text x="%d" y="12" font-size="8" fill="var(--bt-text-muted)">%s</text>'
                % (i * cw + 15, months[cur_m.month - 1])
            )
        cur_m += timedelta(weeks=1)
    for i, dlbl in enumerate(["", "Mon", "", "Wed", "", "Fri", ""]):
        dl += (
            '<text x="2" y="%d" font-size="7" fill="var(--bt-text-muted)">%s</text>'
            % (i * rh + 17, dlbl)
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
    lg += (
        '<text x="%d" y="%d" font-size="7" fill="var(--bt-text-muted)">Less</text>'
        % (lx - 25, svg_h - 5)
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
    lg += (
        '<text x="%d" y="%d" font-size="7" fill="var(--bt-text-muted)">More</text>'
        % (lx + 5 * (cell_size + 2) + 2, svg_h - 5)
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
    drop_attrs = (
        'ondrop="onFavDrop(event)" ondragover="onFavDragOver(event)"' if is_own else ""
    )
    h_out = '<div class="bt-fav-grid" id="favGrid">'
    for idx in range(4):
        if idx < len(favs):
            b = favs[idx]
            cc = cat_color(b.category)
            if b.cover_url:
                cover = (
                    '<img src="%s" alt="%s" class="bt-cover-img" loading="lazy">'
                    % (_esc(b.cover_url), _esc(b.title))
                )
            else:
                cover = (
                    '<div class="bt-cover-placeholder" style="background:linear-gradient(135deg,%s,%sdd);font-size:1.2rem;">%s</div>'
                    % (cc, cc, _esc(b.title[:2].upper()))
                )
            # NOTE: % binds tighter than +. The whole onclick+label must be ONE
            # format string (was split literals -> only last literal formatted ->
            # 'not all arguments converted' TypeError at runtime).
            rm = (
                '<button class="bt-fav-remove" onclick="removeFav(\'%s\')" aria-label="Remove %s">&times;</button>'
                % (b.book_id.replace("'", "\\'").replace('"', "&quot;"), _esc(b.title))
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
            '<div class="%s" title="%s">'
            '<div class="bt-badge-icon"><i class="bi bi-%s-fill"></i></div>'
            '<div class="bt-badge-name">%s</div>'
            "</div>"
        ) % (cls, _esc(desc), _esc(icon), _esc(name))
    h_out += "</div>"
    return h_out


def _render_diary_entries(entries: list) -> str:
    if not entries:
        return (
            '<div class="text-center text-muted small py-3">No diary entries yet.</div>'
        )
    _esc = html.escape
    h_out = ""
    for e in entries:
        dt = e.get("date_read", "")[:10]
        bt = e.get("book_title", "Unknown")
        dtxt = e.get("diary_text", "")
        rbadge = e.get("rating_badge", "")
        cov = e.get("book_cover", "")
        cov_html = (
            '<img src="%s" alt="" class="bt-diary-cover" loading="lazy">' % _esc(cov)
            if cov
            else '<div class="bt-diary-cover bt-diary-cover-placeholder">%s</div>'
            % _esc(bt[:2].upper())
        )
        tp = _esc(dtxt[:120]) + "..." if len(dtxt) > 120 else _esc(dtxt)
        h_out += (
            '<div class="bt-diary-entry">'
            "%s"
            '<div class="bt-diary-body">'
            '<div class="bt-diary-date">%s</div>'
            '<a href="/diary" class="bt-diary-book-title">%s</a>'
            '<div class="bt-diary-meta">%s</div>'
            '<div class="bt-diary-text">%s</div>'
            "</div></div>"
        ) % (cov_html, dt, _esc(bt), rbadge, tp)
    return h_out


def init_social_routes(
    app,
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
):
    global \
        storage, \
        lib, \
        auth, \
        social, \
        review_mgr, \
        recommender, \
        notif_mgr, \
        book_lists, \
        communities, \
        gamification
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

    def _rate_limit(limit_value, **kwargs):
        """Rate-limit decorator; no-op fallback if flask-limiter is missing.

        Reads the single limiter instance that web_app exposes as
        app.extensions["booktale_limiter"] (flask-limiter 4.x stores itself
        in app.extensions["limiter"] as a SET, or not at all when
        RATELIMIT_ENABLED=0, so we must not depend on that key). This module
        needs no import from web_app, avoiding a circular import.
        """
        _lim = app.extensions.get("booktale_limiter")
        if _lim is None:
            return lambda f: f
        return _lim.limit(limit_value, **kwargs)

    # ═══ API ENDPOINTS ═══

    @app.route("/api/feed")
    @login_required
    def api_feed():
        uid = session["user_id"]
        page = max(1, int(request.args.get("page", 1)))
        tab = request.args.get("tab", "following")
        if tab == "trending":
            posts, total = social.get_trending_feed(uid, page=page)
        elif tab == "discover":
            posts, total = social.get_discover_feed(uid, page=page)
        else:
            posts, total = social.get_feed(uid, page=page)
        return jsonify({"posts": posts, "total": total, "page": page})

    @app.route("/api/posts", methods=["POST"])
    @login_required
    # Abuse ceiling: posts are shared-surface content (feed spam vector).
    @_rate_limit("30 per minute")
    def api_create_post():
        uid = session["user_id"]
        data = request.get_json() or {}
        content = data.get("content", "").strip()
        if not content:
            return jsonify({"success": False, "error": "Post content cannot be empty"})
        ptype = data.get("type", "post")
        bids = data.get("book_ids", [])
        imgs = data.get("image_urls", [])
        post = social.create_post(
            uid, content, post_type=ptype, book_ids=bids, image_urls=imgs
        )
        rt = get_realtime()
        if rt:
            users = storage.load_users()
            author = users.get(uid)
            enriched = dict(
                post,
                author_name=author.name if author else "Unknown",
                author_avatar=avatar_html(author.name, 36) if author else "?",
                is_liked=False,
                likes_count=0,
                books=[],
                time_ago="just now",
            )
            rt.emit_new_post(enriched)
        try:
            if gamification:
                gamification.on_post_created(uid)
        # Optional sub-feature: degrade gracefully, never break the request.
        except Exception:  # nosec B110
            pass
        return jsonify({"success": True, "post": post})

    @app.route("/api/upload", methods=["POST"])
    @login_required
    # Defense in depth: uploads write files to disk and are a storage/malware
    # abuse vector — cap them per IP well below the global 200/min default.
    @_rate_limit("10 per minute")
    def api_upload():
        uid = session["user_id"]
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file provided"})
        file = request.files["file"]
        if not file.filename:
            return jsonify({"success": False, "error": "No file selected"})
        utype = request.form.get("type", "post")
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in Config.ALLOWED_EXTENSIONS:
            return jsonify({"success": False, "error": "File type not allowed"})
        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(0)
        if size > Config.MAX_UPLOAD_SIZE:
            return jsonify({"success": False, "error": "File too large. Max 5MB."})

        # Phase 4 (P1): verify content + re-encode server-side, so a file
        # renamed from HTML/JS to .png is rejected and even genuine images
        # with embedded payloads are stripped before touching disk.
        ok, data, out_ext = _verify_and_reencode_image(file)
        if not ok:
            log(
                "Upload rejected (not a valid image): %s (%s)" % (file.filename, utype),
                uid,
            )
            return jsonify({"success": False, "error": "File is not a valid image"})
        if out_ext is None:
            out_ext = ext  # Pillow-less fallback: keep the validated extension
        safe_name = "%s_%s%s" % (uid, uuid.uuid4().hex[:12], out_ext)
        subdir = "avatars" if utype == "avatar" else "post_images"
        save_dir = os.path.join(Config.UPLOADS_DIR, subdir)
        os.makedirs(save_dir, exist_ok=True)
        dest_path = os.path.join(save_dir, safe_name)
        if data is None:
            file.save(dest_path)
        else:
            with open(dest_path, "wb") as f:
                f.write(data)
        url_path = "/uploads/%s/%s" % (subdir, safe_name)
        log("Uploaded %s (%s, %s)" % (url_path, utype, file.filename), uid)
        return jsonify({"success": True, "url": url_path, "filename": safe_name})

    @app.route("/uploads/<path:filename>")
    def serve_upload(filename):
        from flask import send_from_directory

        full_path = os.path.join(Config.UPLOADS_DIR, filename)
        if not os.path.exists(full_path):
            return jsonify({"error": "File not found"}), 404
        return send_from_directory(Config.UPLOADS_DIR, filename)

    @app.route("/api/posts/<post_id>/repost", methods=["POST"])
    @login_required
    # Abuse ceiling: reposts amplify feed spam.
    @_rate_limit("30 per minute")
    def api_repost(post_id):
        ok, msg, repost = social.repost_post(post_id, session["user_id"])
        return jsonify({"success": ok, "message": msg, "repost": repost})

    @app.route("/api/posts/<post_id>/like", methods=["POST"])
    @login_required
    # Abuse ceiling: like-farming (engagement manipulation).
    @_rate_limit("60 per minute")
    def api_like_post(post_id):
        uid = session["user_id"]
        ok, msg, is_liked = social.like_post(post_id, uid)
        post = social.get_post(post_id)
        lc = len(post.get("likes", [])) if post else 0
        rt = get_realtime()
        if rt:
            rt.emit_like_update(post_id, uid, is_liked, lc)
        return jsonify(
            {"success": ok, "message": msg, "is_liked": is_liked, "likes_count": lc}
        )

    @app.route("/api/posts/<post_id>/vote", methods=["POST"])
    @login_required
    # Abuse ceiling: vote-stuffing (engagement manipulation).
    @_rate_limit("60 per minute")
    def api_vote_post(post_id):
        data = request.get_json() or {}
        ok, msg, ns = social.vote_post(
            post_id, session["user_id"], data.get("vote", "up")
        )
        return jsonify(
            {
                "success": ok,
                "message": msg,
                "net_score": ns,
                "user_vote": data.get("vote", "up") if ok else "none",
            }
        )

    @app.route("/api/posts/<post_id>/delete", methods=["POST"])
    @login_required
    def api_delete_post(post_id):
        uid = session["user_id"]
        ok, msg = social.delete_post(post_id, uid)
        if ok:
            rt = get_realtime()
            if rt:
                rt.emit_post_deleted(post_id)
        return jsonify({"success": ok, "message": msg})

    @app.route("/api/posts/<post_id>/comments", methods=["GET", "POST"])
    @login_required
    # Abuse ceiling: comment spam on the shared surface. methods=["POST"] so
    # GET page loads / fetches never consume the budget.
    @_rate_limit("30 per minute", methods=["POST"])
    def api_comments(post_id):
        uid = session["user_id"]
        if request.method == "GET":
            comments = social.get_comments(post_id)
            ud = storage.load_users()
            enriched = [
                dict(
                    c,
                    author_name=u.name if (u := ud.get(c["user_id"])) else "Unknown",
                    author_avatar=avatar_html(u.name, 24) if u else "?",
                    likes_count=len(c.get("likes", [])),
                    time_ago=time_ago(c["created_at"]),
                )
                for c in comments
            ]
            return jsonify({"comments": enriched})
        else:
            data = request.get_json() or {}
            content = data.get("content", "").strip()
            pid = data.get("parent_id")
            ok, msg, comment = social.add_comment(post_id, uid, content, pid)
            if ok and comment:
                post = social.get_post(post_id)
                if post and post["user_id"] != uid:
                    rt = get_realtime()
                    if rt:
                        uu = storage.load_users().get(uid)
                        rt.emit_notification(
                            post["user_id"],
                            {
                                "type": "comment",
                                "message": "%s commented on your post"
                                % (uu.name if uu else uid),
                                "post_id": post_id,
                            },
                        )
                try:
                    if gamification:
                        gamification.on_comment_created(uid)
                # Optional sub-feature: degrade gracefully, never break the request.
                except Exception:  # nosec B110
                    pass
                return jsonify({"success": True, "comment": comment, "message": msg})
            return jsonify({"success": False, "error": msg})

    # ═══════════════════════════════════════════════════════════
    # FOLLOW / HASHTAGS / REVIEWS / SHELVES APIs
    # ═══════════════════════════════════════════════════════════

    @app.route("/api/follow/<user_id>", methods=["POST"])
    @login_required
    # Abuse ceiling: mass follow/unfollow churn.
    @_rate_limit("60 per minute")
    def api_follow_user(user_id):
        uid = session["user_id"]
        is_following = social.is_following(uid, user_id)
        if is_following:
            ok, msg = social.unfollow_user(uid, user_id)
        else:
            ok, msg = social.follow_user(uid, user_id)
        rt = get_realtime()
        if rt:
            rt.emit_follow_update(uid, user_id, not is_following)
        return jsonify(
            {"success": ok, "message": msg, "is_following": not is_following}
        )

    @app.route("/api/hashtags/trending")
    @login_required
    def api_trending_hashtags():
        limit = min(int(request.args.get("limit", 10)), 30)
        return jsonify({"hashtags": social.get_trending_hashtags(limit)})

    @app.route("/api/hashtags/<tag>/posts")
    @login_required
    def api_hashtag_posts(tag):
        uid = session["user_id"]
        page = max(1, int(request.args.get("page", 1)))
        posts, total = social.search_by_hashtag(tag, uid, page=page)
        return jsonify({"posts": posts, "total": total})

    @app.route("/api/reviews/<book_id>", methods=["POST"])
    @login_required
    # Abuse ceiling: review spam is shared-surface content.
    @_rate_limit("30 per minute")
    def api_add_review(book_id):
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg, review = review_mgr.add_review(
            uid,
            book_id,
            int(data.get("rating", 5)),
            data.get("content", "").strip(),
            data.get("spoiler", False),
        )
        return jsonify({"success": ok, "message": msg, "review": review})

    @app.route("/api/reviews/<review_id>/helpful", methods=["POST"])
    @login_required
    # Abuse ceiling: helpful-vote manipulation.
    @_rate_limit("60 per minute")
    def api_helpful_review(review_id):
        uid = session["user_id"]
        ok, msg, is_helpful = review_mgr.mark_helpful(review_id, uid)
        return jsonify({"success": ok, "is_helpful": is_helpful})

    @app.route("/api/bookshelves/<book_id>", methods=["POST"])
    @login_required
    def api_add_to_shelf(book_id):
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg = review_mgr.add_to_shelf(
            uid, book_id, data.get("shelf", "want_to_read")
        )
        return jsonify({"success": ok, "message": msg})

    @app.route("/api/bookshelves/status/<book_id>")
    @login_required
    def api_shelf_status(book_id):
        uid = session["user_id"]
        shelf = review_mgr.is_on_shelf(uid, book_id)
        return jsonify({"shelf": shelf})

    @app.route("/api/bookshelves/<book_id>/remove", methods=["POST"])
    @login_required
    def api_remove_from_shelf(book_id):
        uid = session["user_id"]
        ok, msg = review_mgr.remove_from_shelf(uid, book_id)
        return jsonify({"success": ok, "message": msg})

    @app.route("/api/shelves/create", methods=["POST"])
    @login_required
    # Abuse ceiling: shelf-creation spam.
    @_rate_limit("30 per minute")
    def api_create_shelf():
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg = review_mgr.create_custom_shelf(
            uid,
            data.get("name", ""),
            data.get("description", ""),
            data.get("icon", "bookmark"),
        )
        return jsonify({"success": ok, "message": msg})

    @app.route("/api/shelves")
    @login_required
    def api_get_shelves():
        uid = session["user_id"]
        return jsonify({"shelves": review_mgr.get_user_custom_shelves(uid)})

    @app.route("/api/shelves/<shelf_name>", methods=["DELETE"])
    @login_required
    def api_delete_shelf(shelf_name):
        from urllib.parse import unquote

        shelf_name = unquote(shelf_name)
        ok, msg = review_mgr.delete_custom_shelf(session["user_id"], shelf_name)
        return jsonify({"success": ok, "message": msg})

    @app.route("/api/shelves/<shelf_name>/rename", methods=["POST"])
    @login_required
    def api_rename_shelf(shelf_name):
        from urllib.parse import unquote

        shelf_name = unquote(shelf_name)
        data = request.get_json() or {}
        ok, msg = review_mgr.rename_custom_shelf(
            session["user_id"], shelf_name, data.get("new_name", "")
        )
        return jsonify({"success": ok, "message": msg})

    # ═══════════════════════════════════════════════════════════
    # ADVANCED SEARCH
    # ═══════════════════════════════════════════════════════════

    @app.route("/api/search/suggestions")
    @login_required
    def api_search_suggestions():
        q = request.args.get("q", "").strip()
        if len(q) < 2:
            return jsonify({"suggestions": []})
        ql = q.lower()
        books_data = storage.load_books()
        users_data = storage.load_users()
        suggestions = []
        for b in books_data.values():
            if b.is_deleted:
                continue
            if ql in b.title.lower():
                suggestions.append(
                    {
                        "type": "book",
                        "id": b.book_id,
                        "label": b.title[:60],
                        "sub": b.author,
                        "url": "/books/" + b.book_id,
                    }
                )
                if len(suggestions) >= 8:
                    break
        if len(suggestions) < 8:
            for b in books_data.values():
                if b.is_deleted:
                    continue
                if ql in b.author.lower():
                    count = sum(
                        1
                        for bx in books_data.values()
                        if not bx.is_deleted and bx.author.lower() == b.author.lower()
                    )
                    suggestions.append(
                        {
                            "type": "author",
                            "id": b.author,
                            "label": b.author,
                            "sub": "%d books" % count,
                            "url": "/author/" + b.author.replace(" ", "%20"),
                        }
                    )
                    if len(suggestions) >= 12:
                        break
        if len(suggestions) < 15:
            for u in users_data.values():
                if ql in u.name.lower() or ql in u.user_id.lower():
                    suggestions.append(
                        {
                            "type": "user",
                            "id": u.user_id,
                            "label": u.name,
                            "sub": "@" + u.user_id + " · " + u.role.upper(),
                            "url": "/profile/" + u.user_id,
                        }
                    )
                    if len(suggestions) >= 15:
                        break
        return jsonify({"suggestions": suggestions})

    @app.route("/api/search")
    @login_required
    def api_advanced_search():
        uid = session["user_id"]
        q = request.args.get("q", "").strip()
        entity = request.args.get("entity", "all")
        page = max(1, int(request.args.get("page", 1)))
        pp = min(50, max(10, int(request.args.get("per_page", 20))))
        sort_by = request.args.get("sort", "relevance")
        result = {"query": q, "entity": entity, "page": page}
        if entity in ("all", "books") and q:
            cat = request.args.get("cat", "")
            avail = request.args.get("avail", "") == "1"
            books_result = lib.search_books(
                query=q, category=cat, available_only=avail, sort_by=sort_by
            )
            total = len(books_result)
            start = (page - 1) * pp
            result["books"] = {
                "results": [b.to_dict() for b in books_result[start : start + pp]],
                "total": total,
            }
        if entity in ("all", "users") and q:
            users_result = lib.search_users(query=q)
            total = len(users_result)
            start = (page - 1) * pp
            users_page = []
            for u in users_result[start : start + pp]:
                ud = u.to_dict()
                ud.pop("password_hash", None)
                users_page.append(ud)
            result["users"] = {"results": users_page, "total": total}
        if entity in ("all", "posts") and q:
            posts_result, posts_total = social.search_posts(
                q, uid, page=page, per_page=pp
            )
            result["posts"] = {"results": posts_result, "total": posts_total}
        return jsonify(result)

    @app.route("/api/posts/search")
    @login_required
    def api_search_posts():
        uid = session["user_id"]
        q = request.args.get("q", "")
        page = max(1, int(request.args.get("page", 1)))
        if not q:
            return jsonify({"posts": [], "total": 0})
        posts, total = social.search_posts(q, uid, page=page)
        return jsonify({"posts": posts, "total": total})

    @app.route("/api/comments/<comment_id>/reply", methods=["POST"])
    @login_required
    # Abuse ceiling: reply spam on the shared surface.
    @_rate_limit("30 per minute")
    def api_reply_comment(comment_id):
        uid = session["user_id"]
        data = request.get_json() or {}
        content = data.get("content", "").strip()
        if not content:
            return jsonify({"success": False, "error": "Reply cannot be empty"})
        comments_list = storage.load_comments()
        parent = None
        for c in comments_list:
            if c["comment_id"] == comment_id:
                parent = c
                break
        if not parent:
            return jsonify({"success": False, "error": "Comment not found"})
        ok, msg, comment = social.add_comment(
            parent["post_id"], uid, content, parent_id=comment_id
        )
        return jsonify({"success": ok, "message": msg, "comment": comment})

    @app.route("/api/reviews/<review_id>/comments", methods=["GET", "POST"])
    @login_required
    # Abuse ceiling: review-comment spam. methods=["POST"] so GET page loads /
    # fetches never consume the budget.
    @_rate_limit("30 per minute", methods=["POST"])
    def api_review_comments(review_id):
        uid = session["user_id"]
        if request.method == "GET":
            return jsonify({"comments": review_mgr.get_review_comments(review_id)})
        else:
            data = request.get_json() or {}
            content = data.get("content", "").strip()
            if not content:
                return jsonify({"success": False, "error": "Comment cannot be empty"})
            ok, msg, comment = review_mgr.add_review_comment(review_id, uid, content)
            return jsonify({"success": ok, "message": msg, "comment": comment})

    @app.route("/api/reviews/<book_id>/list")
    @login_required
    def api_reviews_list(book_id):
        uid = session["user_id"]
        page = max(1, int(request.args.get("page", 1)))
        sort_by = request.args.get("sort", "recent")
        reviews, stats = review_mgr.get_book_reviews(
            book_id, uid, page=page, sort_by=sort_by
        )
        return jsonify({"reviews": reviews, "stats": stats})

    @app.route("/api/books/<book_id>/reviews")
    @login_required
    def api_book_reviews(book_id):
        uid = session["user_id"]
        page = max(1, int(request.args.get("page", 1)))
        reviews, stats = review_mgr.get_book_reviews(book_id, uid, page=page)
        return jsonify({"reviews": reviews, "stats": stats})

    @app.route("/api/books/<book_id>/review", methods=["POST"])
    @login_required
    # Abuse ceiling: review spam is shared-surface content.
    @_rate_limit("30 per minute")
    def api_submit_review(book_id):
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg, review = review_mgr.add_review(
            uid,
            book_id,
            int(data.get("rating", 5)),
            data.get("content", ""),
            data.get("spoiler", False),
        )
        return jsonify({"success": ok, "message": msg, "review": review})

    # ═══════════════════════════════════════════════════════════
    # FEED PAGE
    # ═══════════════════════════════════════════════════════════

    # ═══════════════════════════════════════════════════════════
    # PROFILE API ENDPOINTS (favorites, reviews stats)
    # ═══════════════════════════════════════════════════════════

    @app.route("/api/reviews/stats")
    @login_required
    def api_reviews_stats_overall():
        """Get overall rating distribution stats for the profile chart."""
        all_reviews = storage.load_reviews()
        dist = {}
        for r in all_reviews:
            star = r.get("rating", 0)
            dist[star] = dist.get(star, 0) + 1
        labels = ["1 Star", "2 Stars", "3 Stars", "4 Stars", "5 Stars"]
        values = [dist.get(i, 0) for i in range(1, 6)]
        return jsonify({"labels": labels, "values": values, "total": len(all_reviews)})

    @app.route("/api/profile/favorites/remove", methods=["POST"])
    @login_required
    def api_profile_favorites_remove():
        """Remove a book from the current user's favorite_books list."""
        uid = session["user_id"]
        data = request.get_json() or {}
        book_id = data.get("book_id", "")
        if not book_id:
            return jsonify({"success": False, "error": "No book_id provided"})
        users = storage.load_users()
        user = users.get(uid)
        if not user:
            return jsonify({"success": False, "error": "User not found"})
        if book_id in user.favorite_books:
            user.favorite_books.remove(book_id)
            storage.save_users(users)
            return jsonify({"success": True, "message": "Removed from favorites"})
        return jsonify({"success": False, "error": "Book not in favorites"})

    @app.route("/api/profile/favorites/reorder", methods=["POST"])
    @login_required
    def api_profile_favorites_reorder():
        """Reorder the current user's favorite_books list."""
        uid = session["user_id"]
        data = request.get_json() or {}
        book_ids = data.get("book_ids", [])
        if not book_ids:
            return jsonify({"success": False, "error": "No book_ids provided"})
        users = storage.load_users()
        user = users.get(uid)
        if not user:
            return jsonify({"success": False, "error": "User not found"})
        # Validate that book_ids correspond to real books
        all_books = storage.load_books()
        valid_ids = [bid for bid in book_ids if bid in all_books]
        user.favorite_books = valid_ids[:4]  # Max 4 favorites
        storage.save_users(users)
        return jsonify({"success": True, "message": "Favorites reordered"})

    @app.route("/api/profile/favorites/add", methods=["POST"])
    @login_required
    def api_profile_favorites_add():
        """Add a book to the current user's favorite_books list (max 4)."""
        uid = session["user_id"]
        data = request.get_json() or {}
        book_id = data.get("book_id", "")
        if not book_id:
            return jsonify({"success": False, "error": "No book_id provided"})
        books = storage.load_books()
        if book_id not in books:
            return jsonify({"success": False, "error": "Book not found"})
        users = storage.load_users()
        user = users.get(uid)
        if not user:
            return jsonify({"success": False, "error": "User not found"})
        if len(user.favorite_books) >= 4:
            return jsonify(
                {
                    "success": False,
                    "error": "Maximum 4 favorites allowed. Remove one first.",
                }
            )
        if book_id in user.favorite_books:
            return jsonify({"success": False, "error": "Book already in favorites"})
        user.favorite_books.append(book_id)
        storage.save_users(users)
        return jsonify(
            {
                "success": True,
                "message": "Added to favorites",
                "favorites": user.favorite_books,
            }
        )

    @app.route("/api/profile/update", methods=["POST"])
    @login_required
    # Defense in depth: email is a password-reset identity, so changing it is
    # an account-takeover vector. Only requests that actually change the email
    # consume the per-IP budget (deduct_when); name/bio edits are never
    # throttled — the global 200/min default is no longer the only guard.
    @_rate_limit(
        "10 per minute",
        deduct_when=lambda response: getattr(g, "_profile_email_changed", False),
    )
    def api_profile_update():
        """Update the current user's profile fields."""
        uid = session["user_id"]
        data = request.get_json() or {}
        users = storage.load_users()
        user = users.get(uid)
        if not user:
            return jsonify({"success": False, "error": "User not found"})
        if "email" in data:
            g._profile_email_changed = True
        allowed = {
            "name",
            "email",
            "phone",
            "bio",
            "website",
            "location",
            "profile_picture",
        }
        for key in allowed:
            if key in data:
                setattr(user, key, data[key])
        storage.save_users(users)
        if "name" in data:
            session["user_name"] = data["name"]
        return jsonify({"success": True, "message": "Profile updated"})

    @app.route("/feed")
    @login_required
    def feed_page():
        # Trending posts are loaded via the right sidebar's API calls
        # (The trending section in the right sidebar handles this dynamically)
        # Build the feed HTML
        FEED_CONTENT = """<!-- Compose Box -->
<div class="compose-box animate-in">
  <form class="w-100" onsubmit="return submitPost()">
    <textarea id="postContent" class="w-100" placeholder="What\'s happening?" aria-label="What\'s happening?" rows="2" style="border:none;resize:none;font-size:1.1rem;padding:8px 0;background:transparent;color:var(--text);outline:none;font-family:var(--font);min-height:50px;"></textarea>
    <div class="compose-toolbar">
      <div>
        <button type="submit" class="btn btn-primary" id="postSubmitBtn"><i class="bi bi-feather"></i> Post</button>
      </div>
      <div class="text-muted small" id="postCharCount">0 / 500</div>
    </div>
  </form>
</div>

<!-- Feed Tabs -->
<nav class="d-flex border-bottom" style="border-color:var(--border);" aria-label="Feed tabs">
  <a href="#" class="feed-tab active" data-tab="following" onclick="switchFeedTab(this)">Following</a>
  <a href="#" class="feed-tab" data-tab="trending" onclick="switchFeedTab(this)">Trending</a>
  <a href="#" class="feed-tab" data-tab="discover" onclick="switchFeedTab(this)">Discover</a>
</nav>

<!-- Feed Content -->
<div id="feedContent" style="min-height:200px;">
  <div class="text-center py-5"><div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div></div>
</div>

<!-- Trending Section (Right sidebar already handles this) -->
"""
        return render_page(
            "Social Feed",
            FEED_CONTENT
            + """
<!-- Feed JavaScript: load posts, post creation, like, tab switching -->
<script>
var currentFeedTab = "following";
var currentFeedPage = 1;

function loadFeed(tab, page) {
  currentFeedTab = tab || currentFeedTab;
  currentFeedPage = page || 1;
  var c = document.getElementById("feedContent");
  if (!c) return;
  c.innerHTML = '<div class="text-center py-5"><div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div></div>';
  fetch("/api/feed?tab=" + currentFeedTab + "&page=" + currentFeedPage)
    .then(function(r){ return r.json() })
    .then(function(d) {
      if (!d.posts || !d.posts.length) {
        c.innerHTML = '<div class="empty-state empty-state-variant py-5"><div class="empty-icon"><i class="bi bi-inbox"></i></div><div class="empty-title">No posts yet</div><div class="empty-desc">Follow users or be the first to share what you are reading!</div><button class="empty-cta" onclick="document.getElementById('postContent')?.focus()"><i class="bi bi-feather"></i> Create a Post</button></div>';
        return;
      }
      var html = "";
      d.posts.forEach(function(p) {
        var likedClass = p.is_liked ? " liked" : "";
        html += '<article class="post-card">';
        html += '<div class="post-card-body">';
        html += '<div class="post-card-header">' + p.author_avatar + ' <a href="/profile/' + p.user_id + '" class="post-author-name">' + p.author_name + '</a><span class="text-muted" style="font-size:.8rem;">' + (p.time_ago || "") + '</span></div>';
        html += '<div class="post-content-text">' + p.content + '</div>';
        html += '<div class="post-actions">';
        html += '<button class="post-action' + likedClass + '" onclick="likePost(\'' + p.post_id + '\',this)"><i class="bi bi-heart-fill"></i> ' + (p.likes_count || 0) + '</button>';
        html += '<button class="post-action" onclick="window.location.href=\'/profile/' + p.user_id + '\'"><i class="bi bi-chat-fill"></i> ' + (p.comment_count || 0) + '</button>';
        html += '</div></div></article>';
      });
      c.innerHTML = html;
    })
    .catch(function() {
      c.innerHTML = '<div class="empty-state empty-state-variant py-5"><div class="empty-icon"><i class="bi bi-wifi-off"></i></div><div class="empty-title">Could not load feed</div><div class="empty-desc">Check your connection and try again.</div><button class="empty-cta" onclick="loadFeed('following',1)"><i class="bi bi-arrow-clockwise"></i> Retry</button></div>';
    });
}

function switchFeedTab(el) {
  document.querySelectorAll(".feed-tab").forEach(function(t){ t.classList.remove("active"); });
  el.classList.add("active");
  loadFeed(el.getAttribute("data-tab"), 1);
}

function submitPost() {
  var ta = document.getElementById("postContent");
  if (!ta) return false;
  var content = ta.value.trim();
  if (!content) { showToast("Write something!", "error"); return false; }
  fetch("/api/posts", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({content: content})
  }).then(function(r){ return r.json() }).then(function(d){
    if (d.success) {
      ta.value = "";
      showToast("Posted!", "success");
      loadFeed(currentFeedTab, 1);
    } else {
      showToast(d.error || "Failed to post", "error");
    }
  });
  return false;
}

function likePost(postId, btn) {
  fetch("/api/posts/" + postId + "/like", {method: "POST"})
    .then(function(r){ return r.json() })
    .then(function(d){
      if (btn) {
        var count = d.likes_count || 0;
        btn.innerHTML = (d.is_liked ? '<i class="bi bi-heart-fill"></i> ' : '<i class="bi bi-heart-fill"></i> ') + count;
        btn.classList.toggle("liked", d.is_liked);
      }
    });
}

// Character count on post content
document.addEventListener("DOMContentLoaded", function(){
  var ta = document.getElementById("postContent");
  var cc = document.getElementById("postCharCount");
  if (ta && cc) {
    ta.addEventListener("input", function(){
      var len = ta.value.length;
      cc.textContent = len + " / 500";
      if (len > 500) { ta.value = ta.value.substring(0,500); cc.textContent = "500 / 500"; }
    });
  }
  loadFeed("following", 1);
});
</script>
""",
        )

    @app.route("/search")
    @login_required
    def search_page():
        return render_page(
            "Search",
            '<div class="empty-state empty-state-variant py-5"><div class="empty-icon"><i class="bi bi-search" style="font-size:3rem;"></i></div><div class="empty-title">Search Books &amp; People</div><div class="empty-desc">Use the search overlay (Ctrl+K) to find books, users, and more.</div><button class="empty-cta" onclick="openSearchOverlay()"><i class="bi bi-search me-2"></i>Open Search</button></div>',
        )

    @app.route("/profile/edit")
    @login_required
    def profile_edit_page():
        """Profile edit page."""
        uid = session["user_id"]
        users_data = storage.load_users()
        user = users_data.get(uid)
        if not user:
            return render_page(
                "Not Found",
                '<div class="empty-state empty-state-variant"><div class="empty-icon"><i class="bi bi-person-x-fill"></i></div><div class="empty-title">User not found</div><div class="empty-desc">The user you are looking for does not exist.</div></div>',
            )
        bio_val = h(user.bio) if user.bio else ""
        name_val = h(user.name)
        email_val = h(user.email) if user.email else ""
        phone_val = h(user.phone) if user.phone else ""
        website_val = h(user.website) if user.website else ""
        location_val = h(user.location) if user.location else ""
        pp_val = h(user.profile_picture) if user.profile_picture else ""
        avatar = avatar_html(user.name, 64)
        CONTENT = """<div class="animate-in">
    <div class="profile-banner"></div>
    <div class="row justify-content-center" style="margin-top:-40px;">
        <div class="col-lg-8">
            <div class="glass-card p-4">
                <div class="d-flex gap-3 mb-4 align-items-center">
                    <div id="avatarPreview">AVATAR_PLACEHOLDER</div>
                    <div>
                        <h4 class="fw-bold mb-0">Edit Profile</h4>
                        <p class="text-muted small mb-0">@USER_ID_PLACEHOLDER &middot; ROLE_PLACEHOLDER</p>
                    </div>
                    <div class="ms-auto">
                        <a href="/profile/USER_ID_PLACEHOLDER" class="btn btn-outline btn-sm"><i class="bi bi-arrow-left"></i> Back</a>
                    </div>
                </div>
                <hr style="border-color:var(--border);">
                <form id="profileEditForm" onsubmit="return saveProfile()">
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Display Name</label>
                            <input type="text" id="editName" class="form-control" value="NAME_PLACEHOLDER" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Email</label>
                            <input type="email" id="editEmail" class="form-control" value="EMAIL_PLACEHOLDER">
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Phone</label>
                            <input type="text" id="editPhone" class="form-control" value="PHONE_PLACEHOLDER">
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Website</label>
                            <input type="url" id="editWebsite" class="form-control" value="WEBSITE_PLACEHOLDER" placeholder="https://example.com">
                        </div>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Location</label>
                        <input type="text" id="editLocation" class="form-control" value="LOCATION_PLACEHOLDER" placeholder="City, Country">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Bio</label>
                        <textarea id="editBio" class="form-control" rows="4" placeholder="Tell us about yourself...">BIO_PLACEHOLDER</textarea>
                        <small class="text-muted" id="bioCharCount">0 / 500</small>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Profile Picture</label>
                        <div class="input-group">
                            <input type="url" id="editProfilePic" class="form-control" value="PP_PLACEHOLDER" placeholder="https://example.com/avatar.jpg" oninput="previewAvatar(this.value)">
                            <button class="btn btn-outline" type="button" onclick="document.getElementById(\'editProfilePic\').value=\'\';previewAvatar(\'\')"><i class="bi bi-x-lg"></i></button>
                        </div>
                        <small class="text-muted">Enter a URL, or upload an image below</small>
                    </div>
                    <div class="mb-3 p-3" style="border:2px dashed var(--border);border-radius:12px;text-align:center;">
                        <label class="form-label d-block">Upload New Avatar</label>
                        <input type="file" id="avatarUploadInput" accept="image/jpeg,image/png,image/gif,image/webp" style="display:none;" onchange="uploadAvatar(this)">
                        <button class="btn btn-outline" type="button" onclick="document.getElementById(\'avatarUploadInput\').click()">
                            <i class="bi bi-cloud-upload"></i> Choose File
                        </button>
                        <div id="avatarUploadStatus" class="mt-2 small text-muted">Max 5MB, JPG/PNG/GIF/WEBP</div>
                    </div>
                    <div class="d-flex gap-2">
                        <button type="submit" class="btn btn-primary" id="saveProfileBtn"><i class="bi bi-check-lg"></i> Save Changes</button>
                        <a href="/profile/USER_ID_PLACEHOLDER" class="btn btn-outline">Cancel</a>
                    </div>
                </form>
            </div>
        </div>
    </div>
</div>
<script>
function saveProfile() {
    var btn = document.getElementById("saveProfileBtn");
    btn.disabled = true;
    btn.innerHTML = \'<span class="spinner-border spinner-border-sm"></span> Saving...\';
    var data = {
        name: document.getElementById("editName").value.trim(),
        email: document.getElementById("editEmail").value.trim(),
        phone: document.getElementById("editPhone").value.trim(),
        website: document.getElementById("editWebsite").value.trim(),
        location: document.getElementById("editLocation").value.trim(),
        bio: document.getElementById("editBio").value.trim(),
        profile_picture: document.getElementById("editProfilePic").value.trim()
    };
    if (!data.name) { showToast("Name is required", "error"); btn.disabled = false; btn.innerHTML = \'<i class="bi bi-check-lg"></i> Save Changes\'; return false; }
    fetch("/api/profile/update", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(data)
    }).then(function(r){ return r.json() }).then(function(d){
        if (d.success) {
            showToast("Profile updated!", "success");
            setTimeout(function(){ window.location.href = "/profile/\' + uid + \'"; }, 1000);
        } else {
            showToast(d.error || "Failed to update", "error");
            btn.disabled = false;
            btn.innerHTML = \'<i class="bi bi-check-lg"></i> Save Changes\';
        }
    }).catch(function(){
        showToast("Network error", "error");
        btn.disabled = false;
        btn.innerHTML = \'<i class="bi bi-check-lg"></i> Save Changes\';
    });
    return false;
}
function previewAvatar(url) {
    var preview = document.getElementById("avatarPreview");
    if (url) {
        preview.innerHTML = \'<div class="avatar" style="width:64px;height:64px;background-size:cover;background-image:url(\' + encodeURI(url) + \');border-radius:50%;border:3px solid var(--bg);box-shadow:0 4px 12px rgba(0,0,0,.1);"></div>\';
    } else {
        preview.innerHTML = "AVATAR2_PLACEHOLDER";
    }
}

function uploadAvatar(input) {
    var file = input.files[0];
    if (!file) return;
    var status = document.getElementById("avatarUploadStatus");
    var btn = input.parentElement.querySelector("button");
    var oldHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = \'<span class="spinner-border spinner-border-sm"></span> Uploading...\';
    status.textContent = "Uploading...";
    var formData = new FormData();
    formData.append("file", file);
    formData.append("type", "avatar");
    fetch("/api/upload", {
        method: "POST",
        body: formData
    }).then(function(r){ return r.json() }).then(function(d){
        if (d.success) {
            document.getElementById("editProfilePic").value = d.url;
            previewAvatar(d.url);
            status.innerHTML = \'<span class="text-success"><i class="bi bi-check-circle"></i> Uploaded!</span> \' + d.url;
            showToast("Avatar uploaded!", "success");
        } else {
            status.textContent = d.error || "Upload failed";
            showToast(d.error || "Upload failed", "error");
        }
        btn.disabled = false;
        btn.innerHTML = oldHtml;
    }).catch(function(){
        status.textContent = "Network error";
        showToast("Network error", "error");
        btn.disabled = false;
        btn.innerHTML = oldHtml;
    });
    input.value = "";
}
document.addEventListener("DOMContentLoaded", function(){
    var bio = document.getElementById("editBio");
    var cc = document.getElementById("bioCharCount");
    if (bio && cc) {
        cc.textContent = bio.value.length + " / 500";
        bio.addEventListener("input", function(){
            var len = bio.value.length;
            cc.textContent = len + " / 500";
            if (len > 500) { bio.value = bio.value.substring(0,500); cc.textContent = "500 / 500"; }
        });
    }
});
</script>"""
        # Replace placeholders with actual values
        CONTENT = CONTENT.replace("AVATAR_PLACEHOLDER", avatar).replace(
            "AVATAR2_PLACEHOLDER", avatar
        )
        CONTENT = CONTENT.replace("USER_ID_PLACEHOLDER", h(uid))
        CONTENT = CONTENT.replace("ROLE_PLACEHOLDER", h(user.role.upper()))
        CONTENT = CONTENT.replace("NAME_PLACEHOLDER", name_val)
        CONTENT = CONTENT.replace("EMAIL_PLACEHOLDER", email_val)
        CONTENT = CONTENT.replace("PHONE_PLACEHOLDER", phone_val)
        CONTENT = CONTENT.replace("WEBSITE_PLACEHOLDER", website_val)
        CONTENT = CONTENT.replace("LOCATION_PLACEHOLDER", location_val)
        CONTENT = CONTENT.replace("BIO_PLACEHOLDER", bio_val)
        CONTENT = CONTENT.replace("PP_PLACEHOLDER", pp_val)
        return render_page("Edit Profile", CONTENT)

    # ═══════════════════════════════════════════════════════════
    # AUTHOR PAGE
    # ═══════════════════════════════════════════════════════════

    @app.route("/author/<author_name>")
    @login_required
    def author_page(author_name):
        from urllib.parse import unquote

        author_name = unquote(author_name).strip()
        books_data = storage.load_books()
        author_books = [
            b
            for b in books_data.values()
            if not b.is_deleted and author_name.lower() in b.author.lower()
        ]
        total_books = len(author_books)
        total_copies = sum(b.total_copies for b in author_books)
        total_issues = sum(b.issue_count for b in author_books)
        BOOKS_GRID = ""
        for b in sorted(author_books, key=lambda bx: bx.issue_count, reverse=True)[:24]:
            cc = cat_color(b.category)
            avail = (
                '<span class="badge-green px-2 py-1 small">Available</span>'
                if b.available_copies > 0
                else '<span class="badge-red px-2 py-1 small">Out</span>'
            )
            BOOKS_GRID += (
                '<a href="/books/%s" class="text-decoration-none col-6 col-md-4 col-lg-3 mb-2"><div class="glass-card p-2 text-center" style="cursor:pointer;"><div style="font-size:1.2rem;color:%s;"><i class="bi bi-book-fill"></i></div><div class="fw-bold small">%s</div><small class="text-muted">%s</small><div class="mt-1">%s</div></div></a>'
                % (b.book_id, cc, h(b.title)[:40], h(b.category), avail)
            )
        if not BOOKS_GRID:
            BOOKS_GRID = '<div class="col-12"><div class="empty-state empty-state-variant"><div class="empty-icon"><i class="bi bi-book"></i></div><div class="empty-title">No books found</div><div class="empty-desc">This author has no books in the library yet.</div></div></div>'
        from collections import Counter

        cat_counts = Counter(b.category for b in author_books)
        CAT_LIST = ""
        for cat, cnt in cat_counts.most_common():
            cc = cat_color(cat)
            CAT_LIST += (
                '<span class="badge me-1 mb-1" style="background:%s20;color:%s;">%s (%d)</span>'
                % (cc, cc, h(cat), cnt)
            )
        AUTHOR_CONTENT = (
            '<div class="animate-in"><div class="glass-card p-4 mb-3"><div class="d-flex gap-3"><div style="width:72px;height:72px;border-radius:50%%;background:linear-gradient(135deg,#4f46e5,#a855f7);display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:1.8rem;color:white;"><i class="bi bi-person-fill"></i></div><div><h1 class="fw-bold mb-0" style="font-size:1.2rem;">%s</h1><div class="text-muted small">Author</div><div class="info-grid mt-2"><div class="info-card p-2"><div class="value">%d</div><div class="label">Books</div></div><div class="info-card p-2"><div class="value">%d</div><div class="label">Copies</div></div><div class="info-card p-2"><div class="value">%d</div><div class="label">Issues</div></div></div><div class="mt-2">%s</div></div></div></div><h5 class="fw-bold mb-2 mt-3"><i class="bi bi-book-fill text-primary me-1"></i> Books by %s</h5><div class="row g-2">%s</div></div>'
            % (
                h(author_name),
                total_books,
                total_copies,
                total_issues,
                CAT_LIST,
                h(author_name),
                BOOKS_GRID,
            )
        )
        return render_page(author_name, AUTHOR_CONTENT)

    # ═══════════════════════════════════════════════════════════
    # PROFILE PAGE (Phase 4 Showcase)
    # ═══════════════════════════════════════════════════════════

    @app.route("/profile/<user_id>")
    @login_required
    def profile_page(user_id):
        uid = session["user_id"]
        users_data = storage.load_users()
        pu = users_data.get(user_id)
        if not pu:
            return render_page(
                "Not Found",
                '<div class="empty-state empty-state-variant"><div class="empty-icon"><i class="bi bi-person-x-fill"></i></div><div class="empty-title">User not found</div><div class="empty-desc">The user you are looking for does not exist.</div><a href="/feed" class="empty-cta"><i class="bi bi-house-fill"></i> Go to Feed</a></div>',
            )
        is_own = uid == user_id
        is_following = social.is_following(uid, user_id)
        fc = social.get_following_count(user_id)
        flc = social.get_follower_count(user_id)
        stats = review_mgr.get_user_reading_stats(user_id)
        # Gamification
        gd = {}
        badges = []
        gm_lev = "New Reader"
        gm_pts = 0
        gm_stk = 0
        if gamification:
            try:
                gd = gamification.get_user_gamification(user_id)
                badges = gd.get("achievements", [])
                gm_lev = gd.get("level", "New Reader")
                gm_pts = gd.get("points", 0)
                gm_stk = gd.get("streak_days", 0)
            # Optional sub-feature: degrade gracefully, never break the request.
            except Exception:  # nosec B110
                pass
        # Diary
        de = []
        dtot = 0
        try:
            from app.services.reading.diary import DiaryManager

            de, dtot = DiaryManager(storage).get_user_diary(user_id, page=1, per_page=5)
        # Optional sub-feature: degrade gracefully, never break the request.
        except Exception:  # nosec B110
            pass
        # Challenge
        cd = {}
        try:
            from app.services.reading.reading_challenge import ReadingChallenge

            cd = ReadingChallenge(storage).get_goal(user_id, datetime.now().year)
        # Optional sub-feature: degrade gracefully, never break the request.
        except Exception:  # nosec B110
            pass
        ds = {}
        try:
            ds = DiaryManager(storage).get_stats(user_id)
        # Optional sub-feature: degrade gracefully, never break the request.
        except Exception:  # nosec B110
            pass
        favs = getattr(pu, "favorite_books", [])
        shelves = review_mgr.get_user_shelf(user_id)
        sc = review_mgr.get_shelf_counts(user_id)

        # Posts
        posts, tp = social.get_user_posts(user_id, uid, page=1, per_page=5)
        PH = ""
        for p in posts:
            PH += (
                '<div class="glass-card p-3 mb-2" style="animation:cardEnter .3s ease both;"><div style="font-size:.9rem;">%s</div><div class="d-flex gap-2 mt-2" style="font-size:.75rem;color:var(--text-muted);"><span>\u2764\ufe0f %d</span><span>\U0001f4ac %d</span><span>%s</span></div></div>'
                % (
                    h(p.get("content", "")),
                    p.get("likes_count", 0),
                    p.get("comment_count", 0),
                    p.get("time_ago", ""),
                )
            )
        if not PH:
            PH = '<div class="text-center text-muted small py-3">No posts yet.</div>'

        # Activity
        rl, _ = review_mgr.get_user_reviews(user_id, uid, page=1, per_page=5)
        AH = ""
        for r in rl:
            stars = "\u2605" * r["rating"] + "\u2606" * (5 - r["rating"])
            AH += (
                '<div class="activity-item"><div class="activity-icon" style="background:#f59e0b20;color:#f59e0b;"><i class="bi bi-star-fill"></i></div><div class="flex-grow-1"><div style="font-size:.85rem;"><strong>%s</strong> %s</div><div style="font-size:.75rem;color:var(--text-muted);">Reviewed %s</div></div></div>'
                % (h(r.get("book_title", "")), stars, r.get("time_ago", ""))
            )
        if not AH:
            AH = '<div class="text-center text-muted small py-3">No reviews yet.</div>'

        DH = _render_diary_entries(de)
        FGH = _render_fav_grid(favs, is_own)
        BGH = _render_badges_grid(badges)

        # Heatmap
        HS = ""
        try:
            hm_path = os.path.join(Config.DATA_DIR, "diary.json")
            he = []
            try:
                with open(hm_path, "r", encoding="utf-8") as f:
                    he = json.load(f)
            # Optional sub-feature: degrade gracefully, never break the request.
            except Exception:  # nosec B110
                pass
            from datetime import date as d2

            td = d2.today()
            hmd = {}
            for i in range(365):
                hmd[(td - timedelta(days=i)).isoformat()] = 0
            for e in he:
                if e.get("user_id") == user_id:
                    dr = e.get("date_read", "")
                    if dr in hmd:
                        hmd[dr] += 1
            hml = [{"date": d, "count": hmd[d]} for d in sorted(hmd.keys())]
            HS = _render_heatmap_svg(hml, sum(hmd.values()))
        except:
            HS = '<div class="text-center text-muted small py-3">Heatmap unavailable</div>'

        FB = ""
        if not is_own:
            if is_following:
                FB = (
                    '<button class="btn btn-outline btn-sm" onclick="toggleFollow(\'%s\',this)"><i class="bi bi-person-check"></i> Following</button>'
                    % user_id
                )
            else:
                FB = (
                    '<button class="btn btn-primary btn-sm" onclick="toggleFollow(\'%s\',this)"><i class="bi bi-person-plus"></i> Follow</button>'
                    % user_id
                )

        if pu.profile_picture:
            PA = (
                '<div class="avatar" style="width:72px;height:72px;background-size:cover;background-image:url(%s);border-radius:50%%;border:3px solid var(--bg);box-shadow:0 4px 12px rgba(0,0,0,.1);" title="%s"></div>'
                % (h(pu.profile_picture), h(pu.name))
            )
        else:
            PA = avatar_html(pu.name, 72)

        cp = cd.get("progress", 0) if cd else 0
        cg = cd.get("goal", 0) if cd else 0
        CR = ""
        if cg > 0:
            pct = min(100, round(cp / cg * 100))
            circ = 2 * 3.14159 * 36
            offset = circ - (pct / 100) * circ
            CR = (
                '<div class="bt-challenge-ring-wrapper"><svg class="bt-progress-ring" viewBox="0 0 80 80"><circle class="ring-bg" cx="40" cy="40" r="36"/><circle class="ring-fg" cx="40" cy="40" r="36" style="stroke-dasharray:%s;stroke-dashoffset:%s;"/><text class="ring-text" x="40" y="40" text-anchor="middle" dominant-baseline="central" font-size="18" font-weight="700">%d%%</text></svg><div class="bt-challenge-label">%d / %d books</div></div>'
                % (circ, offset, pct, cp, cg)
            )

        # Shelf HTML
        SH = ""
        for sname in ["want_to_read", "reading", "read"]:
            if sname in sc:
                icon = {
                    "want_to_read": "bookmark-heart",
                    "reading": "book",
                    "read": "check-circle",
                }.get(sname, "bookmark")
                col = {
                    "want_to_read": "#f59e0b",
                    "reading": "#4f46e5",
                    "read": "#10b981",
                }.get(sname, "#4f46e5")
                label = {
                    "want_to_read": "Want to Read",
                    "reading": "Currently Reading",
                    "read": "Read",
                }.get(sname, sname)
                cnt = sc.get(sname, 0)
                bis = [s for s in shelves if s["shelf"] == sname][:6]
                sh_section = (
                    ""
                    if not bis
                    else "".join(
                        '<a href="/books/%s" class="text-decoration-none"><div class="shelf-book" style="border-left:3px solid %s;"><div class="fw-bold" style="font-size:.8rem;">%s</div><small class="text-muted">%s</small></div></a>'
                        % (h(b["book_id"]), col, h(b["title"]), h(b["author"]))
                        for b in bis
                    )
                )
                if not sh_section:
                    sh_section = '<div class="text-center text-muted small py-3">No books yet.</div>'
                SH += (
                    '<div class="glass-card p-3 mb-3"><div class="section-title"><i class="bi bi-%s-fill" style="color:%s;"></i> %s (%d)</div>%s</div>'
                    % (icon, col, label, cnt, sh_section)
                )

        cs = review_mgr.get_user_custom_shelves(user_id)
        for c in cs:
            name = c["name"]
            icon = c.get("icon", "bookmark")
            col = c.get("color", "#4f46e5")
            cnt = c.get("book_count", 0)
            bis = [s for s in shelves if s["shelf"] == name][:6]
            sh_section = (
                ""
                if not bis
                else "".join(
                    '<a href="/books/%s" class="text-decoration-none"><div class="shelf-book" style="border-left:3px solid %s;"><div class="fw-bold" style="font-size:.8rem;">%s</div><small class="text-muted">%s</small></div></a>'
                    % (h(b["book_id"]), col, h(b["title"]), h(b["author"]))
                    for b in bis
                )
            )
            if not sh_section:
                sh_section = (
                    '<div class="text-center text-muted small py-3">Empty shelf.</div>'
                )
            db = (
                '<button class="btn btn-sm" style="background:none;border:none;color:var(--text-dim);font-size:.65rem;padding:0;" onclick="deleteShelf(\'%s\')" title="Delete shelf"><i class="bi bi-trash"></i></button>'
                % h(name)
                if is_own
                else ""
            )
            eb = (
                '<button class="btn btn-sm" style="background:none;border:none;color:var(--text-dim);font-size:.65rem;padding:0;" onclick="renameShelf(\'%s\')" title="Rename shelf"><i class="bi bi-pencil"></i></button>'
                % h(name)
                if is_own
                else ""
            )
            SH += (
                '<div class="glass-card p-3 mb-3"><div class="section-title d-flex justify-content-between align-items-center"><span><i class="bi bi-%s-fill" style="color:%s;"></i> %s (%d)</span><span class="d-flex gap-1">%s %s</span></div>%s</div>'
                % (icon, col, h(name), cnt, eb, db, sh_section)
            )
        if is_own:
            SH += '<button class="btn btn-outline btn-sm w-100 mt-2" onclick="createShelf()" style="border-style:dashed;"><i class="bi bi-plus-circle"></i> Create New Shelf</button>'

        # Build the showcase template
        vb = '<span class="text-muted small">Not enough data</span>'
        if ds.get("top_genres"):
            vb = "".join(
                '<span class="bt-vibe-tag">%s <small class="text-muted">(%d)</small></span>'
                % (h(g[0]), g[1])
                for g in ds.get("top_genres", [])
            )

        unlocked_count = sum(1 for b in badges if b.get("unlocked")) if badges else 0
        total_badges = len(badges) if badges else 0

        PCONTENT = """<div class="animate-in" style="--i:0;">
    <div class="profile-banner"><div style="position:absolute;bottom:1rem;right:1.5rem;color:rgba(255,255,255,.4);font-size:.7rem;letter-spacing:1px;font-weight:600;">BOOKSOCIAL</div></div>
    <div class="glass-card p-0 mb-3" style="overflow:hidden;">
        <div class="profile-info-row">
            <div class="profile-avatar-wrapper">%s</div>
            <div class="flex-grow-1 pb-2">
                <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
                    <div><h4 class="fw-bold mb-0" style="font-size:1.2rem;">%s %s</h4><div class="text-muted" style="font-size:.8rem;">@%s &middot; %s</div></div>
                    <div class="d-flex gap-2">%s <a href="/profile/edit" class="btn btn-outline btn-sm"><i class="bi bi-pencil"></i></a></div>
                </div>
                <div class="profile-stats">
                    <div class="profile-stat"><div class="num">%d</div><div class="label">Following</div></div>
                    <div class="profile-stat"><div class="num">%d</div><div class="label">Followers</div></div>
                    <div class="profile-stat"><div class="num">%d</div><div class="label">Books Read</div></div>
                    <div class="profile-stat"><div class="num">%d</div><div class="label">Reviews</div></div>
                    <div class="profile-stat"><div class="num">%s</div><div class="label">Avg Rating</div></div>
                </div>
                <div class="d-flex flex-wrap gap-1 mt-1">
                    <span class="bt-stat-pill"><i class="bi bi-trophy-fill"></i> <span class="bt-stat-num">%d</span> pts &middot; %s</span>
                    <span class="bt-stat-pill"><i class="bi bi-fire"></i> <span class="bt-stat-num">%d</span>-day streak</span>
                </div>
            </div>
        </div>
    </div>
    <div class="row g-3">
        <div class="col-lg-4">
            %s
            <div class="glass-card p-3 mb-3"><div class="section-title"><i class="bi bi-bookmark-star-fill text-warning"></i> Favorite Books</div>%s<div class="text-muted small mt-2">Drag to reorder%s</div></div>
            <div class="glass-card p-3 mb-3">
                <div class="section-title"><i class="bi bi-pie-chart-fill text-primary"></i> Reading Stats</div>
                <div class="bt-profile-stats-grid">
                    <div class="metric-card p-2 text-center"><div class="bt-profile-stat-value count-up" data-target="%d">0</div><div class="bt-profile-stat-label">Total Read</div></div>
                    <div class="metric-card p-2 text-center"><div class="bt-profile-stat-value">%d</div><div class="bt-profile-stat-label">Pages Read</div></div>
                    <div class="metric-card p-2 text-center"><div class="bt-profile-stat-value">%d</div><div class="bt-profile-stat-label">Rereads</div></div>
                    <div class="metric-card p-2 text-center"><div class="bt-profile-stat-value"><span class="bt-rating-badge bt-rating-%s">%s</span></div><div class="bt-profile-stat-label">Avg Rating</div></div>
                </div>
            </div>
            <div class="glass-card p-3 mb-3"><div class="section-title"><i class="bi bi-tags-fill"></i> Top Genres</div>%s</div>
        </div>
        <div class="col-lg-5">
            <div class="glass-card p-3 mb-3"><div class="d-flex justify-content-between align-items-center mb-2"><div class="section-title mb-0"><i class="bi bi-grid-3x3-gap-fill text-primary"></i> Reading Activity</div></div>%s</div>
            <div class="glass-card p-3 mb-3">
                <div class="section-title"><i class="bi bi-trophy-fill text-warning"></i> Reading Challenge %s</div>
                <div class="d-flex align-items-center gap-3">
                    %s
                    <div class="flex-grow-1">
                        <div class="progress-thin" style="height:8px;"><div class="bar" style="width:%d%%;background:linear-gradient(90deg,var(--bt-accent),var(--bt-accent-2));"></div></div>
                        <div class="d-flex justify-content-between small text-muted mt-1"><span>%d / %d books</span><span>%s</span></div>
                    </div>
                </div>
            </div>
            <div class="glass-card p-3 mb-3"><div class="d-flex justify-content-between align-items-center mb-2"><div class="section-title mb-0"><i class="bi bi-journal-text text-info"></i> Recent Diary</div><a href="/diary" class="btn btn-outline btn-sm">View All (%d)</a></div>%s</div>
            <div class="glass-card p-3 mb-3"><div class="d-flex justify-content-between align-items-center mb-2"><div class="section-title mb-0"><i class="bi bi-pencil-fill"></i> Recent Posts</div><span class="text-muted small">%d</span></div>%s</div>
            <div class="glass-card p-3 mb-3"><div class="section-title"><i class="bi bi-bar-chart-fill text-primary"></i> Books by Month</div><div class="chart-container" style="height:180px;"><canvas id="booksByMonthChart"></canvas></div></div>
            <div class="glass-card p-3 mb-3"><div class="section-title"><i class="bi bi-pie-chart-fill text-info"></i> Rating Distribution</div><div class="chart-container" style="height:160px;"><canvas id="ratingDistChart"></canvas></div></div>
        </div>
        <div class="col-lg-3">
            <div class="glass-card p-3 mb-3"><div class="section-title d-flex justify-content-between"><span><i class="bi bi-award-fill text-warning"></i> Badges</span><span class="badge bg-primary">%d / %d</span></div><div class="bt-badges-scroll" style="max-height:280px;overflow-y:auto;">%s</div></div>
            <div class="glass-card p-3 mb-3"><div class="section-title"><i class="bi bi-clock-history text-info"></i> Recent Activity</div><div style="max-height:400px;overflow-y:auto;">%s</div></div>
            %s
        </div>
    </div>
</div>
"""
        # Apply format with proper %% escaping for the avatar HTML
        # First, escape % in the avatar HTML to avoid format key errors
        PA_escaped = PA.replace("%", "%%")
        PC = PCONTENT % (
            PA_escaped,
            h(pu.name),
            '<span class="verified-badge"><i class="bi bi-check"></i></span>'
            if pu.role in ("admin", "librarian")
            else "",
            h(user_id),
            h(pu.role.upper()),
            FB,
            fc,
            flc,
            stats.get("total_read", 0),
            stats.get("total_reviews", 0),
            "%.1f" % stats["avg_rating"] if stats.get("avg_rating") else "-",
            gm_pts,
            h(gm_lev),
            gm_stk,
            CR,
            FGH,
            ' <small class="text-muted">(you)</small>' if is_own else "",
            ds.get("total_books", 0),
            ds.get("total_pages_read", 0),
            ds.get("reread_count", 0),
            ds.get("avg_rating_label", "timepass"),
            ds.get("avg_rating_label", "timepass"),
            vb,
            HS,
            str(datetime.now().year),
            CR if CR else '<span class="text-muted small">Set a reading goal!</span>',
            round(cp / max(1, cg) * 100) if cg > 0 else 0,
            cp,
            cg,
            "On Track!" if cd.get("on_track") else "Behind schedule" if cg > 0 else "",
            dtot,
            DH,
            tp,
            PH,
            unlocked_count,
            total_badges,
            BGH,
            AH,
            SH,
        )
        return render_page(
            pu.name,
            PC
            + """
<!-- Profile Chart.js init and drag/drop handlers -->
<script>
function initProfileCharts() {
  // Books by Month chart
  var bm = document.getElementById("booksByMonthChart");
  if (bm && typeof Chart !== "undefined") {
    fetch("/api/analytics/monthly").then(function(r){ return r.json() }).then(function(d){
      if (d.labels && d.labels.length) {
        new Chart(bm, {
          type: "bar",
          data: {
            labels: d.labels,
            datasets: [{ label: "Books", data: d.values, backgroundColor: "rgba(124,106,247,0.6)", borderColor: "#7c6af7", borderWidth: 2, borderRadius: 4 }]
          },
          options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true, grid: { color: "rgba(0,0,0,0.04)" } }, x: { grid: { display: false } } } }
        });
      }
    }).catch(function(){});
  }
  // Rating Distribution chart
  var rd = document.getElementById("ratingDistChart");
  if (rd && typeof Chart !== "undefined") {
    fetch("/api/reviews/stats").then(function(r){ return r.json() }).then(function(d){
      if (d.labels && d.labels.length) {
        new Chart(rd, {
          type: "doughnut",
          data: {
            labels: d.labels,
            datasets: [{ data: d.values, backgroundColor: ["#ef4444","#f59e0b","#eab308","#10b981","#3b82f6"], borderWidth: 2, borderColor: "transparent", hoverOffset: 6 }]
          },
          options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom", labels: { boxWidth: 10, padding: 6, font: {size: 9}, color: "var(--text-muted)" } } }, cutout: "65%" }
        });
      }
    }).catch(function(){})
}

// Drag and drop handlers for favorite books
function onFavDragStart(ev) {
  ev.dataTransfer.setData("text/plain", ev.currentTarget.getAttribute("data-id"));
  ev.dataTransfer.effectAllowed = "move";
  ev.currentTarget.classList.add("bt-dragging");
}
function onFavDragOver(ev) {
  ev.preventDefault();
  ev.dataTransfer.dropEffect = "move";
  var target = ev.currentTarget;
  if (target.classList.contains("bt-fav-slot")) target.classList.add("bt-drag-over");
}
function onFavDrop(ev) {
  ev.preventDefault();
  var fromId = ev.dataTransfer.getData("text/plain");
  var toSlot = ev.currentTarget;
  if (toSlot.classList.contains("bt-fav-slot-empty")) return;
  var toId = toSlot.getAttribute("data-id");
  if (!fromId || !toId || fromId === toId) return;
  toSlot.classList.remove("bt-drag-over");
  // Save new order
  var grid = document.getElementById("favGrid");
  if (!grid) return;
  var slots = grid.querySelectorAll(".bt-fav-slot");
  var ids = [];
  slots.forEach(function(s){ var id = s.getAttribute("data-id"); if (id) ids.push(id); });
  saveFavOrder(ids);
}
function removeFav(bookId) {
  if (!confirm("Remove this book from favorites?")) return;
  fetch("/api/profile/favorites/remove", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({book_id: bookId})
  }).then(function(r){ return r.json() }).then(function(d){
    if (d.success) { showToast("Removed", "success"); location.reload(); }
    else { showToast(d.error || "Failed", "error"); }
  });
}
function saveFavOrder(ids) {
  fetch("/api/profile/favorites/reorder", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({book_ids: ids})
  }).then(function(r){ return r.json() }).then(function(d){
    if (d.success) location.reload();
  });
}

// Initialize charts when DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initProfileCharts);
} else {
  setTimeout(initProfileCharts, 500);
}

// Toggle follow/unfollow
function toggleFollow(userId, btn) {
  fetch("/api/follow/" + userId, {method: "POST"})
    .then(function(r){ return r.json() })
    .then(function(d){
      if (d.success) {
        if (d.is_following) {
          btn.innerHTML = '<i class="bi bi-person-check"></i> Following';
          btn.className = "btn btn-outline btn-sm";
        } else {
          btn.innerHTML = '<i class="bi bi-person-plus"></i> Follow';
          btn.className = "btn btn-primary btn-sm";
        }
        showToast(d.message, "success");
      } else {
        showToast(d.error || "Failed", "error");
      }
    });
}

// Create a new custom shelf
function createShelf() {
  var name = prompt("Enter shelf name:");
  if (!name || !name.trim()) return;
  fetch("/api/shelves/create", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({name: name.trim(), description: "", icon: "bookmark"})
  }).then(function(r){ return r.json() }).then(function(d){
    if (d.success) { showToast("Shelf created!", "success"); setTimeout(function(){ location.reload(); }, 1000); }
    else { showToast(d.error || "Failed", "error"); }
  });
}

// Delete a custom shelf
function deleteShelf(shelfName) {
  if (!confirm("Delete shelf '" + shelfName + "'? This cannot be undone.")) return;
  fetch("/api/shelves/" + encodeURIComponent(shelfName), {method: "DELETE"})
    .then(function(r){ return r.json() })
    .then(function(d){
      if (d.success) { showToast("Shelf deleted", "success"); setTimeout(function(){ location.reload(); }, 1000); }
      else { showToast(d.error || "Failed", "error"); }
    });
}

// Rename a custom shelf
function renameShelf(shelfName) {
  var newName = prompt("New name for shelf '" + shelfName + "':", shelfName);
  if (!newName || !newName.trim() || newName.trim() === shelfName) return;
  fetch("/api/shelves/" + encodeURIComponent(shelfName) + "/rename", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({new_name: newName.trim()})
  }).then(function(r){ return r.json() }).then(function(d){
    if (d.success) { showToast("Shelf renamed!", "success"); setTimeout(function(){ location.reload(); }, 1000); }
    else { showToast(d.error || "Failed", "error"); }
  });
}

// Favorites search and add
function openFavSearch() {
  var modal = new bootstrap.Modal(document.getElementById("favSearchModal"));
  modal.show();
  setTimeout(function(){ var inp = document.getElementById("favSearchInput"); if (inp) inp.focus(); }, 500);
}

function searchFavBooks(q) {
  if (q.length < 2) { document.getElementById("favSearchResults").innerHTML = ""; return; }
  var resultsDiv = document.getElementById("favSearchResults");
  resultsDiv.innerHTML = '<div class="text-center py-4 text-muted small"><div class="spinner-border spinner-border-sm"></div> Searching...</div>';
  fetch("/api/books?q=" + encodeURIComponent(q))
    .then(function(r){ return r.json() })
    .then(function(books){
      if (!books || !books.length) { resultsDiv.innerHTML = '<div class="text-center py-4 text-muted small">No books found</div>'; return; }
      var favIds = [];
      document.querySelectorAll(".bt-fav-slot[data-id]").forEach(function(s){ var id = s.getAttribute("data-id"); if (id) favIds.push(id); });
      resultsDiv.innerHTML = books.slice(0, 10).map(function(b){
        var disabled = favIds.indexOf(b.book_id) !== -1;
        if (disabled) { return '<div class="search-result-item" style="opacity:.5;"><div class="fw-bold small">' + booktaleUtils.escapeHtml(b.title) + '</div><small class="text-muted">' + booktaleUtils.escapeHtml(b.author) + '</small> <span class="badge bg-secondary">Already added</span></div>'; }
        return '<div class="search-result-item" style="cursor:pointer;" onclick="addFavBook(\'' + booktaleUtils.jsStr(b.book_id) + '\')"><div class="fw-bold small">' + booktaleUtils.escapeHtml(b.title) + '</div><small class="text-muted">' + booktaleUtils.escapeHtml(b.author) + '</small></div>';
      }).join("");
    })
    .catch(function(){ resultsDiv.innerHTML = '<div class="text-center py-4 text-muted small">Search failed</div>'; });
}

function addFavBook(bookId) {
  fetch("/api/profile/favorites/add", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({book_id: bookId})
  }).then(function(r){ return r.json() }).then(function(d){
    if (d.success) { showToast("Added to favorites!", "success"); setTimeout(function(){ location.reload(); }, 800); }
    else { showToast(d.error || "Failed", "error"); }
  });
}
</script>

<!-- Favorites Search Modal -->
<div class="modal fade" id="favSearchModal" tabindex="-1" aria-hidden="true">
<div class="modal-dialog modal-dialog-scrollable"><div class="modal-content">
<div class="modal-header"><h5 class="modal-title"><i class="bi bi-bookmark-plus text-warning me-1"></i> Add to Favorites</h5>
<button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
<div class="modal-body">
<div class="mb-3">
<input type="text" id="favSearchInput" class="form-control" placeholder="Search books by title or author..." oninput="searchFavBooks(this.value)">
</div>
<div id="favSearchResults">
<div class="text-center py-4 text-muted small">Type at least 2 characters to search...</div>
</div>
</div>
<div class="modal-footer">
<small class="text-muted">You can have up to 4 favorite books.</small>
<button class="btn btn-outline" data-bs-dismiss="modal">Close</button>
</div>
</div></div></div>
""",
        )

    # ═══════════════════════════════════════════════════════════
    # LISTS API
    # ═══════════════════════════════════════════════════════════

    @app.route("/api/lists", methods=["POST"])
    @login_required
    # Abuse ceiling: list-creation spam (public lists are shared surface).
    @_rate_limit("30 per minute")
    def api_create_list():
        uid = session["user_id"]
        if not book_lists:
            return jsonify({"success": False, "error": "Lists module not available"})
        data = request.get_json() or {}
        ok, msg, lst = book_lists.create_list(
            uid,
            data.get("name", ""),
            data.get("description", ""),
            data.get("is_public", True),
            data.get("list_type", "custom"),
        )
        return jsonify({"success": ok, "message": msg, "list": lst})

    @app.route("/api/lists/<list_id>", methods=["GET", "PUT", "DELETE"])
    @login_required
    def api_list_ops(list_id):
        uid = session["user_id"]
        if not book_lists:
            return jsonify({"success": False, "error": "Lists module not available"})
        if request.method == "GET":
            lst = book_lists.get_list(list_id)
            if not lst:
                return jsonify({"error": "List not found"}), 404
            books_data = storage.load_books()
            enriched = []
            for b in lst.get("books", []):
                book = books_data.get(b["book_id"])
                if book:
                    enriched.append(
                        {
                            **b,
                            "category": book.category,
                            "available": book.available_copies,
                        }
                    )
            lst["books"] = enriched
            return jsonify(lst)
        elif request.method == "PUT":
            data = request.get_json() or {}
            ok, msg = book_lists.update_list(
                list_id,
                uid,
                data.get("name"),
                data.get("description"),
                data.get("is_public"),
            )
            return jsonify({"success": ok, "message": msg})
        else:
            ok, msg = book_lists.delete_list(list_id, uid)
            return jsonify({"success": ok, "message": msg})

    @app.route("/api/lists/<list_id>/books", methods=["POST", "DELETE"])
    @login_required
    def api_list_books(list_id):
        uid = session["user_id"]
        if not book_lists:
            return jsonify({"success": False, "error": "Lists module not available"})
        data = request.get_json() or {}
        if request.method == "POST":
            ok, msg = book_lists.add_book_to_list(
                list_id, data.get("book_id", ""), uid, data.get("note", "")
            )
        else:
            ok, msg = book_lists.remove_book_from_list(
                list_id, data.get("book_id", ""), uid
            )
        return jsonify({"success": ok, "message": msg})

    @app.route("/api/lists/<list_id>/follow", methods=["POST"])
    @login_required
    # Abuse ceiling: mass list follow/unfollow churn.
    @_rate_limit("60 per minute")
    def api_list_follow(list_id):
        uid = session["user_id"]
        if not book_lists:
            return jsonify({"success": False, "error": "Lists module not available"})
        data = request.get_json() or {}
        if data.get("unfollow"):
            ok, msg = book_lists.unfollow_list(list_id, uid)
        else:
            ok, msg = book_lists.follow_list(list_id, uid)
        return jsonify({"success": ok, "message": msg})

    @app.route("/api/lists/<list_id>/upvote", methods=["POST"])
    @login_required
    # Abuse ceiling: list upvote-stuffing (engagement manipulation).
    @_rate_limit("60 per minute")
    def api_list_upvote(list_id):
        uid = session["user_id"]
        if not book_lists:
            return jsonify({"success": False, "error": "Lists module not available"})
        ok, msg, is_upvoted = book_lists.upvote_list(list_id, uid)
        return jsonify({"success": ok, "message": msg, "is_upvoted": is_upvoted})

    @app.route("/api/lists/my")
    @login_required
    def api_my_lists():
        uid = session["user_id"]
        if not book_lists:
            return jsonify({"lists": []})
        return jsonify({"lists": book_lists.get_user_lists(uid)})

    @app.route("/api/lists/trending")
    @login_required
    def api_lists_trending():
        if not book_lists:
            return jsonify({"lists": []})
        return jsonify({"lists": book_lists.get_trending_lists(10)})

    @app.route("/api/lists/weekly-books")
    @login_required
    def api_weekly_books():
        if not book_lists:
            return jsonify({"books": []})
        return jsonify({"books": book_lists.get_weekly_trending_books(10)})

    @app.route("/api/lists/public")
    @login_required
    def api_public_lists():
        if not book_lists:
            return jsonify({"lists": []})
        return jsonify({"lists": book_lists.get_public_lists()})
