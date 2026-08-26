"""
diary_routes.py - Reading Diary pages and API endpoints.
Extracted from feature_routes.py for focused maintenance.
"""

from flask import jsonify, request, session

from app.routes.feature_shared import (
    _diary,
    _storage,
    h,
    cat_color,
)
from app.services.reading.diary import (
    RATING_LABELS,
    RATING_SCORES,
    rating_badge_html,
    star_rating_html,
)


def register_diary_routes(app, login_required, render_page, _rate_limit):
    """Register reading diary routes on *app*."""

    @app.route("/diary")
    @login_required
    def diary_page():
        uid = session["user_id"]
        page = max(1, int(request.args.get("page", 1)))
        entries, _total = _diary.get_user_diary(uid, page=page)
        stats = _diary.get_stats(uid)

        avg_info = RATING_LABELS.get(
            stats.get("avg_rating_label", "timepass"), RATING_LABELS["timepass"]
        )
        ENTRY_CARDS = ""
        for e in entries:
            cc = cat_color(e.get("book_category", ""))
            cover = e.get("book_cover", "")
            cover_html = (
                f'<img src="{cover}" alt="" class="bt-diary-cover" loading="lazy" onerror="this.style.display=&#39;none&#39;">'
                if cover
                else ""
            )
            vibe_html = (
                "".join(
                    f'<a href="/explore/vibes/{h(t)}" class="bt-vibe-tag">{h(t)}</a>'
                    for t in e.get("vibe_tags", [])
                )
                if e.get("vibe_tags")
                else ""
            )
            spoiler_badge = (
                '<span class="badge bg-warning text-dark" style="font-size:.6rem;">⚠️ Spoiler</span>'
                if e.get("spoiler")
                else ""
            )
            reread_badge = (
                '<span class="badge bg-info" style="font-size:.6rem;">🔄 Reread</span>'
                if e.get("is_reread")
                else ""
            )

            ENTRY_CARDS += f"""
            <div class="bt-diary-entry" role="article">
                <div style="width:60px;flex-shrink:0;">{cover_html or f'<div style="width:60px;height:90px;border-radius:6px;background:linear-gradient(135deg,{cc},{cc}dd);display:flex;align-items:center;justify-content:center;"><i class="bi bi-book-fill" style="color:white;font-size:1.2rem;"></i></div>'}</div>
                <div class="bt-diary-body">
                    <div class="bt-diary-date">{e.get("date_read", "")[:10]}</div>
                    <a href="/books/{h(e["book_id"])}" class="bt-diary-book-title">{h(e.get("book_title", ""))}</a>
                    <div style="font-size:.75rem;color:var(--text-muted);">{h(e.get("book_author", ""))}</div>
                    <div class="d-flex align-items-center gap-2 mt-1 flex-wrap">
                        {e.get("rating_badge", "")}
                        {e.get("star_html", "")}
                        {spoiler_badge}
                        {reread_badge}
                    </div>
                    {f'<div class="bt-diary-text">{h(e.get("diary_text", ""))[:300]}</div>' if e.get("diary_text") else ""}
                    {f'<div class="d-flex gap-1 mt-1 flex-wrap">{vibe_html}</div>' if vibe_html else ""}
                    <div class="bt-diary-meta">
                        <a href="/diary/{e["id"]}" class="btn btn-sm btn-outline"><i class="bi bi-eye"></i> View</a>
                        <button class="btn btn-sm btn-outline" onclick="editDiaryEntry('{e["id"]}')"><i class="bi bi-pencil"></i></button>
                        <button class="btn btn-sm btn-outline" onclick="deleteDiaryEntry('{e["id"]}')"><i class="bi bi-trash"></i></button>
                    </div>
                </div>
            </div>"""

        if not ENTRY_CARDS:
            ENTRY_CARDS = """
            <div class="empty-state">
                <div class="empty-icon"><i class="bi bi-journal-text"></i></div>
                <h5>Your reading diary is empty</h5>
                <p class="text-muted">Start logging books you've read!</p>
                <button class="btn btn-primary" onclick="showLogForm()"><i class="bi bi-plus-lg"></i> Log a Book</button>
            </div>"""

        _vibe_tags = stats.get("vibe_tags_cloud", [])
        if _vibe_tags:
            VIBE_TAGS_HTML = (
                '<div class="glass-card p-3"><div class="section-title">'
                '<i class="bi bi-tags-fill"></i> Vibe Tags</div>'
                '<div class="d-flex flex-wrap gap-1">'
                + "".join(
                    f'<span class="bt-vibe-tag">{h(t)} <small class="text-muted">({c})</small></span>'
                    for t, c in _vibe_tags
                )
                + "</div></div>"
            )
        else:
            VIBE_TAGS_HTML = ""
        _diary_html = f"""
        <div class="animate-in">
            <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
                <h4 class="fw-bold mb-0"><i class="bi bi-journal-text me-2 text-primary"></i>Reading Diary <span class="text-muted fw-normal" style="font-size:.9rem;">({stats["total_books"]} entries)</span></h4>
                <button class="btn btn-primary btn-sm" onclick="showLogForm()"><i class="bi bi-plus-lg"></i> Log a Book</button>
            </div>
            <div class="stats-bar mb-3 animate-in">
                <div class="stat-item"><div class="num">{stats["total_books"]}</div><div class="desc">Books Read</div></div>
                <div class="stat-item"><div class="num">{stats["reread_count"]}</div><div class="desc">Rereads</div></div>
                <div class="stat-item"><div class="num">{stats["total_pages_read"]}</div><div class="desc">Pages</div></div>
                <div class="stat-item"><div class="num" style="color:{avg_info["color"]};">{avg_info["emoji"]} {avg_info["label"]}</div><div class="desc">Avg Rating</div></div>
            </div>
            <div class="row">
                <div class="col-lg-8">
                    {ENTRY_CARDS}
                </div>
                <div class="col-lg-4">
                    <div class="glass-card p-3 mb-3">
                        <div class="section-title"><i class="bi bi-pie-chart-fill"></i> Rating Distribution</div>
                        {"".join(f'<div class="d-flex align-items-center gap-2 mb-1"><span class="small" style="min-width:80px;">{RATING_LABELS.get(l, {}).get("emoji", "")} {l}</span><div class="flex-grow-1"><div class="progress-thin"><div class="bar" style="width:{round(c / stats["total_books"] * 100) if stats["total_books"] else 0}%;background:{RATING_LABELS.get(l, {}).get("color", "#6b7280")};"></div></div></div><small class="fw-bold">{c}</small></div>' for l, c in sorted(stats.get("rating_distribution", {}).items(), key=lambda x: RATING_SCORES.get(x[0], 0), reverse=True))}
                    </div>
                    <div class="glass-card p-3 mb-3">
                        <div class="section-title"><i class="bi bi-grid-3x3-gap-fill"></i> Top Genres</div>
                        {"".join(f'<div class="d-flex justify-content-between mb-1"><span>{h(g)}</span><span class="fw-bold">{c}</span></div>' for g, c in stats.get("top_genres", []))}
                    </div>
                    {VIBE_TAGS_HTML}
                </div>
            </div>
        </div>
        """

        _diary_js = """
        <div class="modal fade" id="logModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content">
            <div class="modal-header"><h5 class="modal-title"><i class="bi bi-journal-plus text-primary me-1"></i> Log a Book</h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
            <div class="modal-body">
                <div class="mb-3"><label class="form-label">Book *</label>
                    <input type="text" id="logBookSearch" class="form-control" placeholder="Search for a book..." oninput="searchDiaryBooks(this.value)">
                    <div id="logBookResults" class="mt-1"></div>
                    <input type="hidden" id="logBookId">
                </div>
                <div class="mb-3"><label class="form-label">Date Read</label>
                    <input type="date" id="logDate" class="form-control"></div>
                <div class="mb-3"><label class="form-label">Rating *</label>
                    <div class="d-flex gap-2 flex-wrap" id="ratingButtons">
                        <button class="btn btn-sm btn-outline" onclick="selectRating('perfection',this)" id="rating-perfection" type="button">📖 Perfection</button>
                        <button class="btn btn-sm btn-primary" onclick="selectRating('worth_it',this)" id="rating-worth_it" type="button">☕ Worth the Read</button>
                        <button class="btn btn-sm btn-outline" onclick="selectRating('timepass',this)" id="rating-timepass" type="button">⌛ Timepass</button>
                        <button class="btn btn-sm btn-outline" onclick="selectRating('skip',this)" id="rating-skip" type="button">❌ Skip It</button>
                    </div>
                    <input type="hidden" id="logRating" value="worth_it">
                </div>
                <div class="mb-3"><label class="form-label">Star Rating (optional)</label>
                    <div class="d-flex gap-1" id="starSelector" style="font-size:1.5rem;cursor:pointer;">
                        <span class="star-opt" data-val="1" onclick="selectStar(1)" style="color:var(--text-dim);transition:all .2s;">☆</span>
                        <span class="star-opt" data-val="2" onclick="selectStar(2)" style="color:var(--text-dim);transition:all .2s;">☆</span>
                        <span class="star-opt" data-val="3" onclick="selectStar(3)" style="color:var(--text-dim);transition:all .2s;">☆</span>
                        <span class="star-opt" data-val="4" onclick="selectStar(4)" style="color:var(--text-dim);transition:all .2s;">☆</span>
                        <span class="star-opt" data-val="5" onclick="selectStar(5)" style="color:var(--text-dim);transition:all .2s;">☆</span>
                    </div>
                </div>
                <div class="mb-3"><label class="form-label">Review / Thoughts</label>
                    <textarea id="logText" class="form-control" rows="3" placeholder="What did you think of this book?"></textarea></div>
                <div class="mb-3">
                    <div class="form-check form-check-inline"><input type="checkbox" id="logReread" class="form-check-input"><label class="form-check-label small">Reread</label></div>
                    <div class="form-check form-check-inline"><input type="checkbox" id="logSpoiler" class="form-check-input"><label class="form-check-label small">Contains spoilers</label></div>
                </div>
                <div class="mb-3"><label class="form-label">Vibe Tags <small class="text-muted">(comma-separated, e.g. cozy)</small></label>
                    <input type="text" id="logVibes" class="form-control" placeholder="cozy, slow-burn, unputdownable"></div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-outline" data-bs-dismiss="modal">Cancel</button>
                <button class="btn btn-primary" onclick="submitDiaryLog()"><i class="bi bi-check-lg"></i> Log It</button>
            </div>
        </div></div></div>

        <script>
        var selectedDiaryBookId = null;
        var ratingLabel = "worth_it";
        var starRating = null;

        function searchDiaryBooks(q) {
            if(q.length<2){ document.getElementById("logBookResults").innerHTML="";return}
            fetch("/api/books?q="+encodeURIComponent(q)).then(function(r){return r.json()}).then(function(books){
                var c=document.getElementById("logBookResults");
                if(!books.length){c.innerHTML="<div class=\\"text-muted small\\">No books found</div>";return}
                c.innerHTML=books.slice(0,5).map(function(b){return "<div class=\\"search-result-item\\" style=\\"cursor:pointer;padding:.3rem .5rem;\\" onclick=\\"selectDiaryBook(\\'"+booktaleUtils.jsStr(b.book_id)+"\\',\\'"+booktaleUtils.jsStr(b.title)+"\\')\\">"+booktaleUtils.escapeHtml(b.title)+" <small class=\\"text-muted\\">"+booktaleUtils.escapeHtml(b.author)+"</small></div>"}).join("");
            });
        }

        function selectDiaryBook(bid, title) {
            selectedDiaryBookId = bid;
            document.getElementById("logBookSearch").value = title;
            document.getElementById("logBookId").value = bid;
            document.getElementById("logBookResults").innerHTML = "<small class=\\"text-success\\">Selected: "+booktaleUtils.escapeHtml(title)+"</small>";
        }

        function showLogForm() {var m=new bootstrap.Modal(document.getElementById("logModal")); m.show()}

        function submitDiaryLog() {
            if(!selectedDiaryBookId){showToast("Select a book","error");return}
            var data = {
                book_id: selectedDiaryBookId,
                date_read: document.getElementById("logDate").value,
                rating_label: document.getElementById("logRating").value,
                diary_text: document.getElementById("logText").value.trim(),
                is_reread: document.getElementById("logReread").checked,
                spoiler: document.getElementById("logSpoiler").checked,
                vibe_tags: document.getElementById("logVibes").value.split(",").map(function(t){return t.trim()}).filter(function(t){return t})
            };
            if(starRating) data.star_rating = starRating;
            fetch("/api/diary/log", {
                method:"POST",
                headers:{"Content-Type":"application/json"},
                body: JSON.stringify(data)
            }).then(function(r){return r.json()}).then(function(d){
                if(d.success){showToast(d.message,"success");setTimeout(function(){location.reload()},1000)}
                else{showToast(d.error,"error")}
            });
        }

        function deleteDiaryEntry(eid) {
            if(!confirm("Delete this entry?")) return;
            fetch("/api/diary/"+eid, {method:"DELETE"}).then(function(r){return r.json()}).then(function(d){
                if(d.success){showToast(d.message,"success");setTimeout(function(){location.reload()},1000)}
                else{showToast(d.error,"error")}
            });
        }

        function editDiaryEntry(eid) {
            window.location.href = "/diary/" + eid;
        }
        </script>"""

        CONTENT = _diary_html + _diary_js
        return render_page("Reading Diary", CONTENT)

    @app.route("/diary/<entry_id>")
    @login_required
    def diary_entry_page(entry_id):
        uid = session["user_id"]
        entry = _diary.get_entry(entry_id)
        if not entry:
            return render_page(
                "Not Found",
                '<div class="empty-state empty-state-variant"><div class="empty-icon"><i class="bi bi-journal-x"></i></div><div class="empty-title">Entry not found</div><div class="empty-desc">This diary entry may have been deleted.</div><a href="/diary" class="empty-cta"><i class="bi bi-arrow-left"></i> Back to Diary</a></div>',
            )

        if entry["user_id"] != uid:
            users = _storage.load_users()
            user = users.get(uid)
            if not user or user.role != "admin":
                return render_page(
                    "Forbidden",
                    '<div class="empty-state empty-state-variant"><div class="empty-icon"><i class="bi bi-shield-lock-fill"></i></div><div class="empty-title">Private Entry</div><div class="empty-desc">You can only view your own diary entries.</div></div>',
                )

        books = _storage.load_books()
        book = books.get(entry["book_id"])
        cover = book.cover_url or book.cover_image or "" if book else ""

        _ed = """
        <div class="animate-in">
            <div class="row">
                <div class="col-lg-8">
                    <div class="glass-card p-4">
                        <div class="d-flex gap-4">
                            <div style="width:120px;flex-shrink:0;">COVER_PLACEHOLDER</div>
                            <div class="flex-grow-1">
                                <div class="text-muted small mb-1"><i class="bi bi-calendar3"></i> Read on DATE_PLACEHOLDER</div>
                                <h4 class="fw-bold mb-1">BOOK_TITLE_PLACEHOLDER</h4>
                                <p class="text-muted mb-2">BOOK_AUTHOR_PLACEHOLDER</p>
                                <div class="d-flex gap-2 flex-wrap mb-2">
                                    RATING_BADGE_PLACEHOLDER STAR_HTML_PLACEHOLDER REREAD_PLACEHOLDER SPOILER_PLACEHOLDER
                                </div>
                            </div>
                        </div>
                        <hr style="border-color:var(--border);">
                        <div style="font-size:.95rem;line-height:1.7;">DIARY_TEXT_PLACEHOLDER</div>
                    </div>
                    <div class="d-flex gap-2 mt-3">
                        <button class="btn btn-primary" onclick="editDiaryEntry(ENTRY_ID_PLACEHOLDER)"><i class="bi bi-pencil"></i> Edit</button>
                        <button class="btn btn-danger" onclick="deleteDiaryEntry(ENTRY_ID_PLACEHOLDER)"><i class="bi bi-trash"></i> Delete</button>
                        <a href="/diary" class="btn btn-outline"><i class="bi bi-arrow-left"></i> Back to Diary</a>
                    </div>
                </div>
                <div class="col-lg-4">
                    <div class="glass-card p-3 mb-3">
                        <div class="section-title"><i class="bi bi-info-circle"></i> Details</div>
                        <div class="info-grid">
                            <div class="info-card"><div class="value">DATE_READ_PLACEHOLDER</div><div class="label">Date Read</div></div>
                            <div class="info-card"><div class="value">REREAD_YESNO_PLACEHOLDER</div><div class="label">Reread</div></div>
                            <div class="info-card"><div class="value">SPOILER_YESNO_PLACEHOLDER</div><div class="label">Spoiler</div></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>"""
        _ej = """
        <script>
        function deleteDiaryEntry(eid) {
            if(!confirm("Delete this entry?")) return;
            fetch("/api/diary/"+eid, {method:"DELETE"}).then(function(r){return r.json()}).then(function(d){
                if(d.success){showToast(d.message,"success");setTimeout(function(){window.location.href="/diary"},1000)}
                else{showToast(d.error,"error")}
            });
        }
        function editDiaryEntry(eid) {
            window.location.href = "/diary?edit="+eid;
        }
        </script>"""
        CONTENT = (
            _ed.replace("COVER_PLACEHOLDER", cover or "")
            .replace("DATE_PLACEHOLDER", str(entry.get("date_read", "")[:10]))
            .replace("BOOK_TITLE_PLACEHOLDER", h(book.title) if book else "Unknown Book")
            .replace("BOOK_AUTHOR_PLACEHOLDER", h(book.author) if book else "")
            .replace(
                "RATING_BADGE_PLACEHOLDER",
                rating_badge_html(entry.get("rating_label", "timepass")),
            )
            .replace("STAR_HTML_PLACEHOLDER", star_rating_html(entry.get("star_rating")))
            .replace(
                "REREAD_PLACEHOLDER",
                (
                    '<span class="badge bg-info" style="font-size:.6rem;">🔄 Reread</span>'
                    if entry.get("is_reread")
                    else ""
                ),
            )
            .replace(
                "SPOILER_PLACEHOLDER",
                (
                    '<span class="badge bg-warning text-dark" style="font-size:.6rem;">⚠️ Spoiler</span>'
                    if entry.get("spoiler")
                    else ""
                ),
            )
            .replace("DIARY_TEXT_PLACEHOLDER", h(entry.get("diary_text", "")))
            .replace("ENTRY_ID_PLACEHOLDER", "\\'" + h(entry["id"]) + "\\'")
            .replace("DATE_READ_PLACEHOLDER", str(entry.get("date_read", "")[:10]))
            .replace("REREAD_YESNO_PLACEHOLDER", "Yes" if entry.get("is_reread") else "No")
            .replace("SPOILER_YESNO_PLACEHOLDER", "Yes" if entry.get("spoiler") else "No")
            + _ej
        )
        return render_page("Diary Entry", CONTENT)

    # ── Diary API Routes ──

    @app.route("/api/diary/log", methods=["POST"])
    @login_required
    def api_diary_log():
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg, entry = _diary.log_read(
            uid,
            data.get("book_id", ""),
            date_read=data.get("date_read", ""),
            rating_label=data.get("rating_label", "worth_it"),
            star_rating=data.get("star_rating"),
            diary_text=data.get("diary_text", ""),
            is_reread=data.get("is_reread", False),
            spoiler=data.get("spoiler", False),
            vibe_tags=data.get("vibe_tags", []),
        )
        return jsonify({"success": ok, "message": msg, "entry": entry})

    @app.route("/api/diary/<entry_id>", methods=["PUT", "DELETE"])
    @login_required
    def api_diary_entry(entry_id):
        uid = session["user_id"]
        if request.method == "DELETE":
            ok, msg = _diary.delete_entry(entry_id, uid)
            return jsonify({"success": ok, "message": msg})
        else:
            data = request.get_json() or {}
            ok, msg = _diary.update_entry(entry_id, uid, **data)
            return jsonify({"success": ok, "message": msg})

    @app.route("/api/diary/stats")
    @login_required
    def api_diary_stats():
        uid = session["user_id"]
        return jsonify(_diary.get_stats(uid))

    @app.route("/api/diary/book/<book_id>")
    @login_required
    def api_diary_book_logs(book_id):
        include_spoilers = request.args.get("spoilers", "0") == "1"
        return jsonify({"logs": _diary.get_book_logs(book_id, include_spoilers=include_spoilers)})
