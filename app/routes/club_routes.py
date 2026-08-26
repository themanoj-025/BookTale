"""
club_routes.py - Book club page routes.

Routes: /clubs, /clubs/<club_id>, /api/clubs/create, /api/clubs/<id>/join, /api/clubs/<id>/leave
"""

from flask import jsonify, request, session

from app.routes.helpers import avatar_html, cat_color
from app.routes.page_state import (
    communities,
    h,
    login_required,
    render_page,
    storage,
    make_rate_limit,
)


def init_club_routes(app) -> None:
    """Register club routes on the Flask app."""

    _rate_limit = make_rate_limit(app)

    # ════════════════════════════════════════════════════════════════
    # 1. BOOK CLUBS PAGE (/clubs)
    # ════════════════════════════════════════════════════════════════

    @app.route("/clubs")
    @login_required
    def clubs_page():
        uid = session["user_id"]
        clubs_data, total = communities.get_clubs(page=1) if communities else ([], 0)

        clubs_html = ""
        for c in clubs_data:
            member_count = len(c.get("members", []))
            is_member = uid in c.get("members", [])
            btn = '<a href="/clubs/{}" class="btn btn-primary btn-sm w-100">View Club</a>'.format(h(
                c["club_id"]
            ))
            if is_member:
                btn = (
                    '<div class="d-flex gap-1"><a href="/clubs/{}" class="btn btn-primary btn-sm flex-grow-1">View</a><span class="badge bg-success" style="display:flex;align-items:center;padding:.3rem .6rem;">Member</span></div>'.format(h(c["club_id"]))
                )
            clubs_html += """<div class="col-md-6 col-lg-4 mb-3">
                <div class="glass-card p-3 h-100">
                    <div class="d-flex align-items-center gap-3 mb-2">
                        <div style="width:48px;height:48px;border-radius:12px;background:linear-gradient(135deg,#4f46e5,#a855f7);display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                            <i class="bi bi-people-fill" style="color:white;font-size:1.2rem;"></i>
                        </div>
                        <div class="flex-grow-1" style="min-width:0;">
                            <div class="fw-bold" style="font-size:.9rem;">%s</div>
                            <small class="text-muted">%d members</small>
                        </div>
                    </div>
                    <p style="font-size:.8rem;color:var(--text-muted);margin-bottom:.5rem;">%s</p>
                    <div class="d-flex gap-1 flex-wrap">
                        <span class="badge" style="background:%s20;color:%s;">%s</span>
                    </div>
                    <div class="mt-2">%s</div>
                </div>
            </div>""" % (
                h(c["name"]),
                member_count,
                h(c.get("description", "")[:100]),
                cat_color(c.get("category", "General")),
                cat_color(c.get("category", "General")),
                h(c.get("category", "General")),
                btn,
            )

        if not clubs_html:
            clubs_html = """<div class="col-12"><div class="glass-card p-5 text-center">
                <div style="font-size:3rem;margin-bottom:.5rem;">📚</div>
                <h5>No Book Clubs Yet</h5>
                <p class="text-muted small">Create the first book club and invite readers to join!</p>
                <button class="btn btn-primary" onclick="showCreateClubForm()"><i class="bi bi-plus-lg"></i> Create Club</button>
            </div></div>"""

        CONTENT = (
            """<div class="animate-in">
    <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
        <h4 class="fw-bold mb-0"><i class="bi bi-people-fill me-2" style="color:var(--primary);"></i>Book Clubs <span class="text-muted fw-normal" style="font-size:.9rem;">(%d)</span></h4>
        <button class="btn btn-primary btn-sm" onclick="showCreateClubForm()"><i class="bi bi-plus-lg"></i> Create Club</button>
    </div>
    <div class="row g-3">CLUBS_HTML</div>
</div>

<!-- Create Club Modal -->
<div class="modal fade" id="createClubModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content">
    <div class="modal-header"><h5 class="modal-title"><i class="bi bi-people-fill me-1" style="color:var(--primary);"></i> Create Book Club</h5>
    <button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
    <div class="modal-body">
        <form id="createClubForm" onsubmit="return false;">
            <div class="mb-3"><label class="form-label">Club Name *</label><input type="text" id="clubName" class="form-control" placeholder="e.g. Fantasy Readers" required></div>
            <div class="mb-3"><label class="form-label">Description</label><textarea id="clubDesc" class="form-control" rows="3" placeholder="What is this club about?"></textarea></div>
            <div class="mb-3"><label class="form-label">Category</label><select id="clubCategory" class="form-select">
                <option>General</option><option>Fiction</option><option>Science Fiction</option><option>Fantasy</option>
                <option>Mystery</option><option>Romance</option><option>Non-Fiction</option><option>History</option>
                <option>Philosophy</option>
            </select></div>
            <div class="mb-3"><label class="form-label">Max Members</label><input type="number" id="clubMaxMembers" class="form-control" value="50" min="2" max="500"></div>
        </form>
    </div>
    <div class="modal-footer">
        <button class="btn btn-outline" data-bs-dismiss="modal">Cancel</button>
        <button class="btn btn-primary" onclick="submitCreateClub()"><i class="bi bi-check-lg"></i> Create</button>
    </div>
</div></div></div>

<script>
function showCreateClubForm(){var m=new bootstrap.Modal(document.getElementById("createClubModal"));m.show()}
function submitCreateClub(){
    var data={
        name:document.getElementById("clubName").value.trim(),
        description:document.getElementById("clubDesc").value.trim(),
        category:document.getElementById("clubCategory").value,
        max_members:parseInt(document.getElementById("clubMaxMembers").value)||50,
        is_public:true
    };
    if(!data.name){showToast("Enter a club name","error");return}
    fetch("/api/clubs/create',{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify(data)
    }).then(function(r){return r.json()}).then(function(d){
        if(d.success){showToast(d.message,"success");setTimeout(function(){location.reload()},1000)}
        else{showToast(d.error||"Failed","error")}
    });
}
</script>"""
            % total
        )

        CONTENT = CONTENT.replace("CLUBS_HTML", clubs_html)
        return render_page("Book Clubs", CONTENT)

    # ════════════════════════════════════════════════════════════════
    # 2. CLUB DETAIL PAGE (/clubs/<club_id>)
    # ════════════════════════════════════════════════════════════════

    @app.route("/clubs/<club_id>")
    @login_required
    def club_detail_page(club_id):
        uid = session["user_id"]
        club = communities.get_club(club_id) if communities else None

        if not club:
            return render_page(
                "Club Not Found",
                '<div class="text-center py-5"><div style="font-size:4rem;">🔍</div><h5>Club not found</h5><p class="text-muted">This book club may have been deleted.</p><a href="/clubs" class="btn btn-primary btn-sm"><i class="bi bi-arrow-left"></i> Browse Clubs</a></div>',
            )

        is_member = uid in club.get("members", [])
        member_count = len(club.get("members", []))

        # Enrich members
        users_data = storage.load_users()
        members_html = ""
        for mid in club.get("members", [])[:12]:
            mu = users_data.get(mid)
            name = mu.name if mu else mid[:8]
            role_badge = (
                '<span class="badge bg-danger" style="font-size:.5rem;">Owner</span>'
                if mid == club.get("owner_id")
                else (
                    '<span class="badge bg-warning text-dark" style="font-size:.5rem;">Mod</span>'
                    if mid in club.get("moderators", [])
                    else ""
                )
            )
            members_html += (
                '<div class="d-flex align-items-center gap-2 mb-1">'
                + avatar_html(name, 28)
                + '<span class="small">'
                + h(name[:20])
                + "</span> "
                + role_badge
                + "</div>"
            )
        if not members_html:
            members_html = '<div class="text-muted small py-2">No members yet.</div>'

        # Current book
        current_book = club.get("current_book", {})
        book_html = ""
        if current_book:
            bid = current_book.get("book_id", "")
            btitle = current_book.get("title", "")
            bauth = current_book.get("author", "")
            book_html = (
                '<div class="glass-card p-3 mb-3"><div class="section-title"><i class="bi bi-book-fill text-primary"></i> Currently Reading</div><div class="d-flex align-items-center gap-2"><div style="width:36px;height:36px;border-radius:8px;background:var(--primary);display:flex;align-items:center;justify-content:center;color:white;"><i class="bi bi-book-fill"></i></div><div><a href="/books/'
                + h(bid)
                + '" class="fw-bold text-decoration-none" style="color:var(--text);font-size:.9rem;">'
                + h(btitle)
                + '</a><br><small class="text-muted">'
                + h(bauth)
                + "</small></div></div></div>"
            )
        else:
            book_html = '<div class="glass-card p-3 mb-3 text-center text-muted small py-3"><i class="bi bi-book"></i> No current book selected.</div>'

        # Forum topics
        forum_html = ""
        try:
            topics, _t_total = communities.get_topics(club_id)
            for t in topics[:8]:
                forum_html += (
                    '<div class="d-flex align-items-center gap-2 mb-2 p-2" style="border-radius:8px;border:1px solid var(--border);cursor:pointer;" onclick="showToast(\'Topic view coming soon\',\'info\')"><div style="width:32px;height:32px;border-radius:50%;background:var(--primary-light);display:flex;align-items:center;justify-content:center;"><i class="bi bi-chat-dots" style="color:var(--primary);"></i></div><div class="flex-grow-1" style="min-width:0;"><div class="fw-bold small">'
                    + h(t["title"][:50])
                    + '</div><small class="text-muted">by '
                    + h(t.get("author_name", ""))
                    + " &middot; "
                    + str(t.get("replies_count", 0))
                    + " replies</small></div></div>"
                )
        except (AttributeError, TypeError, KeyError):
            pass
        if not forum_html:
            forum_html = '<div class="text-center text-muted small py-3">No discussions yet. Start one!</div>'

        cc = cat_color(club.get("category", "General"))
        join_leave_btn = ""
        if is_member:
            join_leave_btn = (
                '<button class="btn btn-outline btn-sm" onclick="leaveClub(\''
                + h(club_id)
                + '\')"><i class="bi bi-box-arrow-left"></i> Leave Club</button>'
            )
        else:
            join_leave_btn = (
                '<button class="btn btn-primary btn-sm" onclick="joinClub(\''
                + h(club_id)
                + '\')"><i class="bi bi-person-plus"></i> Join Club</button>'
            )

        CONTENT = """<div class="animate-in">
    <div class="row">
        <div class="col-lg-8">
            <div class="glass-card p-4 mb-3">
                <div class="d-flex gap-3">
                    <div style="width:56px;height:56px;border-radius:14px;background:linear-gradient(135deg,%s,%sdd);display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                        <i class="bi bi-people-fill" style="color:white;font-size:1.3rem;"></i>
                    </div>
                    <div class="flex-grow-1">
                        <h4 class="fw-bold mb-1">%s</h4>
                        <p class="text-muted mb-1" style="font-size:.85rem;">%s</p>
                        <div class="d-flex gap-2 flex-wrap">
                            <span class="badge" style="background:%s20;color:%s;">%s</span>
                            <span class="badge bg-secondary">%d members</span>
                            %s
                        </div>
                    </div>
                    <div>%s</div>
                </div>
            </div>
            %s
            <div class="glass-card p-3 mb-3">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <div class="section-title mb-0"><i class="bi bi-chat-dots-fill"></i> Discussions</div>
                    <button class="btn btn-primary btn-sm" onclick="showToast('Topic creation coming soon','info')"><i class="bi bi-plus-lg"></i> New Topic</button>
                </div>
                %s
            </div>
        </div>
        <div class="col-lg-4">
            <div class="glass-card p-3 mb-3">
                <div class="section-title"><i class="bi bi-people-fill"></i> Members (%d)</div>
                <div style="max-height:300px;overflow-y:auto;">%s</div>
                <a href="/clubs" class="btn btn-outline btn-sm w-100 mt-2">All Clubs</a>
            </div>
        </div>
    </div>
</div>
<script>
function joinClub(cid) {
    fetch("/api/clubs/" + cid + "/join", {method:"POST"})
        .then(function(r){return r.json()})
        .then(function(d){if(d.success){showToast(d.message,"success");setTimeout(function(){location.reload()},1000)}else{showToast(d.error,"error")}});
}
function leaveClub(cid) {
    if(!confirm("Leave this club?")) return;
    fetch("/api/clubs/" + cid + "/leave", {method:"POST"})
        .then(function(r){return r.json()})
        .then(function(d){if(d.success){showToast(d.message,"success");setTimeout(function(){location.reload()},1000)}else{showToast(d.error,"error")}});
}
</script>""" % (
            cc,
            cc,
            h(club["name"]),
            h(club.get("description", "")[:150]),
            cc,
            cc,
            h(club.get("category", "General")),
            member_count,
            (
                '<span class="badge bg-success">Public</span>'
                if club.get("is_public", True)
                else '<span class="badge bg-secondary">Private</span>'
            ),
            join_leave_btn,
            book_html,
            forum_html,
            member_count,
            members_html,
        )

        return render_page(club["name"], CONTENT)

    # ════════════════════════════════════════════════════════════════
    # 3. CLUB API ENDPOINTS
    # ════════════════════════════════════════════════════════════════

    @app.route("/api/clubs/create", methods=["POST"])
    @login_required
    @_rate_limit("10 per minute")
    def api_create_club():
        uid = session["user_id"]
        data = request.get_json() or {}
        ok, msg, club = (
            communities.create_club(
                data.get("name", ""),
                data.get("description", ""),
                uid,
                category=data.get("category", "General"),
                is_public=data.get("is_public", True),
                max_members=int(data.get("max_members", 50)),
            )
            if communities
            else (False, "Clubs module not available", None)
        )
        return jsonify(
            {"success": ok, "message": msg, "club": club}
        )

    @app.route("/api/clubs/<club_id>/join", methods=["POST"])
    @login_required
    @_rate_limit("60 per minute")
    def api_club_join(club_id):
        uid = session["user_id"]
        ok, msg = (
            communities.join_club(club_id, uid) if communities else (False, "Clubs unavailable")
        )
        return jsonify({"success": ok, "message": msg})

    @app.route("/api/clubs/<club_id>/leave", methods=["POST"])
    @login_required
    def api_club_leave(club_id):
        uid = session["user_id"]
        ok, msg = (
            communities.leave_club(club_id, uid) if communities else (False, "Clubs unavailable")
        )
        return jsonify({"success": ok, "message": msg})

    return app
