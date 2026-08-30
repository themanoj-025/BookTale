"""
wishlist_routes.py - Wishlist / Suggestions pages and API endpoints.
Extracted from feature_routes.py for focused maintenance.
"""

from flask import jsonify, request, session

from app.routes.feature_shared import _wishlist, _storage, h, _js_str
from flask import Response


def register_wishlist_routes(app, login_required, admin_required, render_page, _rate_limit) -> None:
    """Register wishlist and suggestion routes on *app*."""

    @app.route("/wishlist")
    @login_required
    def wishlist_page() -> str:
        uid = session["user_id"]
        status = request.args.get("status", "")
        sort_by = request.args.get("sort", "score")
        page = max(1, int(request.args.get("page", 1)))
        suggestions, _total = _wishlist.get_suggestions(status=status, page=page, sort_by=sort_by)
        user_votes = {}
        for s in suggestions:
            if uid in s.get("upvotes", []):
                user_votes[s["suggestion_id"]] = "up"
            elif uid in s.get("downvotes", []):
                user_votes[s["suggestion_id"]] = "down"
            else:
                user_votes[s["suggestion_id"]] = "none"

        stats = _wishlist.get_suggestion_stats()
        trending = _wishlist.get_trending_suggestions(5)

        STAT_BAR = (
            '<div class="stats-bar mb-3 animate-in">'
            '<div class="stat-item"><div class="num">' + str(stats["total"]) + '</div><div class="desc">Total</div></div>'
            '<div class="stat-item"><div class="num text-warning">' + str(stats["pending"]) + '</div><div class="desc">Pending</div></div>'
            '<div class="stat-item"><div class="num text-success">' + str(stats["approved"]) + '</div><div class="desc">Approved</div></div>'
            '<div class="stat-item"><div class="num text-danger">' + str(stats["rejected"]) + '</div><div class="desc">Rejected</div></div>'
            '<div class="stat-item"><div class="num">' + str(stats["unique_suggesters"]) + '</div><div class="desc">Suggesters</div></div>'
            '</div>'
        )

        TRENDING_HTML = ""
        for s in trending[:5]:
            TRENDING_HTML += (
                '<div class="d-flex align-items-center gap-2 mb-2 p-1" style="border-bottom:1px solid var(--border);">'
                '<div style="width:24px;height:24px;border-radius:6px;background:#f59e0b20;display:flex;align-items:center;justify-content:center;flex-shrink:0;"><i class="bi bi-fire" style="color:#f59e0b;font-size:.6rem;"></i></div>'
                '<div class="flex-grow-1" style="min-width:0;"><div class="fw-bold small">' + h(s["title"])[:50] + '</div><small class="text-muted">' + (s.get("author", "")[:30]) + '</small></div>'
                '<span class="badge bg-warning text-dark">+' + str(len(s.get("upvotes", []))) + '</span>'
                '</div>'
            )
        if not TRENDING_HTML:
            TRENDING_HTML = '<div class="text-center text-muted small py-3">No trending suggestions.</div>'

        SUGGESTIONS_HTML = ""
        for s in suggestions:
            score = len(s.get("upvotes", [])) - len(s.get("downvotes", []))
            status_badges = {
                "pending": '<span class="badge bg-warning text-dark">⏳ Pending</span>',
                "approved": '<span class="badge bg-success">✅ Approved</span>',
                "rejected": '<span class="badge bg-danger">❌ Rejected</span>',
                "purchased": '<span class="badge bg-info">📦 Purchased</span>',
            }
            sb = status_badges.get(s["status"], "")
            uv = user_votes.get(s["suggestion_id"], "none")
            up_class = "upvoted" if uv == "up" else ""
            down_class = "downvoted" if uv == "down" else ""
            score_cls = "positive" if score > 0 else ("negative" if score < 0 else "")
            reason_html = (
                '<p class="small text-muted mt-1 mb-0">' + h(s.get("reason", "")) + '</p>'
                if s.get("reason")
                else ""
            )
            comments_badge = (
                '<span class="text-info">💬 ' + str(len(s.get("comments", []))) + '</span>'
                if s.get("comments")
                else ""
            )
            admin_html = (
                '<div class="mt-2 p-2" style="background:rgba(79,70,229,.04);border-radius:8px;">'
                '<small><strong>Admin:</strong> ' + h(s.get("admin_notes", "")) + '</small></div>'
                if s.get("admin_notes")
                else ""
            )
            mod_buttons = ""
            if session.get("role") == "admin" and s["status"] == "pending":
                _sid = _js_str(s["suggestion_id"])
                mod_buttons = (
                    '<button class="btn btn-sm btn-success" onclick="moderateSuggestion(\'' + _sid + '\',\'approved\')"><i class="bi bi-check-lg"></i> Approve</button>'
                    '<button class="btn btn-sm btn-danger" onclick="moderateSuggestion(\'' + _sid + '\',\'rejected\')"><i class="bi bi-x-lg"></i> Reject</button>'
                )
            cat_badge = ('<span>🔖 ' + h(s.get('category', '')) + '</span>') if s.get('category') else ''
            SUGGESTIONS_HTML += (
                '<div class="glass-card p-3 mb-2">'
                '<div class="d-flex gap-3">'
                '<div class="vote-column" style="min-width:40px;">'
                '<button class="vote-btn ' + up_class + '" onclick="voteSuggestion(\'' + _js_str(s["suggestion_id"]) + '\',\'up\',this)"><i class="bi bi-arrow-up-short"></i></button>'
                '<span class="vote-score ' + score_cls + '">' + str(score) + '</span>'
                '<button class="vote-btn ' + down_class + '" onclick="voteSuggestion(\'' + _js_str(s["suggestion_id"]) + '\',\'down\',this)"><i class="bi bi-arrow-down-short"></i></button>'
                '</div>'
                '<div class="flex-grow-1" style="min-width:0;">'
                '<div class="d-flex justify-content-between align-items-start">'
                '<div><h6 class="fw-bold mb-0">' + h(s["title"]) + '</h6>'
                '<small class="text-muted">' + (h(s.get("author", "")) if s.get("author") else "") + '</small></div>'
                + sb +
                '</div>'
                + reason_html +
                '<div class="d-flex gap-2 mt-2 align-items-center" style="font-size:.75rem;color:var(--text-muted);">'
                '<span>👤 ' + h(s.get("suggester_name", "")) + '</span>'
                + cat_badge +
                '<span>📅 ' + (s.get("created_at", "")[:10]) + '</span>'
                + comments_badge +
                '</div>'
                + admin_html +
                '<div class="d-flex gap-1 mt-2">'
                + mod_buttons +
                '<button class="btn btn-sm btn-outline" onclick="showSuggestionComments(\'' + _js_str(s["suggestion_id"]) + '\')"><i class="bi bi-chat"></i> Comment</button>'
                '</div></div></div></div>'
            )
        if not SUGGESTIONS_HTML:
            SUGGESTIONS_HTML = (
                '<div class="empty-state empty-state-variant">'
                '<div class="empty-icon"><i class="bi bi-lightbulb"></i></div>'
                '<div class="empty-title">No suggestions yet</div>'
                '<div class="empty-desc">Be the first to suggest a book for the library!</div>'
                '<button class="empty-cta" onclick="showSuggestForm()"><i class="bi bi-plus-lg"></i> Suggest a Book</button>'
                '</div>'
            )

        active_all = "active" if not status else ""
        active_pending = "active" if status == "pending" else ""
        active_approved = "active" if status == "approved" else ""
        active_rejected = "active" if status == "rejected" else ""
        STATUS_TABS = (
            '<div class="d-flex border-bottom mb-3 gap-2">'
            '<a href="/wishlist?status=" class="feed-tab ' + active_all + '">All</a>'
            '<a href="/wishlist?status=pending" class="feed-tab ' + active_pending + '">⏳ Pending</a>'
            '<a href="/wishlist?status=approved" class="feed-tab ' + active_approved + '">✅ Approved</a>'
            '<a href="/wishlist?status=rejected" class="feed-tab ' + active_rejected + '">❌ Rejected</a>'
            '</div>'
        )

        CONTENT = (
            '<div class="animate-in">'
            '<div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">'
            '<h4 class="fw-bold mb-0"><i class="bi bi-lightbulb-fill me-2 text-warning"></i>Book Wishlist & Suggestions</h4>'
            '<button class="btn btn-primary btn-sm" onclick="showSuggestForm()"><i class="bi bi-plus-lg"></i> Suggest a Book</button>'
            '</div>'
            + STAT_BAR + STATUS_TABS +
            '<div class="row">'
            '<div class="col-lg-9">' + SUGGESTIONS_HTML + '</div>'
            '<div class="col-lg-3">'
            '<div class="glass-card p-3" style="position:sticky;top:4.5rem;">'
            '<div class="section-title"><i class="bi bi-fire text-danger"></i> Trending Suggestions</div>'
            + TRENDING_HTML +
            '</div></div></div></div>'
        )

        # Modal + JS (no f-string)
        CONTENT += (
            '<div class="modal fade" id="suggestModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content">'
            '<div class="modal-header"><h5 class="modal-title"><i class="bi bi-lightbulb text-warning me-1"></i> Suggest a Book</h5>'
            '<button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>'
            '<div class="modal-body">'
            '<div class="mb-3"><label class="form-label">Book Title *</label><input type="text" id="suggestTitle" class="form-control" placeholder="e.g. The Great Gatsby" required></div>'
            '<div class="mb-3"><label class="form-label">Author</label><input type="text" id="suggestAuthor" class="form-control" placeholder="F. Scott Fitzgerald"></div>'
            '<div class="mb-3"><label class="form-label">Why should we add this?</label><textarea id="suggestReason" class="form-control" rows="3" placeholder="Tell us why this book should be in the library..."></textarea></div>'
            '<div class="row">'
            '<div class="col-md-6 mb-3"><label class="form-label">ISBN</label><input type="text" id="suggestIsbn" class="form-control" placeholder="Optional"></div>'
            '<div class="col-md-6 mb-3"><label class="form-label">Category</label><select id="suggestCategory" class="form-select"><option value="">Any</option>'
        )
        for c in ["Fiction", "Non-Fiction", "Science", "History", "Biography", "Philosophy", "Technology", "Other"]:
            CONTENT += '<option value="' + c + '">' + c + '</option>'
        CONTENT += (
            '</select></div></div>'
            '</div>'
            '<div class="modal-footer">'
            '<button class="btn btn-outline" data-bs-dismiss="modal">Cancel</button>'
            '<button class="btn btn-primary" onclick="submitSuggestion()"><i class="bi bi-send"></i> Submit</button>'
            '</div></div></div></div>'
            '<script>'
            'function showSuggestForm(){var m=new bootstrap.Modal(document.getElementById("suggestModal"));m.show()}'
            'function submitSuggestion(){'
            'var t=document.getElementById("suggestTitle").value.trim();'
            "if(!t){showToast('Enter a book title','error');return}"
            "fetch('/api/wishlist/suggest',{"
            "method:'POST',headers:{'Content-Type':'application/json'},"
            "body:JSON.stringify({title:t,"
            "author:document.getElementById('suggestAuthor').value.trim(),"
            "reason:document.getElementById('suggestReason').value.trim(),"
            "isbn:document.getElementById('suggestIsbn').value.trim(),"
            "category:document.getElementById('suggestCategory').value})"
            "}).then(r=>r.json()).then(function(d){"
            "if(d.success){showToast(d.message,'success');setTimeout(function(){location.reload()},1200)}"
            "else{showToast(d.error,'error')}"
            "});}"
            "function voteSuggestion(sid,vote,btn){"
            "fetch('/api/wishlist/'+sid+'/vote',{"
            "method:'POST',headers:{'Content-Type':'application/json'},"
            "body:JSON.stringify({vote:vote})"
            "}).then(r=>r.json()).then(function(d){"
            "if(d.success){showToast(d.message,'success');setTimeout(function(){location.reload()},1200)}"
            "else{showToast(d.error,'error')}"
            "});}"
            "function moderateSuggestion(sid,status){"
            "var notes=prompt('Add admin notes (optional):','');"
            "fetch('/api/wishlist/'+sid+'/moderate',{"
            "method:'POST',headers:{'Content-Type':'application/json'},"
            "body:JSON.stringify({status:status,admin_notes:notes||''})"
            "}).then(r=>r.json()).then(function(d){"
            "if(d.success){showToast(d.message,'success');setTimeout(function(){location.reload()},1200)}"
            "else{showToast(d.error,'error')}"
            "});}"
            "function showSuggestionComments(sid){"
            "var notes=prompt('Add a comment:','');"
            "if(!notes||!notes.trim())return;"
            "fetch('/api/wishlist/'+sid+'/comment',{"
            "method:'POST',headers:{'Content-Type':'application/json'},"
            "body:JSON.stringify({content:notes.trim()})"
            "}).then(r=>r.json()).then(function(d){"
            "if(d.success){showToast(d.message,'success');setTimeout(function(){location.reload()},1200)}"
            "else{showToast(d.error,'error')}"
            "});}"
            '</script>'
        )
        return render_page("Wishlist", CONTENT)

    # ── Wishlist API ──

    @app.route("/api/wishlist/suggest", methods=["POST"])
    @login_required
    @_rate_limit("10 per minute")
    def api_suggest_book() -> Response:
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg, suggestion = _wishlist.add_suggestion(
            uid,
            data.get("title", ""),
            data.get("author", ""),
            data.get("reason", ""),
            data.get("isbn", ""),
            data.get("category", ""),
            data.get("url", ""),
        )
        try:
            from app.services.social.gamification import Gamification

            g = Gamification(_storage)
            g.add_points(uid, 5, "Suggested a book")
        except (ImportError, AttributeError):
            pass
        return jsonify({"success": ok, "message": msg, "suggestion": suggestion})

    @app.route("/api/wishlist/<suggestion_id>/vote", methods=["POST"])
    @login_required
    @_rate_limit("60 per minute")
    def api_vote_suggestion(suggestion_id) -> Response:
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg, result = _wishlist.vote_suggestion(suggestion_id, uid, data.get("vote", "up"))
        return jsonify({"success": ok, "message": msg, **result})

    @app.route("/api/wishlist/<suggestion_id>/moderate", methods=["POST"])
    @login_required
    @admin_required
    @_rate_limit("20 per minute")
    def api_moderate_suggestion(suggestion_id) -> Response:
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg = _wishlist.moderate_suggestion(
            suggestion_id, uid, data.get("status", ""), data.get("admin_notes", "")
        )
        return jsonify({"success": ok, "message": msg})

    @app.route("/api/wishlist/<suggestion_id>/comment", methods=["POST"])
    @login_required
    @_rate_limit("30 per minute")
    def api_suggestion_comment(suggestion_id) -> Response:
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg = _wishlist.add_suggestion_comment(suggestion_id, uid, data.get("content", ""))
        return jsonify({"success": ok, "message": msg})

    @app.route("/api/wishlist/stats")
    @login_required
    def api_wishlist_stats() -> Response:
        return jsonify(_wishlist.get_suggestion_stats())
