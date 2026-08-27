"""
tasks.py - RQ background jobs (Phase 6).

Each function here is a unit of work executed by the RQ worker (`python
worker.py` in docker-compose). Jobs run in the worker process, NOT the web
process, so slow I/O (SMTP, external cover APIs) never blocks a request.

Job functions are deliberately pure module-level functions (RQ serializes
them by import path) and build their own storage handle via create_storage()
so they work identically whether enqueued through Redis or run inline by the
jobs facade's bounded fallback pool.

Three jobs today:
  - job_fetch_book_cover     : async cover/metadata fetch (was an unbounded
                               raw thread in library.py)
  - job_send_overdue_emails  : scheduled overdue-notice batch (cron daily)
  - job_purge_expired_tokens : reap expired auth tokens (cron hourly)
"""

from app.core.logger import log


def job_fetch_book_cover(book_id: str, title: str, author: str, isbn: str, storage=None) -> dict:
    """Fetch cover/metadata for one book and persist it (idempotent).

    `storage` is the caller's storage handle for the in-process pool path
    (so the write lands where the caller's data lives); the RQ worker path
    passes None and builds its own via create_storage().

    Returns a summary dict; never raises (a cover is an enhancement, not a
    requirement — the book must keep working even if OpenLibrary is down).
    """
    try:
        from app.services.books.cover_service import fetch_cover as _fetch_cover

        if storage is None:
            from app.db.storage_adapter import create_storage

            storage = create_storage()
        result = _fetch_cover(isbn=isbn, title=title, author=author)
        if not result or not result.get("cover_url"):
            log(f"Cover fetch returned nothing for '{title}'", "worker")
            return {"book_id": book_id, "ok": False, "reason": "no_cover"}
        books = storage.load_books(force=True)
        if book_id not in books:
            log(f"Cover fetch: book {book_id} no longer exists", "worker")
            return {"book_id": book_id, "ok": False, "reason": "book_gone"}
        b = books[book_id]
        b.cover_url = result["cover_url"]
        if result.get("description"):
            b.description = result["description"]
        b.cover_fetched = True
        b.cover_source = result.get("cover_source", "")
        if result.get("dominant_color"):
            b.dominant_color = result["dominant_color"]
        if result.get("page_count"):
            b.pages = result["page_count"]
        if result.get("genres"):
            b.genres = result["genres"]
        storage.save_books(books)
        log(f"Cover fetched for '{title}': {result['cover_source']}", "worker", book_id)
        return {
            "book_id": book_id,
            "ok": True,
            "source": result.get("cover_source", ""),
        }
    except (OSError, RuntimeError) as e:
        # Cover enhancement must never crash a batch: log with full context.
        log(f"Cover fetch failed for '{title}' ({book_id}): {e}", "worker", book_id)
        return {"book_id": book_id, "ok": False, "reason": "error"}


def job_send_overdue_emails() -> dict:
    """Compute the overdue list and send the email batch (cron, daily).

    No-op (with a log line) when SMTP is not configured or nothing is
    overdue, so a scheduled run is always safe and observable.
    """
    from app.db.service import LibraryService
    from app.services.email.email_notifier import send_overdue_batch

    overdue = LibraryService().get_overdue_list()
    if not overdue:
        log("Overdue email job: nothing overdue, skipping", "worker")
        return {"sent": 0, "failed": 0, "skipped": 0, "total": 0}
    log(f"Overdue email job: {len(overdue)} overdue item(s) found", "worker")
    result = send_overdue_batch(overdue)
    log(
        f"Overdue email job done: sent={result['sent']} failed={result['failed']} "
        f"skipped={result['skipped']}",
        "worker",
    )
    return result


def job_purge_expired_tokens() -> int:
    """Delete expired auth-token rows (cron, hourly). Returns count removed."""
    from app.services.auth.auth import purge_expired_tokens

    removed = purge_expired_tokens()
    log(f"Token purge job: removed {removed} expired token(s)", "worker")
    return removed
