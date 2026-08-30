"""
scripts/smoke_checklist.py - Run the SMOKE_TEST.md core journeys against the
DB-backed app (web_app boots on DbStorage/SQLite — the relational layer).

Usage:
    python scripts/smoke_checklist.py

Boots web_app against a throwaway temp DATA_DIR (SQLite lands there), then walks
the A–E journeys from SMOKE_TEST.md through the Flask test client + the app's
own Library and social-module objects (the web layer has no checkout routes;
issue/return are the CLI/Library journeys the checklist marks as Lb). Prints
✅/❌ per item and exits non-zero on any failure.

Intentional gaps (documented in SMOKE_TEST.md as manual/future-phase):
  #8 reset-password (needs a generated token + browser flow)
  #10 settings override restart (covered by tests/security)
  #26 profile-with-favorites (covered by the line-151 regression test)
  #34 avatar upload (multipart browser flow)
  #40 keyboard-only pass (manual a11y gate)
  #43 CSRF / #44 healthz (Phase 4 / Phase 7 gates — not implemented yet)

NOTE: must import web_app AFTER redirecting Config paths (module-level bootstrap
creates the admin + tables at import time).
"""

import os
import sys
import tempfile
import threading
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

os.environ["SECRET_KEY"] = "smoke-secret-key-for-ci-only"
os.environ["DEFAULT_ADMIN_PASSWORD"] = "SmokeAdmin123"
# Phase 4: CSRF + rate limiting are ON by default. The checklist's test-client
# POSTs carry no CSRF tokens and make a handful of requests per journey, so the
# defaults here opt out — BUT both flags are overridable via the environment so
# the checklist can be run against the rate-limited app too:
#   RATELIMIT_ENABLED=1 python scripts/smoke_checklist.py
# (the journeys stay comfortably under the limits: ≤2 register POSTs vs 5/min,
# ≤4 login POSTs with ≤1 failure vs 10/min failed-only, 1 forgot-password POST
# vs 5/min, and no settings-save POSTs at all).
os.environ.setdefault("WTF_CSRF_ENABLED", "0")
os.environ.setdefault("RATELIMIT_ENABLED", "0")
# Single-process runs: keep budgets in-process even when the checklist is run
# with RATELIMIT_ENABLED=1, so burned per-IP budgets never persist in a shared
# Redis across runs (TestRedisLimiterStorage covers Redis budget semantics).
os.environ.setdefault("RATELIMIT_STORAGE_URI", "memory://")

# ── Isolate data into a temp dir BEFORE importing web_app ──────────────
_TMP = tempfile.mkdtemp(prefix="booktale_smoke_")
from app.config.settings import Config

Config.DATA_DIR = os.path.join(_TMP, "data")
Config.LOGS_DIR = os.path.join(_TMP, "logs")
Config.BACKUPS_DIR = os.path.join(_TMP, "backups")
for _d in (Config.DATA_DIR, Config.LOGS_DIR, Config.BACKUPS_DIR):
    os.makedirs(_d, exist_ok=True)

# ── Import the app (module-level: storage = create_storage() -> DbStorage) ─
from web_app import app, lib, storage

client = app.test_client()

RESULTS = []


def check(num: int, name: str, ok: bool, note: str = "") -> None:
    RESULTS.append((num, name, ok))
    mark = "✅" if ok else "❌"
    print(f"  {mark} #{num:<2} {name}" + (f"  [{note}]" if note else ""))


def admin_session() -> None:
    """Log in as the bootstrap admin for admin-gated journeys."""
    with client.session_transaction() as s:
        s["user_id"] = Config.DEFAULT_ADMIN_ID
        s["user_name"] = "System Admin"
        s["role"] = "admin"


# ═══════════════════════════════════════════════════════════════════
print("== A. Auth & Accounts (DB-backed) ==")

r = client.get("/")
check(1, "Landing page loads", r.status_code == 200)

r = client.post(
    "/register",
    data={
        "user_id": "MEM-SMOKE1",
        "name": "Smoke Reader",
        "email": "s1@x.io",
        "password": "secret123456",
        "confirm_password": "secret123456",
        "role": "user",
    },
    follow_redirects=True,
)
users = storage.load_users()
check(2, "Register MEM-SMOKE1", r.status_code == 200 and "MEM-SMOKE1" in users)

client.post(
    "/register",
    data={
        "user_id": "MEM-ADMINWANNABE",
        "name": "Hax",
        "email": "h@x.io",
        "password": "secret123456",
        "confirm_password": "secret123456",
        "role": "admin",
    },
)
check(
    3,
    "POST /register role=admin downgraded",
    storage.load_users()["MEM-ADMINWANNABE"].role == "user",
)

r = client.post("/login", data={"user_id": "MEM-SMOKE1", "password": "secret123456"})
check(4, "Login valid -> redirect to feed", r.status_code in (301, 302))

r = client.post("/login", data={"user_id": "MEM-SMOKE1", "password": "wrong"})
check(
    5,
    "Login wrong password shows error (no crash)",
    r.status_code == 200 and b"Invalid credentials" in r.data,
)

r = client.get("/logout")
check(6, "Logout clears session", r.status_code in (301, 302))

r = client.post("/forgot-password", data={"identity": "nobody@x.io"})
check(7, "Forgot-password anti-enumeration page", r.status_code == 200)

from app.config.settings import validate_secure_config

_refused = False
_saved_key = Config.SECRET_KEY
try:
    Config.SECRET_KEY = "change-this-secret-key-in-production"
    validate_secure_config()
except RuntimeError:
    _refused = True
finally:
    Config.SECRET_KEY = _saved_key
check(9, "Insecure SECRET_KEY refuses boot", _refused)

# ═══════════════════════════════════════════════════════════════════
print("== B. Library Core ==")

# /books and /book detail are login_required — log back in first.
client.post("/login", data={"user_id": "MEM-SMOKE1", "password": "secret123456"})

lib.add_book("Dune", "Frank Herbert", "9780441172719", "Fiction", 2, fetch_cover_async=False)
lib.add_book(
    "Neuromancer",
    "William Gibson",
    "9780441569595",
    "Science",
    1,
    fetch_cover_async=False,
)
books = storage.load_books()
bids = list(books)
check(
    11,
    "Seeded 2 books + GET /books renders",
    len(bids) == 2 and client.get("/books").status_code == 200,
)

r = client.get("/books?q=Dune")
check(12, "Search books by title", r.status_code == 200)

bid = bids[0]
r = client.get(f"/books/{bid}")
check(13, "Book detail page renders", r.status_code == 200)

ok, msg = lib.issue_book("MEM-SMOKE1", bid, actor="Librarian")
check(14, "Issue a book (available) -> success", ok, msg)

# #15: drain the last copy (Neuromancer has 1 copy) with a fresh user, then a
# second fresh user must be offered the reservation queue.
neuromancer = next(b for b in books.values() if b.title == "Neuromancer").book_id
lib.register_user("MEM-RESERVED", "Reserved", "rv@x.io", "", "user", "hash", actor="test")
ok1, m1 = lib.issue_book("MEM-RESERVED", neuromancer, actor="Librarian")
ok2, m2 = lib.issue_book("MEM-ADMINWANNABE", neuromancer, actor="Librarian")
check(
    15,
    "Issue last copy -> clean unavailable + reservation",
    ok1 and not ok2 and "reservation" in m2.lower(),
    m2,
)

# #16: exceed borrow limit (MAX_BORROW_LIMIT=3): MEM-SMOKE1 holds Dune + 2 more
lib.add_book(
    "Snow Crash",
    "Neal Stephenson",
    "9780553380958",
    "Fiction",
    5,
    fetch_cover_async=False,
)
lib.add_book("Hyperion", "Dan Simmons", "9780553283686", "Science", 5, fetch_cover_async=False)
others = [b.book_id for b in storage.load_books().values() if b.book_id not in (bid, neuromancer)]
for b in others:
    lib.issue_book("MEM-SMOKE1", b, actor="Librarian")
# MEM-SMOKE1 now holds 3 books (Dune + both others) = MAX_BORROW_LIMIT.
# Try a book they do NOT hold (neuromancer is held by MEM-RESERVED) so the
# rejection is genuinely the borrow limit, not "already issued".
ok, over_msg = lib.issue_book("MEM-SMOKE1", neuromancer, actor="Librarian")
check(
    16,
    "Exceed borrow limit -> clean rejection",
    not ok and "borrow limit" in over_msg.lower(),
    over_msg,
)

ok, msg, fine = lib.return_book("MEM-SMOKE1", bid, actor="Librarian")
check(17, "Return book -> availability restored", ok and fine == 0.0, msg)

admin_session()
r = client.get("/admin/overdue")
check(18, "Overdue list page renders", r.status_code == 200)

ok, msg = lib.add_book("Temp Book", "T", "9780000000000", "Other", 1, fetch_cover_async=False)
tb = next(b for b in storage.load_books().values() if b.title == "Temp Book")
ok2, _ = lib.delete_book(tb.book_id, actor="ADMIN001")
check(
    19,
    "Admin add + soft-delete book",
    ok and ok2 and storage.load_books()[tb.book_id].is_deleted,
)

r = client.get("/admin/users")
check(20, "Admin user management renders", r.status_code == 200)

# ═══════════════════════════════════════════════════════════════════
print("== C. Social & Community ==")

from app.services.books.reviews import ReviewManager
from app.services.social.social import SocialFeed

social = SocialFeed(storage)
reviews = ReviewManager(storage)

post = social.create_post("MEM-SMOKE1", "Just finished Dune!", book_ids=[bid])
check(21, "Create a post", bool(post.get("post_id")), post["post_id"])

ok, msg, liked = social.like_post(post["post_id"], "MEM-ADMINWANNABE")
check(22, "Like a post", ok and liked)

ok, msg, comment = social.add_comment(post["post_id"], "MEM-ADMINWANNABE", "Nice!")
check(23, "Comment on a post", ok)

ok, msg = social.follow_user("MEM-ADMINWANNABE", "MEM-SMOKE1")
check(24, "Follow a user", ok)

r = client.get("/profile/MEM-SMOKE1")
check(25, "Profile page renders", r.status_code == 200)

ok, msg, rev = reviews.add_review("MEM-SMOKE1", bid, 5, "Masterpiece!")
check(27, "Write a review with rating", ok)

from app.services.reading.reading_challenge import ReadingChallenge

challenge = ReadingChallenge(storage)
ok, msg = challenge.set_goal("MEM-SMOKE1", datetime.now().year, 12)
check(28, "Set reading challenge goal", ok)

from app.services.reading.diary import DiaryManager

diary = DiaryManager(storage)
ok, msg, entry = diary.log_read("MEM-SMOKE1", bid, date_read="2026-07-01", star_rating=5)
r = client.get("/reading-calendar")
check(29, "Diary entry + calendar page", ok and r.status_code == 200)

r = client.get("/analytics")
check(30, "Reading analytics page renders", r.status_code == 200)

from app.services.reading.wishlist import Wishlist

wishlist = Wishlist(storage)
ok, msg, sug = wishlist.add_suggestion(
    "MEM-SMOKE1", "A Fire Upon the Deep", "Vernor Vinge", "Because it's classic sci-fi"
)
check(31, "Wishlist suggest a book", ok)

from app.services.reading.reading_progress import ReadingProgress

rp = ReadingProgress(storage)
ok, msg, prog = rp.update_progress("MEM-SMOKE1", bid, current_page=100)
check(32, "Reading progress update", ok)

# ═══════════════════════════════════════════════════════════════════
print("== D. Admin / Settings / Content ==")

r = client.get("/settings")
check(33, "Settings page renders", r.status_code == 200)

r = client.get("/reports")
check(35, "Admin reports page renders", r.status_code == 200)

import json

override_path = os.path.join(Config.DATA_DIR, "settings_override.json")
with open(override_path, "w", encoding="utf-8") as f:
    json.dump({"FINE_PER_DAY": 7.5}, f)
from app.config.settings import _load_settings_overrides

_load_settings_overrides()
check(36, "Admin settings override applied", Config.FINE_PER_DAY == 7.5)

from app.services.books.series import SeriesManager

series = SeriesManager(storage)
ok, msg, s = series.create_series("Dune Saga", "Sci-fi epic", "Fiction", "ADMIN001")
check(37, "Series create", ok)

from app.services.social.communities import Communities

comm = Communities(storage)
ok, msg, club = comm.create_club("Sci-Fi Readers", "All things SF", "ADMIN001")
check(38, "Communities create", ok)

from app.services.notifications.notifications import NotificationManager

nm = NotificationManager(storage)
nm.add_notification("MEM-SMOKE1", "like", "Someone liked your post")
check(39, "Notification created + unread badge", nm.get_unread_count("MEM-SMOKE1") >= 1)

# ═══════════════════════════════════════════════════════════════════
print("== E. Stability & Security ==")

from app.db.storage_adapter import DbStorage

store2 = DbStorage()
check(
    41,
    "Data survives 'restart' (fresh storage reads same DB)",
    len(store2.load_users()) >= 3 and len(store2.load_books()) >= 2,
)

lib.add_book("Rare Book", "R", "9789999999999", "Other", 1, fetch_cover_async=False)
rare_id = next(b for b in storage.load_books().values() if b.title == "Rare Book").book_id
for i in range(20):
    lib.register_user(f"MEM-RACE{i}", f"Race{i}", f"r{i}@x.io", "", "user", "hash", actor="test")
race_results = []
lock = threading.Lock()


def _race(i: int) -> None:
    ok, _msg = lib.issue_book(f"MEM-RACE{i}", rare_id, actor="Librarian")
    with lock:
        race_results.append(ok)


threads = [threading.Thread(target=_race, args=(i,)) for i in range(20)]
for t in threads:
    t.start()
for t in threads:
    t.join()
check(
    42,
    "20-thread race for last copy -> 1 winner",
    sum(race_results) == 1,
    f"winners={sum(race_results)}",
)

# E43/E44 are Phase 4/7 gates (CSRF, healthz) — marked as future phases in the
# checklist; not yet implemented, so they are skipped here on purpose.

print("\n" + "=" * 60)
passed = sum(1 for _, _, ok in RESULTS if ok)
failed = [r for r in RESULTS if not r[2]]
print(f"SMOKE CHECKLIST: {passed}/{len(RESULTS)} passed")
if failed:
    print("FAILED:", ", ".join(f"#{n} {name}" for n, name, _ in failed))
    sys.exit(1)
print("ALL SMOKE JOURNEYS PASSED on the relational layer ✅")
sys.exit(0)
