"""
progress_routes.py - Reading Progress pages and Bookmarks API.
Extracted from feature_routes.py for focused maintenance.
"""

import contextlib
from datetime import datetime

from flask import jsonify, request, session

from app.routes.feature_shared import (
from typing import Any
from flask import Response
    _progress,
    _challenge,
    _storage,
    h,
    cat_color,
)


def register_progress_routes(app, login_required, render_page, _rate_limit) -> None:
    """Register reading progress and bookmark routes on *app*."""

    @app.route("/reading-progress")
    @login_required
    def reading_progress_page() -> str:
        uid = session["user_id"]
        rl = _progress.get_user_reading_list(uid)
        stats = _progress.get_reading_stats(uid)

        def render_book_list(books, empty_msg):
            if not books:
                return '<div class="text-center text-muted small py-3">' + empty_msg + '</div>'
            out = ""
            for b in books:
                pct = b.get("percentage", 0)
                cc = cat_color(b.get("book_category", ""))
                bar_col = "var(--success)" if pct >= 100 else "var(--primary)"
                out += (
                    '<div class="d-flex align-items-center gap-2 mb-2 p-2" style="border-radius:8px;border:1px solid var(--border);">'
                    '<div style="width:36px;height:36px;border-radius:8px;background:' + cc + '20;display:flex;align-items:center;justify-content:center;flex-shrink:0;">'
                    '<i class="bi bi-book-fill" style="color:' + cc + ';"></i></div>'
                    '<div class="flex-grow-1" style="min-width:0;">'
                    '<a href="/books/' + h(b["book_id"]) + '" class="fw-bold text-decoration-none" style="color:var(--text);font-size:.85rem;">' + h(b.get("book_title", ""))[:40] + '</a>'
                    '<div class="progress-thin mt-1"><div class="bar" style="width:' + str(pct) + '%;background:' + bar_col + ';"></div></div>'
                    '<small class="text-muted" style="font-size:.65rem;">' + str(pct) + '% · Page ' + str(b.get("current_page", 0)) + '/' + str(b.get("total_pages", 0)) + '</small>'
                    '</div>'
                    '<a href="/reading-progress/' + h(b["book_id"]) + '" class="btn btn-sm btn-outline" style="flex-shrink:0;"><i class="bi bi-arrow-right"></i></a>'
                    '</div>'
                )
            return out

        READING = render_book_list(
            rl.get("currently_reading", []), "No books being read right now."
        )
        FINISHED = render_book_list(rl.get("finished", [])[:5], "No finished books yet.")

        time_h = stats.get("total_time_spent_minutes", 0) // 60
        time_m = stats.get("total_time_spent_minutes", 0) % 60

        CONTENT = """
        <div class="animate-in">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h4 class="fw-bold mb-0"><i class="bi bi-bookmark-check-fill me-2 text-primary"></i>Reading Progress</h4>
            </div>
            <div class="stats-bar mb-3 animate-in">
                <div class="stat-item"><div class="num">""" + str(stats.get("books_started", 0)) + """</div><div class="desc">Started</div></div>
                <div class="stat-item"><div class="num">""" + str(stats.get("books_finished", 0)) + """</div><div class="desc">Finished</div></div>
                <div class="stat-item"><div class="num">""" + str(stats.get("completion_rate", 0)) + """%</div><div class="desc">Completion</div></div>
                <div class="stat-item"><div class="num">""" + str(stats.get("total_pages_read", 0)) + """</div><div class="desc">Pages Read</div></div>
                <div class="stat-item"><div class="num">""" + str(time_h) + """h """ + str(time_m) + """m</div><div class="desc">Time Spent</div></div>
            </div>
            <div class="row">
                <div class="col-lg-7 mb-3">
                    <div class="glass-card p-3">
                        <div class="section-title"><i class="bi bi-book-fill text-primary"></i> Currently Reading (""" + str(len(rl.get("currently_reading", []))) + """)</div>
                        """ + READING + """
                    </div>
                    <div class="glass-card p-3 mt-3">
                        <div class="section-title"><i class="bi bi-check-circle-fill text-success"></i> Recently Finished (""" + str(len(rl.get("finished", []))) + """)</div>
                        """ + FINISHED + """
                    </div>
                </div>
                <div class="col-lg-5 mb-3">
                    <div class="glass-card p-3 mb-3">
                        <div class="section-title"><i class="bi bi-bookmark-fill text-warning"></i> Quick Update</div>
                        <p class="text-muted small">Update your progress for a book you are reading.</p>
                        <div class="input-group mb-2">
                            <input type="text" id="progressBookSearch" class="form-control" placeholder="Search a book..." oninput="searchProgressBooks(this.value)">
                        </div>
                        <div id="progressBookResults" class="mb-2"></div>
                        <div id="progressUpdateForm" style="display:none;">
                            <hr style="border-color:var(--border);">
                            <label class="form-label">Current Page</label>
                            <div class="input-group">
                                <input type="number" id="progressPage" class="form-control" min="1" placeholder="Page number">
                                <button class="btn btn-primary" onclick="submitProgressUpdate()"><i class="bi bi-check"></i> Update</button>
                            </div>
                            <small class="text-muted" id="progressBookInfo"></small>
                        </div>
                    </div>
                    <div class="glass-card p-3">
                        <div class="section-title"><i class="bi bi-bookmark-heart-fill text-danger"></i> My Bookmarks</div>
                        <div id="bookmarksList"><div class="text-center text-muted small py-3">Loading...</div></div>
                    </div>
                </div>
            </div>
        </div>
        """
        CONTENT += """
        <script>
        var selectedProgressBookId = null;
        function searchProgressBooks(q){
            if(q.length<2){ document.getElementById("progressBookResults").innerHTML="";return}
            fetch('/api/books?q='+encodeURIComponent(q)).then(r=>r.json()).then(function(books){
                var c=document.getElementById("progressBookResults");
                if(!books.length){c.innerHTML="<div class=\\"text-muted small\\">No books found</div>";return}
                c.innerHTML=books.slice(0,5).map(function(b){
                    return '<div class="search-result-item" style="cursor:pointer;padding:.3rem .5rem;" onclick="selectProgressBook(\\''+booktaleUtils.jsStr(b.book_id)+'\\',\\''+booktaleUtils.jsStr(b.title)+'\\','+(b.pages||0)+')">'+booktaleUtils.escapeHtml(b.title)+' <small class="text-muted">'+booktaleUtils.escapeHtml(b.author)+'</small></div>';
                }).join('');
            });
        }
        function selectProgressBook(bid,title,pages){
            selectedProgressBookId=bid;
            document.getElementById("progressBookSearch").value=title;
            document.getElementById("progressBookResults").innerHTML="";
            document.getElementById("progressUpdateForm").style.display='block';
            document.getElementById("progressBookInfo").textContent=title+' ('+(pages||'?')+' pages)';
            document.getElementById("progressPage").max=pages||9999;
        }
        function submitProgressUpdate(){
            var page=document.getElementById("progressPage").value;
            if(!selectedProgressBookId||!page){showToast('Select a book and enter a page','error');return}
            fetch('/api/reading-progress/'+selectedProgressBookId+'/update',{
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({current_page:parseInt(page)})
            }).then(r=>r.json()).then(function(d){
                if(d.success){showToast(d.message,'success');setTimeout(function(){location.reload()},1200)}
                else{showToast(d.error,'error')}
            });
        }
        fetch('/api/bookmarks').then(r=>r.json()).then(function(d){
            var c=document.getElementById("bookmarksList");
            if(!d.bookmarks||!d.bookmarks.length){c.innerHTML='<div class="text-center text-muted small py-3">No bookmarks yet.</div>';return}
            c.innerHTML=d.bookmarks.slice(0,8).map(function(b){
                return '<div class="d-flex align-items-center gap-2 mb-2 p-1" style="border-bottom:1px solid var(--border);"><i class="bi bi-bookmark-fill text-warning"></i><div class="flex-grow-1" style="min-width:0;"><span class="fw-bold small">'+booktaleUtils.escapeHtml(b.book_title)+'</span><br><small class="text-muted">Page '+booktaleUtils.escapeHtml(b.page)+(b.note?' &middot; '+booktaleUtils.escapeHtml(b.note):'')+'</small></div><a href="/reading-progress/'+booktaleUtils.jsStr(b.book_id)+'" class="btn btn-sm btn-outline"><i class="bi bi-arrow-right"></i></a></div>';
            }).join('');
        });
        </script>"""
        return render_page("Reading Progress", CONTENT)

    @app.route("/reading-progress/<book_id>")
    @login_required
    def reading_progress_book(book_id) -> Any:
        uid = session["user_id"]
        book = _storage.load_books().get(book_id)
        if not book:
            return render_page(
                "Not Found",
                '<div class="empty-state empty-state-variant"><div class="empty-icon"><i class="bi bi-book-x"></i></div><div class="empty-title">Book not found</div><div class="empty-desc">This book may have been removed or does not exist.</div></div>',
            )
        progress = _progress.get_progress(uid, book_id)
        bookmarks = _progress.get_book_bookmarks(uid, book_id)

        BM_HTML = ""
        for bm in bookmarks:
            BM_HTML += (
                '<div class="d-flex align-items-center gap-2 mb-2 p-2" style="border-radius:8px;border:1px solid var(--border);">'
                '<i class="bi bi-bookmark-fill text-warning"></i>'
                '<div class="flex-grow-1"><strong>Page ' + str(bm['page']) + '</strong> &middot; ' + h(bm.get('note', '')) + '</div>'
                '<button class="btn btn-sm btn-outline" onclick="removeBookmark(\'' + bm["bookmark_id"] + '\')"><i class="bi bi-trash"></i></button>'
                '</div>'
            )
        if not BM_HTML:
            BM_HTML = '<div class="text-center text-muted small py-3">No bookmarks. Add one below!</div>'

        cc = cat_color(book.category)
        CONTENT = """
        <div class="animate-in">
            <div class="row">
                <div class="col-lg-8">
                    <div class="glass-card p-4 mb-3">
                        <div class="d-flex gap-3">
                            <div style="width:56px;height:56px;border-radius:12px;background:linear-gradient(135deg,""" + cc + """,""" + cc + """dd);display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                                <i class="bi bi-book-fill" style="color:white;font-size:1.3rem;"></i>
                            </div>
                            <div class="flex-grow-1">
                                <h5 class="fw-bold mb-1">""" + h(book.title) + """</h5>
                                <p class="text-muted mb-0">""" + h(book.author) + """</p>
                            </div>
                            <div class="text-end">
                                <div class="fw-bold" style="font-size:1.5rem;color:var(--primary);">""" + str(progress.get("percentage", 0)) + """%</div>
                                <small class="text-muted">""" + str(progress.get("current_page", 0)) + """/""" + str(progress.get("total_pages", 0) or "?") + """ pages</small>
                            </div>
                        </div>
                        <div class="progress-thin mt-3" style="height:10px;border-radius:5px;">
                            <div class="bar" style="width:""" + str(progress.get("percentage", 0)) + """%;background:var(--primary);height:10px;border-radius:5px;"></div>
                        </div>
                    </div>
                    <div class="glass-card p-3 mb-3">
                        <div class="section-title"><i class="bi bi-pencil-fill"></i> Update Progress</div>
                        <div class="row g-2">
                            <div class="col-md-4">
                                <label class="form-label">Current Page</label>
                                <input type="number" id="updatePage" class="form-control" value=""" + str(progress.get("current_page", 0)) + """ min="0" max=""" + str(progress.get("total_pages", 9999) or 9999) + """>
                            </div>
                            <div class="col-md-4">
                                <label class="form-label">Minutes Read</label>
                                <input type="number" id="updateMinutes" class="form-control" value="15" min="1">
                            </div>
                            <div class="col-md-4 d-flex align-items-end gap-1">
                                <button class="btn btn-primary" onclick="updateProgress()"><i class="bi bi-check"></i> Update</button>
                                <button class="btn btn-success" onclick="markAsFinished()"><i class="bi bi-check-all"></i> Finished</button>
                            </div>
                        </div>
                        <div class="mt-2">
                            <label class="form-label">Notes</label>
                            <textarea id="updateNotes" class="form-control" rows="2" placeholder="Your thoughts...">""" + h(progress.get("notes", "")) + """</textarea>
                        </div>
                    </div>
                </div>
                <div class="col-lg-4">
                    <div class="glass-card p-3 mb-3">
                        <div class="section-title"><i class="bi bi-clock"></i> Reading Stats</div>
                        <div class="info-grid">
                            <div class="info-card"><div class="value">""" + str(progress.get("percentage", 0)) + """%</div><div class="label">Complete</div></div>
                            <div class="info-card"><div class="value">""" + str(progress.get("current_page", 0)) + """</div><div class="label">Current Page</div></div>
                            <div class="info-card"><div class="value">""" + str(progress.get("estimated_minutes_remaining", 0)) + """m</div><div class="label">Left to Read</div></div>
                            <div class="info-card"><div class="value">""" + str(progress.get("time_spent_minutes", 0)) + """m</div><div class="label">Time Spent</div></div>
                        </div>
                    </div>
                    <div class="glass-card p-3">
                        <div class="section-title"><i class="bi bi-bookmark-fill text-warning"></i> Bookmarks</div>
                        """ + BM_HTML + """
                        <hr style="border-color:var(--border);">
                        <div class="input-group input-group-sm">
                            <input type="number" id="newBookmarkPage" class="form-control" placeholder="Page #" min="1">
                            <button class="btn btn-primary btn-sm" onclick="addBookmark()"><i class="bi bi-plus"></i> Add</button>
                        </div>
                        <input type="text" id="newBookmarkNote" class="form-control form-control-sm mt-1" placeholder="Optional note...">
                    </div>
                </div>
            </div>
        </div>
        <script>
        function updateProgress(){
            fetch('/api/reading-progress/""" + book_id + """/update',{
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({
                    current_page:parseInt(document.getElementById("updatePage").value),
                    time_spent_minutes:parseInt(document.getElementById("updateMinutes").value)||0,
                    notes:document.getElementById("updateNotes").value
                })
            }).then(r=>r.json()).then(function(d){
                if(d.success){showToast(d.message,'success');setTimeout(function(){location.reload()},1000)}
                else{showToast(d.error,'error')}
            });
        }
        function markAsFinished(){
            if(!confirm('Mark this book as finished?'))return;
            fetch('/api/reading-progress/""" + book_id + """/finish',{method:'POST'}).then(r=>r.json()).then(function(d){
                if(d.success){showToast(d.message,'success');setTimeout(function(){location.reload()},1000)}
                else{showToast(d.error,'error')}
            });
        }
        function addBookmark(){
            var p=document.getElementById("newBookmarkPage").value;
            var n=document.getElementById("newBookmarkNote").value;
            if(!p){showToast('Enter a page number','error');return}
            fetch('/api/bookmarks/add',{
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({book_id:'""" + book_id + """',page:parseInt(p),note:n})
            }).then(r=>r.json()).then(function(d){
                if(d.success){showToast(d.message,'success');setTimeout(function(){location.reload()},1000)}
                else{showToast(d.error,'error')}
            });
        }
        function removeBookmark(bid){
            if(!confirm('Remove bookmark?'))return;
            fetch('/api/bookmarks/'+bid+'/remove',{method:'POST'}).then(r=>r.json()).then(function(d){
                if(d.success){showToast(d.message,'success');setTimeout(function(){location.reload()},1000)}
                else{showToast(d.error,'error')}
            });
        }
        </script>"""
        return render_page("Reading: " + book.title, CONTENT)

    @app.route("/reading-progress/history")
    @login_required
    def reading_progress_history() -> Any:
        uid = session["user_id"]
        rl = _progress.get_user_reading_list(uid)
        all_books = rl.get("currently_reading", []) + rl.get("finished", []) + rl.get("on_hold", [])

        ROWS = ""
        for b in all_books:
            cc = cat_color(b.get("book_category", ""))
            pct = b.get("percentage", 0)
            status_badge = (
                '<span class="badge bg-success">✅ Finished</span>'
                if b.get("finished")
                else (
                    '<span class="badge bg-primary">📖 Reading</span>'
                    if b.get("current_page", 0) > 0
                    else '<span class="badge bg-secondary">⏸️ On Hold</span>'
                )
            )
            ROWS += (
                '<tr>'
                '<td><a href="/reading-progress/' + h(b["book_id"]) + '" class="fw-bold text-decoration-none" style="color:var(--text);">' + h(b.get("book_title", ""))[:50] + '</a></td>'
                '<td><span class="badge" style="background:' + cc + '20;color:' + cc + ';">' + h(b.get("book_category", "")) + '</span></td>'
                '<td>' + status_badge + '</td>'
                '<td><div class="d-flex align-items-center gap-2">'
                '<div class="progress-thin flex-grow-1"><div class="bar" style="width:' + str(pct) + '%;background:var(--primary);"></div></div>'
                '<small class="fw-bold">' + str(pct) + '%</small></div></td>'
                '<td>' + str(b.get("current_page", 0)) + '/' + str(b.get("total_pages", 0) or "?") + '</td>'
                '<td>' + str(b.get("time_spent_minutes", 0)) + 'm</td>'
                '</tr>'
            )
        if not ROWS:
            ROWS = '<tr><td colspan="6" class="text-center text-muted py-4">No reading history yet.</td></tr>'

        CONTENT = """
        <div class="animate-in">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h4 class="fw-bold mb-0"><i class="bi bi-clock-history me-2 text-info"></i>Reading History</h4>
                <a href="/reading-progress" class="btn btn-outline btn-sm"><i class="bi bi-arrow-left"></i> Back</a>
            </div>
            <div class="glass-card p-3">
                <div class="table-responsive"><table class="table table-hover">
                    <thead><tr><th>Book</th><th>Category</th><th>Status</th><th>Progress</th><th>Pages</th><th>Time</th></tr></thead>
                    <tbody>""" + ROWS + """</tbody>
                </table></div>
            </div>
        </div>"""
        return render_page("Reading History", CONTENT)

    # ── Reading Progress API ──

    @app.route("/api/reading-progress/<book_id>/update", methods=["POST"])
    @login_required
    def api_update_reading_progress(book_id) -> Response:
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg, progress = _progress.update_progress(
            uid,
            book_id,
            current_page=data.get("current_page"),
            time_spent_minutes=data.get("time_spent_minutes"),
            notes=data.get("notes"),
            finished=data.get("finished"),
        )
        return jsonify({"success": ok, "message": msg, "progress": progress})

    @app.route("/api/reading-progress/<book_id>/finish", methods=["POST"])
    @login_required
    def api_finish_reading(book_id) -> Response:
        uid = session["user_id"]
        ok, msg, progress = _progress.mark_as_finished(uid, book_id)
        with contextlib.suppress(Exception):
            _challenge.set_goal(
                uid,
                datetime.now().year,
                _challenge.get_goal(uid, datetime.now().year).get("goal", 0),
            )
        return jsonify({"success": ok, "message": msg, "progress": progress})

    @app.route("/api/reading-progress/<book_id>")
    @login_required
    def api_get_progress(book_id) -> Response:
        uid = session["user_id"]
        return jsonify(_progress.get_progress(uid, book_id))

    @app.route("/api/reading-progress/stats")
    @login_required
    def api_reading_progress_stats() -> Response:
        uid = session["user_id"]
        rl = _progress.get_user_reading_list(uid)
        stats = _progress.get_reading_stats(uid)
        return jsonify(
            {
                "currently_reading": len(rl.get("currently_reading", [])),
                "finished": len(rl.get("finished", [])),
                "completed": stats.get("books_finished", 0),
                "total_pages": stats.get("total_pages_read", 0),
                "total_time_minutes": stats.get("total_time_spent_minutes", 0),
                "completion_rate": stats.get("completion_rate", 0),
            }
        )

    # ── Bookmarks API ──

    @app.route("/api/bookmarks")
    @login_required
    def api_get_bookmarks() -> Response:
        uid = session["user_id"]
        return jsonify({"bookmarks": _progress.get_user_bookmarks(uid)})

    @app.route("/api/bookmarks/add", methods=["POST"])
    @login_required
    def api_add_bookmark() -> Response:
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg, bm = _progress.add_bookmark(
            uid, data.get("book_id", ""), int(data.get("page", 1)), data.get("note", "")
        )
        return jsonify({"success": ok, "message": msg, "bookmark": bm})

    @app.route("/api/bookmarks/<bookmark_id>/remove", methods=["POST"])
    @login_required
    def api_remove_bookmark(bookmark_id) -> Response:
        uid = session["user_id"]
        ok, msg = _progress.remove_bookmark(bookmark_id, uid)
        return jsonify({"success": ok, "message": msg})
