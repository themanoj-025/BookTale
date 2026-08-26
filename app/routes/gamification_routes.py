"""
gamification_routes.py - Page routes: Feed, Search, Profile, Author, Profile Edit.
Includes gamification renderers (heatmap, badges, diary, favorites grid).
Extracted from social_routes.py for focused maintenance.
"""

import contextlib
import html
import json
import os
from datetime import datetime, timedelta

from flask import jsonify, request, session

from app.config.settings import Config
from app.core.logger import log
from app.routes.social_shared import (
    _render_badges_grid,
    _render_diary_entries,
    _render_fav_grid,
    _render_heatmap_svg,
    avatar_html,
    cat_color,
    gamification,
    get_current_user,
    login_required,
    notif_mgr,
    render_page,
    review_mgr,
    social,
    storage,
)
from app.routes.helpers import h


def register_gamification_routes(app, _rate_limit):
    """Register page routes on *app*.

    Parameters
    ----------
    app : Flask
        The application instance.
    _rate_limit : callable
        A rate-limit decorator factory.
    """

    # ═══ FEED PAGE ═══

    @app.route("/feed")
    @login_required
    def feed_page():
        FEED_CONTENT = """<!-- Compose Box -->
<div class="compose-box animate-in">
  <form class="w-100" onsubmit="return submitPost()">
    <textarea id="postContent" class="w-100" placeholder="What\\'s happening?" aria-label="What\\'s happening?" rows="2" style="border:none;resize:none;font-size:1.1rem;padding:8px 0;background:transparent;color:var(--text);outline:none;font-family:var(--font);min-height:50px;"></textarea>
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
"""
        return render_page(
            "Social Feed",
            FEED_CONTENT
            + """
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
        c.innerHTML = '<div class="empty-state empty-state-variant py-5"><div class="empty-icon"><i class="bi bi-inbox"></i></div><div class="empty-title">No posts yet</div><div class="empty-desc">Follow users or be the first to share what you are reading!</div><button class="empty-cta" onclick="document.getElementById(\\'postContent\\')?.focus()"><i class="bi bi-feather"></i> Create a Post</button></div>';
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
        html += '<button class="post-action' + likedClass + '" onclick="likePost(\\'' + p.post_id + '\\',this)"><i class="bi bi-heart-fill"></i> ' + (p.likes_count || 0) + '</button>';
        html += '<button class="post-action" onclick="window.location.href=\\'/profile/' + p.user_id + '\\'"><i class="bi bi-chat-fill"></i> ' + (p.comment_count || 0) + '</button>';
        html += '</div></div></article>';
      });
      c.innerHTML = html;
    })
    .catch(function() {
      c.innerHTML = '<div class="empty-state empty-state-variant py-5"><div class="empty-icon"><i class="bi bi-wifi-off"></i></div><div class="empty-title">Could not load feed</div><div class="empty-desc">Check your connection and try again.</div><button class="empty-cta" onclick="loadFeed(\\'following\\',1)"><i class="bi bi-arrow-clockwise"></i> Retry</button></div>';
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

    # ═══ SEARCH PAGE ═══

    @app.route("/search")
    @login_required
    def search_page():
        return render_page(
            "Search",
            '<div class="empty-state empty-state-variant py-5"><div class="empty-icon"><i class="bi bi-search" style="font-size:3rem;"></i></div><div class="empty-title">Search Books &amp; People</div><div class="empty-desc">Use the search overlay (Ctrl+K) to find books, users, and more.</div><button class="empty-cta" onclick="openSearchOverlay()"><i class="bi bi-search me-2"></i>Open Search</button></div>',
        )

    # ═══ PROFILE EDIT PAGE ═══

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
                            <button class="btn btn-outline" type="button" onclick="document.getElementById(\\'editProfilePic\\').value=\\'\\';previewAvatar(\\'\\')"><i class="bi bi-x-lg"></i></button>
                        </div>
                        <small class="text-muted">Enter a URL, or upload an image below</small>
                    </div>
                    <div class="mb-3 p-3" style="border:2px dashed var(--border);border-radius:12px;text-align:center;">
                        <label class="form-label d-block">Upload New Avatar</label>
                        <input type="file" id="avatarUploadInput" accept="image/jpeg,image/png,image/gif,image/webp" style="display:none;" onchange="uploadAvatar(this)">
                        <button class="btn btn-outline" type="button" onclick="document.getElementById(\\'avatarUploadInput\\').click()">
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
</div>"""
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
        CONTENT += """
<script>
function saveProfile() {
    var btn = document.getElementById("saveProfileBtn");
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Saving...';
    var data = {
        name: document.getElementById("editName").value.trim(),
        email: document.getElementById("editEmail").value.trim(),
        phone: document.getElementById("editPhone").value.trim(),
        website: document.getElementById("editWebsite").value.trim(),
        location: document.getElementById("editLocation").value.trim(),
        bio: document.getElementById("editBio").value.trim(),
        profile_picture: document.getElementById("editProfilePic").value.trim()
    };
    if (!data.name) { showToast("Name is required", "error"); btn.disabled = false; btn.innerHTML = '<i class="bi bi-check-lg"></i> Save Changes'; return false; }
    fetch("/api/profile/update", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(data)
    }).then(function(r){ return r.json() }).then(function(d){
        if (d.success) {
            showToast("Profile updated!", "success");
            setTimeout(function(){ window.location.href = '/profile/""" + h(uid) + """'; }, 1000);
        } else {
            showToast(d.error || "Failed to update", "error");
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-check-lg"></i> Save Changes';
        }
    }).catch(function(){
        showToast("Network error", "error");
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-check-lg"></i> Save Changes';
    });
    return false;
}
function previewAvatar(url) {
    var preview = document.getElementById("avatarPreview");
    if (url) {
        preview.innerHTML = '<div class="avatar" style="width:64px;height:64px;background-size:cover;background-image:url(' + encodeURI(url) + ');border-radius:50%;border:3px solid var(--bg);box-shadow:0 4px 12px rgba(0,0,0,.1);"></div>';
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
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Uploading...';
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
            status.innerHTML = '<span class="text-success"><i class="bi bi-check-circle"></i> Uploaded!</span> ' + d.url;
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
        return render_page("Edit Profile", CONTENT)

    # ═══ AUTHOR PAGE ═══

    @app.route("/author/<author_name>")
    @login_required
    def author_page(author_name):
        from urllib.parse import unquote
        from collections import Counter

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
                '<a href="/books/{}" class="text-decoration-none col-6 col-md-4 col-lg-3 mb-2">'
                '<div class="glass-card p-2 text-center" style="cursor:pointer;">'
                '<div style="font-size:1.2rem;color:{};"><i class="bi bi-book-fill"></i></div>'
                '<div class="fw-bold small">{}</div>'
                '<small class="text-muted">{}</small>'
                '<div class="mt-1">{}</div>'
                '</div></a>'.format(b.book_id, cc, h(b.title)[:40], h(b.category), avail)
            )
        if not BOOKS_GRID:
            BOOKS_GRID = '<div class="col-12"><div class="empty-state empty-state-variant"><div class="empty-icon"><i class="bi bi-book"></i></div><div class="empty-title">No books found</div><div class="empty-desc">This author has no books in the library yet.</div></div></div>'
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

    # ═══ PROFILE PAGE (Phase 4 Showcase) ═══

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
            except (OSError, ValueError, KeyError):
                pass
        # Diary
        de = []
        dtot = 0
        try:
            from app.services.reading.diary import DiaryManager

            de, dtot = DiaryManager(storage).get_user_diary(user_id, page=1, per_page=5)
        except (OSError, ValueError, KeyError):
            pass
        # Challenge
        cd = {}
        try:
            from app.services.reading.reading_challenge import ReadingChallenge

            cd = ReadingChallenge(storage).get_goal(user_id, datetime.now().year)
        except (OSError, ValueError, KeyError):
            pass
        ds = {}
        with contextlib.suppress(Exception):
            ds = DiaryManager(storage).get_stats(user_id)
        favs = getattr(pu, "favorite_books", [])
        shelves = review_mgr.get_user_shelf(user_id)
        sc = review_mgr.get_shelf_counts(user_id)

        # Posts
        posts, tp = social.get_user_posts(user_id, uid, page=1, per_page=5)
        PH = ""
        for p in posts:
            PH += (
                '<div class="glass-card p-3 mb-2" style="animation:cardEnter .3s ease both;">'
                '<div style="font-size:.9rem;">%s</div>'
                '<div class="d-flex gap-2 mt-2" style="font-size:.75rem;color:var(--text-muted);">'
                '<span>\u2764\ufe0f %d</span><span>\U0001f4ac %d</span><span>%s</span>'
                '</div></div>'
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
                '<div class="activity-item"><div class="activity-icon" style="background:#f59e0b20;color:#f59e0b;"><i class="bi bi-star-fill"></i></div>'
                '<div class="flex-grow-1"><div style="font-size:.85rem;"><strong>{}</strong> {}</div>'
                '<div style="font-size:.75rem;color:var(--text-muted);">Reviewed {}</div></div></div>'.format(
                    h(r.get("book_title", "")), stars, r.get("time_ago", "")
                )
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
                with open(hm_path, encoding="utf-8") as f:
                    he = json.load(f)
            except (OSError, json.JSONDecodeError):
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
        except (OSError, ValueError, KeyError, TypeError):
            HS = '<div class="text-center text-muted small py-3">Heatmap unavailable</div>'

        # Follow button
        FB = ""
        if not is_own:
            if is_following:
                FB = '<button class="btn btn-outline btn-sm" onclick="toggleFollow(\'%s\',this)"><i class="bi bi-person-check"></i> Following</button>' % h(user_id)
            else:
                FB = '<button class="btn btn-primary btn-sm" onclick="toggleFollow(\'%s\',this)"><i class="bi bi-person-plus"></i> Follow</button>' % h(user_id)

        if pu.profile_picture:
            PA = '<div class="avatar" style="width:72px;height:72px;background-size:cover;background-image:url(%s);border-radius:50%;border:3px solid var(--bg);box-shadow:0 4px 12px rgba(0,0,0,.1);" title="%s"></div>' % (
                h(pu.profile_picture), h(pu.name),
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
                        '<a href="/books/{}" class="text-decoration-none"><div class="shelf-book" style="border-left:3px solid {};"><div class="fw-bold" style="font-size:.8rem;">{}</div><small class="text-muted">{}</small></div></a>'.format(
                            h(b["book_id"]), col, h(b["title"]), h(b["author"])
                        )
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
                    '<a href="/books/{}" class="text-decoration-none"><div class="shelf-book" style="border-left:3px solid {};"><div class="fw-bold" style="font-size:.8rem;">{}</div><small class="text-muted">{}</small></div></a>'.format(
                        h(b["book_id"]), col, h(b["title"]), h(b["author"])
                    )
                    for b in bis
                )
            )
            if not sh_section:
                sh_section = '<div class="text-center text-muted small py-3">Empty shelf.</div>'
            db = (
                '<button class="btn btn-sm" style="background:none;border:none;color:var(--text-dim);font-size:.65rem;padding:0;" onclick="deleteShelf(\'%s\')" title="Delete shelf"><i class="bi bi-trash"></i></button>' % h(name)
                if is_own
                else ""
            )
            eb = (
                '<button class="btn btn-sm" style="background:none;border:none;color:var(--text-dim);font-size:.65rem;padding:0;" onclick="renameShelf(\'%s\')" title="Rename shelf"><i class="bi bi-pencil"></i></button>' % h(name)
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
        PA_escaped = PA.replace("%", "%%")
        PC = PCONTENT % (
            PA_escaped,
            h(pu.name),
            (
                '<span class="verified-badge"><i class="bi bi-check"></i></span>'
                if pu.role in ("admin", "librarian")
                else ""
            ),
            h(user_id),
            h(pu.role.upper()),
            FB,
            fc,
            flc,
            stats.get("total_read", 0),
            stats.get("total_reviews", 0),
            "{:.1f}".format(stats["avg_rating"]) if stats.get("avg_rating") else "-",
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
<script>
function initProfileCharts() {
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
}
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
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initProfileCharts);
} else {
  setTimeout(initProfileCharts, 500);
}
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
function deleteShelf(shelfName) {
  if (!confirm("Delete shelf '" + shelfName + "'? This cannot be undone.")) return;
  fetch("/api/shelves/" + encodeURIComponent(shelfName), {method: "DELETE"})
    .then(function(r){ return r.json() })
    .then(function(d){
      if (d.success) { showToast("Shelf deleted", "success"); setTimeout(function(){ location.reload(); }, 1000); }
      else { showToast(d.error || "Failed", "error"); }
    });
}
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
        return '<div class="search-result-item" style="cursor:pointer;" onclick="addFavBook(\\'' + booktaleUtils.jsStr(b.book_id) + '\\')"><div class="fw-bold small">' + booktaleUtils.escapeHtml(b.title) + '</div><small class="text-muted">' + booktaleUtils.escapeHtml(b.author) + '</small></div>';
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
