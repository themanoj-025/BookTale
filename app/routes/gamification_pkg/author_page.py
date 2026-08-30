"""Author page route — display books by a specific author."""

from collections import Counter
from urllib.parse import unquote

from app.routes.social_shared import render_page, storage
from app.routes.helpers import cat_color, h


def render_author_page(author_name: str) -> str:
    """Render the author page showing all books by this author."""
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
            f'<a href="/books/{b.book_id}" class="text-decoration-none col-6 col-md-4 col-lg-3 mb-2">'
            '<div class="glass-card p-2 text-center" style="cursor:pointer;">'
            f'<div style="font-size:1.2rem;color:{cc};"><i class="bi bi-book-fill"></i></div>'
            f'<div class="fw-bold small">{h(b.title)[:40]}</div>'
            f'<small class="text-muted">{h(b.category)}</small>'
            f'<div class="mt-1">{avail}</div>'
            '</div></a>'
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
