"""
social_api.py - Social Feed, Post CRUD, Upload, Follow, Hashtags, Comments, Search, and Lists API.
Extracted from social_routes.py for focused maintenance.
"""

import os
import uuid

from flask import jsonify, request, session

from app.config.settings import Config
from app.core.logger import log
from app.realtime.realtime import get_realtime
from app.routes.social_shared import (
    _verify_and_reencode_image,
    avatar_html,
    gamification,
    login_required,
    notif_mgr,
    review_mgr,
    social,
    storage,
    time_ago,
)

# Re-export module-level refs that init_social_routes may mutate at startup.
from app.routes.social_shared import lib  # noqa: F401
from app.routes.social_shared import book_lists  # noqa: F401


def register_social_api_routes(app, _rate_limit):
    """Register all JSON API endpoints on *app*.

    Parameters
    ----------
    app : Flask
        The application instance.
    _rate_limit : callable
        A rate-limit decorator factory (no-op fallback if flask-limiter is
        missing).
    """

    # ═══ FEED API ═══

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
        post = social.create_post(uid, content, post_type=ptype, book_ids=bids, image_urls=imgs)
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
        except (OSError, ValueError, KeyError):
            pass
        return jsonify({"success": True, "post": post})

    @app.route("/api/upload", methods=["POST"])
    @login_required
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

        ok, data, out_ext = _verify_and_reencode_image(file)
        if not ok:
            log(
                f"Upload rejected (not a valid image): {file.filename} ({utype})",
                uid,
            )
            return jsonify({"success": False, "error": "File is not a valid image"})
        if out_ext is None:
            out_ext = ext
        safe_name = f"{uid}_{uuid.uuid4().hex[:12]}{out_ext}"
        subdir = "avatars" if utype == "avatar" else "post_images"
        save_dir = os.path.join(Config.UPLOADS_DIR, subdir)
        os.makedirs(save_dir, exist_ok=True)
        dest_path = os.path.join(save_dir, safe_name)
        if data is None:
            file.save(dest_path)
        else:
            with open(dest_path, "wb") as f:
                f.write(data)
        url_path = f"/uploads/{subdir}/{safe_name}"
        log(f"Uploaded {url_path} ({utype}, {file.filename})", uid)
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
    @_rate_limit("30 per minute")
    def api_repost(post_id):
        ok, msg, repost = social.repost_post(post_id, session["user_id"])
        return jsonify({"success": ok, "message": msg, "repost": repost})

    @app.route("/api/posts/<post_id>/like", methods=["POST"])
    @login_required
    @_rate_limit("60 per minute")
    def api_like_post(post_id):
        uid = session["user_id"]
        ok, msg, is_liked = social.like_post(post_id, uid)
        post = social.get_post(post_id)
        lc = len(post.get("likes", [])) if post else 0
        rt = get_realtime()
        if rt:
            rt.emit_like_update(post_id, uid, is_liked, lc)
        return jsonify({"success": ok, "message": msg, "is_liked": is_liked, "likes_count": lc})

    @app.route("/api/posts/<post_id>/vote", methods=["POST"])
    @login_required
    @_rate_limit("60 per minute")
    def api_vote_post(post_id):
        data = request.get_json() or {}
        ok, msg, ns = social.vote_post(post_id, session["user_id"], data.get("vote", "up"))
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
                                "message": "%s commented on your post" % (uu.name if uu else uid),
                                "post_id": post_id,
                            },
                        )
                try:
                    if gamification:
                        gamification.on_comment_created(uid)
                # Optional sub-feature: degrade gracefully, never break the request.
                except (OSError, ValueError, KeyError):
                    pass
                return jsonify({"success": True, "comment": comment, "message": msg})
            return jsonify({"success": False, "error": msg})

    # ═══ FOLLOW / HASHTAGS ═══

    @app.route("/api/follow/<user_id>", methods=["POST"])
    @login_required
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
        return jsonify({"success": ok, "message": msg, "is_following": not is_following})

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

    # ═══ ADVANCED SEARCH ═══

    @app.route("/api/search/suggestions")
    @login_required
    def api_search_suggestions():
        from app.routes.social_shared import lib as _lib

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
        from app.routes.social_shared import lib as _lib

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
            books_result = _lib.search_books(
                query=q, category=cat, available_only=avail, sort_by=sort_by
            )
            total = len(books_result)
            start = (page - 1) * pp
            result["books"] = {
                "results": [b.to_dict() for b in books_result[start : start + pp]],
                "total": total,
            }
        if entity in ("all", "users") and q:
            users_result = _lib.search_users(query=q)
            total = len(users_result)
            start = (page - 1) * pp
            users_page = []
            for u in users_result[start : start + pp]:
                ud = u.to_dict()
                ud.pop("password_hash", None)
                users_page.append(ud)
            result["users"] = {"results": users_page, "total": total}
        if entity in ("all", "posts") and q:
            posts_result, posts_total = social.search_posts(q, uid, page=page, per_page=pp)
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
        ok, msg, comment = social.add_comment(parent["post_id"], uid, content, parent_id=comment_id)
        return jsonify({"success": ok, "message": msg, "comment": comment})

    # ═══ LISTS API ═══

    @app.route("/api/lists", methods=["POST"])
    @login_required
    @_rate_limit("30 per minute")
    def api_create_list():
        from app.routes.social_shared import book_lists as _bl

        uid = session["user_id"]
        if not _bl:
            return jsonify({"success": False, "error": "Lists module not available"})
        data = request.get_json() or {}
        ok, msg, lst = _bl.create_list(
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
        from app.routes.social_shared import book_lists as _bl

        uid = session["user_id"]
        if not _bl:
            return jsonify({"success": False, "error": "Lists module not available"})
        if request.method == "GET":
            lst = _bl.get_list(list_id)
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
            ok, msg = _bl.update_list(
                list_id,
                uid,
                data.get("name"),
                data.get("description"),
                data.get("is_public"),
            )
            return jsonify({"success": ok, "message": msg})
        else:
            ok, msg = _bl.delete_list(list_id, uid)
            return jsonify({"success": ok, "message": msg})

    @app.route("/api/lists/<list_id>/books", methods=["POST", "DELETE"])
    @login_required
    def api_list_books(list_id):
        from app.routes.social_shared import book_lists as _bl

        uid = session["user_id"]
        if not _bl:
            return jsonify({"success": False, "error": "Lists module not available"})
        data = request.get_json() or {}
        if request.method == "POST":
            ok, msg = _bl.add_book_to_list(
                list_id, data.get("book_id", ""), uid, data.get("note", "")
            )
        else:
            ok, msg = _bl.remove_book_from_list(list_id, data.get("book_id", ""), uid)
        return jsonify({"success": ok, "message": msg})

    @app.route("/api/lists/<list_id>/follow", methods=["POST"])
    @login_required
    @_rate_limit("60 per minute")
    def api_list_follow(list_id):
        from app.routes.social_shared import book_lists as _bl

        uid = session["user_id"]
        if not _bl:
            return jsonify({"success": False, "error": "Lists module not available"})
        data = request.get_json() or {}
        if data.get("unfollow"):
            ok, msg = _bl.unfollow_list(list_id, uid)
        else:
            ok, msg = _bl.follow_list(list_id, uid)
        return jsonify({"success": ok, "message": msg})

    @app.route("/api/lists/<list_id>/upvote", methods=["POST"])
    @login_required
    @_rate_limit("60 per minute")
    def api_list_upvote(list_id):
        from app.routes.social_shared import book_lists as _bl

        uid = session["user_id"]
        if not _bl:
            return jsonify({"success": False, "error": "Lists module not available"})
        ok, msg, is_upvoted = _bl.upvote_list(list_id, uid)
        return jsonify({"success": ok, "message": msg, "is_upvoted": is_upvoted})

    @app.route("/api/lists/my")
    @login_required
    def api_my_lists():
        from app.routes.social_shared import book_lists as _bl

        uid = session["user_id"]
        if not _bl:
            return jsonify({"lists": []})
        return jsonify({"lists": _bl.get_user_lists(uid)})

    @app.route("/api/lists/trending")
    @login_required
    def api_lists_trending():
        from app.routes.social_shared import book_lists as _bl

        if not _bl:
            return jsonify({"lists": []})
        return jsonify({"lists": _bl.get_trending_lists(10)})

    @app.route("/api/lists/weekly-books")
    @login_required
    def api_weekly_books():
        from app.routes.social_shared import book_lists as _bl

        if not _bl:
            return jsonify({"books": []})
        return jsonify({"books": _bl.get_weekly_trending_books(10)})

    @app.route("/api/lists/public")
    @login_required
    def api_public_lists():
        from app.routes.social_shared import book_lists as _bl

        if not _bl:
            return jsonify({"lists": []})
        return jsonify({"lists": _bl.get_public_lists()})
