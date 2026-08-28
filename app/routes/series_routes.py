"""
series_routes.py - Book Series pages and API endpoints.
Extracted from feature_routes.py for focused maintenance.
"""

from flask import jsonify, redirect, render_template, request, session, url_for

from app.routes.feature_shared import _series, _storage, h, cat_color


def register_series_routes(app, login_required, admin_required, render_page, _rate_limit) -> None:
    """Register series routes on *app*."""

    @app.route("/series")
    @login_required
    def series_list_page() -> str:
        page = max(1, int(request.args.get("page", 1)))
        q = request.args.get("q", "")
        series_list, total = _series.get_all_series(page=page)
        if q:
            series_list = _series.search_series(q)

        CARDS = ""
        for s in series_list:
            cat = s.get("category", "")
            cc = cat_color(cat) if cat else "#4f46e5"
            CARDS += f"""<div class="col-md-6 col-lg-4 mb-3 animate-scale">
                <div class="glass-card p-3 h-100" onclick="window.location.href='/series/{s["series_id"]}'" style="cursor:pointer;">
                    <div class="d-flex gap-3">
                        <div style="width:48px;height:48px;border-radius:12px;background:linear-gradient(135deg,{cc},{cc}dd);display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                            <i class="bi bi-collection-fill" style="color:white;font-size:1.3rem;"></i>
                        </div>
                        <div class="flex-grow-1" style="min-width:0;">
                            <div class="fw-bold" style="font-size:.95rem;">{h(s["name"])}</div>
                            <small class="text-muted">{s.get("book_count", 0)} book{"" if s.get("book_count", 0) == 1 else "s"}</small>
                            <div style="font-size:.75rem;color:var(--text-muted);margin-top:.3rem;">{h(s.get("description", "")[:80])}</div>
                        </div>
                    </div>
                </div>
            </div>"""
        if not CARDS:
            CARDS = '<div class="col-12"><div class="empty-state empty-state-variant"><div class="empty-icon"><i class="bi bi-collection"></i></div><div class="empty-title">No series yet</div><div class="empty-desc">Create your first book series to organize books.</div><a href="/series/create" class="empty-cta"><i class="bi bi-plus-lg"></i> Create Series</a></div></div>'

        CONTENT = f"""
        <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2 animate-in">
            <h4 class="fw-bold mb-0"><i class="bi bi-collection-fill me-2 text-primary"></i>Book Series <span class="text-muted fw-normal" style="font-size:.9rem;">({total})</span></h4>
            <a href="/series/create" class="btn btn-primary btn-sm"><i class="bi bi-plus-lg"></i> New Series</a>
        </div>
        <form class="mb-3 animate-d1" role="search"><div class="search-filters">
            <input type="text" name="q" class="form-control" placeholder="Search series..." value="{h(q) if q else ""}" style="min-width:200px;">
            <button class="btn btn-primary" type="submit"><i class="bi bi-search"></i></button>
            <a href="/series" class="btn btn-outline"><i class="bi bi-x-lg"></i></a>
        </div></form>
        <div class="row g-3 animate-d2">{CARDS}</div>"""
        return render_page("Book Series", CONTENT)

    @app.route("/series/create", methods=["GET", "POST"])
    @login_required
    @admin_required
    def series_create() -> Any:
        if request.method == "GET":
            from app.models.book import CATEGORIES as BOOK_CATEGORIES

            co = "".join(f'<option value="{c}">{c}</option>' for c in BOOK_CATEGORIES)
            try:
                from flask_wtf.csrf import generate_csrf as _gen_csrf

                csrf_field = '<input type="hidden" name="csrf_token" value="' + _gen_csrf() + '">'
            except (ImportError, RuntimeError):
                csrf_field = ""
            CONTENT = f"""
            <div class="row justify-content-center animate-in">
                <div class="col-md-8 col-lg-6">
                    <h4 class="fw-bold mb-3"><i class="bi bi-plus-circle-fill text-primary me-2"></i>Create Book Series</h4>
                    <div class="glass-card p-4">
                        <form method="POST">
                            {csrf_field}
                            <div class="mb-3"><label class="form-label">Series Name</label>
                                <input type="text" name="name" class="form-control" placeholder="e.g. Harry Potter" required></div>
                            <div class="mb-3"><label class="form-label">Description</label>
                                <textarea name="description" class="form-control" rows="3" placeholder="About this series..."></textarea></div>
                            <div class="mb-3"><label class="form-label">Category</label>
                                <select name="category" class="form-select">{co}</select></div>
                            <div class="row"><div class="col-md-6 mb-3"><label class="form-label">Total Planned Books</label>
                                <input type="number" name="total_books" class="form-control" value="0" min="0"></div></div>
                            <div class="d-flex gap-2">
                                <button type="submit" class="btn btn-primary"><i class="bi bi-save me-1"></i>Create</button>
                                <a href="/series" class="btn btn-outline">Cancel</a>
                            </div>
                        </form>
                    </div>
                </div>
            </div>"""
            return render_page("Create Series", CONTENT)
        ok, msg, _ = _series.create_series(
            request.form["name"],
            request.form.get("description", ""),
            request.form.get("category", ""),
            session.get("user_id", "web"),
        )
        if ok:
            return redirect(url_for("series_list_page"))
        return render_page("Error", f'<div class="alert alert-danger">{h(msg)}</div>')

    @app.route("/series/<series_id>")
    @login_required
    def series_detail(series_id) -> Any:
        s = _series.get_series(series_id)
        if not s:
            return render_page(
                "Not Found",
                '<div class="empty-state empty-state-variant"><div class="empty-icon"><i class="bi bi-collection"></i></div><div class="empty-title">Series not found</div><div class="empty-desc">The series you are looking for does not exist.</div><a href="/series" class="empty-cta"><i class="bi bi-arrow-left"></i> Browse Series</a></div>',
            )
        books = _series.get_series_books(s["name"])
        cat = s.get("category", "")
        cc = cat_color(cat) if cat else "#4f46e5"

        BOOKS_HTML = ""
        for i, b in enumerate(books):
            bcc = cat_color(b.get("category", ""))
            order = b.get("series_order", 0) or (i + 1)
            avail = (
                '<span class="badge-green px-2 py-1 small">Available</span>'
                if b.get("available_copies", 0) > 0
                else '<span class="badge-red px-2 py-1 small">Out</span>'
            )
            BOOKS_HTML += f"""
            <div class="col-md-6 mb-2">
                <div class="glass-card p-2 d-flex align-items-center gap-3" onclick="window.location.href='/books/{b["book_id"]}'" style="cursor:pointer;">
                    <div style="width:40px;height:40px;border-radius:10px;background:{bcc}20;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-weight:800;color:{bcc};">#{order}</div>
                    <div class="flex-grow-1" style="min-width:0;">
                        <div class="fw-bold" style="font-size:.9rem;">{h(b["title"])}</div>
                        <small class="text-muted">{h(b["author"])}</small>
                    </div>
                    <div class="flex-shrink-0">{avail}</div>
                </div>
            </div>"""
        if not BOOKS_HTML:
            BOOKS_HTML = '<div class="col-12"><div class="empty-state empty-state-variant"><div class="empty-icon"><i class="bi bi-book"></i></div><div class="empty-title">No books in this series yet</div><div class="empty-desc">Add books to this series to organize them.</div></div></div>'

        CONTENT = f"""
        <div class="row animate-in">
            <div class="col-lg-8">
                <div class="glass-card p-4 mb-3">
                    <div class="d-flex gap-3 mb-3">
                        <div style="width:64px;height:64px;border-radius:14px;background:linear-gradient(135deg,{cc},{cc}dd);display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                            <i class="bi bi-collection-fill" style="color:white;font-size:1.5rem;"></i>
                        </div>
                        <div>
                            <h3 class="fw-bold mb-1">{h(s["name"])}</h3>
                            <p class="text-muted mb-2">{h(s.get("description", ""))}</p>
                            <div class="d-flex gap-2">
                                <span class="badge" style="background:{cc}20;color:{cc};">{h(cat) if cat else "General"}</span>
                                <span class="badge bg-secondary">{len(books)} book{"" if len(books) == 1 else "s"}</span>
                                {f'<span class="badge bg-info">{s["total_books"]} planned</span>' if s.get("total_books", 0) > 0 else ""}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-lg-4">
                <div class="glass-card p-3 mb-3">
                    <div class="section-title"><i class="bi bi-info-circle"></i> About</div>
                    <div class="info-grid">
                        <div class="info-card"><div class="value">{len(books)}</div><div class="label">Books</div></div>
                        <div class="info-card"><div class="value">{sum(b.get("issue_count", 0) for b in books)}</div><div class="label">Total Issues</div></div>
                        <div class="info-card"><div class="value">{sum(b.get("available_copies", 0) for b in books)}</div><div class="label">Available</div></div>
                    </div>
                </div>
            </div>
        </div>
        <h5 class="fw-bold mb-3 animate-d1"><i class="bi bi-book-fill me-1"></i>Books in this Series</h5>
        <div class="row g-2 animate-d2">{BOOKS_HTML}</div>"""
        return render_page(s["name"], CONTENT)

    @app.route("/api/series/search")
    @login_required
    def api_series_search() -> Response:
        q = request.args.get("q", "")
        return jsonify({"series": _series.search_series(q) if q else []})

    @app.route("/api/series/suggestions")
    @login_required
    def api_series_suggestions() -> Response:
        q = request.args.get("q", "")
        return jsonify({"suggestions": _series.get_series_suggestions(q) if q else []})

    @app.route("/api/series/<series_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    @_rate_limit("20 per minute")
    def api_series_delete(series_id) -> Response:
        ok, msg = _series.delete_series(series_id)
        return jsonify({"success": ok, "message": msg})
