"""
scripts/smoke_live.py - Run the SMOKE_TEST.md top journeys against a REAL
HTTP server with CSRF protection AND rate limiting ENABLED (the production
defaults), to prove the Phase-4 gates don't break any top user journey.

This complements scripts/smoke_checklist.py (which runs the full A-E journey
set through the in-process test client, but with CSRF/rate-limiting opted
out). smoke_live.py boots web_app on a real socket via werkzeug's
make_server, then drives the rate-limited journeys over real HTTP with the
CSRF tokens a browser would submit:

  A. Auth (per-IP limits)
     - GET /login, /register, /forgot-password page loads x10 each
       -> all 200, NEVER 429 (page loads must not consume the budget)
     - POST /register (valid) -> 200 registered
     - POST /register role=admin -> 200, role downgraded to user
     - POST /login valid -> 302 redirect to feed (valid login not blocked)
     - POST /login wrong x10 -> 200 error each (failures allowed up to 10)
     - POST /login wrong 11th -> 429 (per-IP failure throttle fires)
     - POST /forgot-password -> 200 anti-enumeration
     - POST /forgot-password x5 more -> 429 on the 6th POST (5/min budget)

  E. Phase gates (per-user limits)
     - POST /api/settings/save WITHOUT a CSRF token -> 400 (gate #43)
     - POST /api/settings/save WITH X-CSRFToken -> 200 (fetch-style works)
     - valid password change -> 200 and does NOT consume the per-user budget
     - wrong-current-password x10 -> 200 error; 11th -> 429 (per-user)
     - GET /healthz -> 200, GET /readyz -> 200 (gate #44)

Journey order matters: the settings (per-user) probes run BEFORE the login
failure burst, because 10 failed logins exhaust the per-IP login budget for
~1 minute.

Usage:
    python scripts/smoke_live.py

Boots web_app with CSRF + rate limiting ON (WTF_CSRF_ENABLED=1,
RATELIMIT_ENABLED=1) against a throwaway temp DATA_DIR, picks a free port,
and exits non-zero on any failure.
"""

import os
import re
import socket
import sys
import tempfile
import threading
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# ── Secure, rate-limited boot (the production defaults) BEFORE importing ──
os.environ["SECRET_KEY"] = "smoke-live-secret-key-for-ci-only"
os.environ["DEFAULT_ADMIN_PASSWORD"] = "SmokeLiveAdmin123"
os.environ["WTF_CSRF_ENABLED"] = "1"
os.environ["RATELIMIT_ENABLED"] = "1"
# Single-process smoke: pin rate-limit budgets to in-process memory so the
# 11 burned login failures (keyed on 127.0.0.1) don't persist in a shared
# Redis between runs or leak into dev sessions. Multi-worker/restart budget
# semantics are covered by TestRedisLimiterStorage, not this smoke.
os.environ.setdefault("RATELIMIT_STORAGE_URI", "memory://")

_TMP = tempfile.mkdtemp(prefix="booktale_smoke_live_")
from app.config.settings import Config

Config.DATA_DIR = os.path.join(_TMP, "data")
Config.LOGS_DIR = os.path.join(_TMP, "logs")
Config.BACKUPS_DIR = os.path.join(_TMP, "backups")
for _d in (Config.DATA_DIR, Config.LOGS_DIR, Config.BACKUPS_DIR):
    os.makedirs(_d, exist_ok=True)

import requests

from web_app import app, storage

RESULTS = []


def check(num: int, name: str, ok: bool, note: str = "") -> None:
    RESULTS.append((num, name, ok))
    mark = "✅" if ok else "❌"
    print(f"  {mark} #{num:<2} {name}" + (f"  [{note}]" if note else ""))


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _csrf_field(html: str) -> str:
    """Extract the hidden form csrf_token a browser would submit."""
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ""


def _csrf_meta(html: str) -> str:
    """Extract the fetch-style X-CSRFToken from base.html's meta tag."""
    m = re.search(r'<meta name="csrf-token" content="([^"]+)">', html)
    return m.group(1) if m else ""


# ── Boot the real server on a free port ──────────────────────────────────
PORT = _free_port()
BASE = f"http://127.0.0.1:{PORT}"
from werkzeug.serving import make_server

_server = make_server("127.0.0.1", PORT, app, threaded=True)
_thread = threading.Thread(target=_server.serve_forever, daemon=True)
_thread.start()

_ready = False
for _ in range(50):
    try:
        if requests.get(f"{BASE}/healthz", timeout=2).status_code == 200:
            _ready = True
            break
    except requests.RequestException:
        time.sleep(0.2)
if not _ready:
    print("❌ live server failed to become ready")
    sys.exit(1)
print(f"✅ live server ready at {BASE} (CSRF ON, RATELIMIT ON)\n")


def _get(session, path, **kw) -> None:
    return session.get(BASE + path, timeout=5, **kw)


def _post(session, path, data=None, headers=None) -> None:
    return session.post(BASE + path, data=data, headers=headers, timeout=5)


# ═══════════════════════════════════════════════════════════════════
print("== A. Auth over real HTTP (rate limits + CSRF active) ==")

r = _get(requests.Session(), "/")
check(1, "Landing page loads (no auth)", r.status_code == 200)

# Register: page loads must never 429 even if the 5/min POST budget is
# scoped to POSTs only — this run proves the scoping holds.
s = requests.Session()
loads_ok = True
for _i in range(10):
    rr = _get(s, "/register")
    if rr.status_code != 200:
        loads_ok = False
        break
check(2, "GET /register x10 -> all 200, never 429", loads_ok)

r = _post(
    s,
    "/register",
    {
        "user_id": "MEM-LIVE1",
        "name": "Live Reader",
        "email": "live1@x.io",
        "password": "secret123456",
        "confirm_password": "secret123456",
        "role": "user",
        "csrf_token": _csrf_field(rr.text),
    },
)
check(3, "POST /register valid -> registered", r.status_code == 200)

# role=admin downgrade (verify against storage in the same process)
r2 = _get(s, "/register")
r = _post(
    s,
    "/register",
    {
        "user_id": "MEM-LIVEHACK",
        "name": "Hax",
        "email": "h@x.io",
        "password": "secret123456",
        "confirm_password": "secret123456",
        "role": "admin",
        "csrf_token": _csrf_field(r2.text),
    },
)
_users = storage.load_users()
check(
    4,
    "POST /register role=admin -> role downgraded to user",
    r.status_code == 200 and _users["MEM-LIVEHACK"].role == "user",
)

# Login: page loads never 429; valid login works; failures cap at 10/min.
s = requests.Session()
loads_ok = True
for _i in range(10):
    rr = _get(s, "/login")
    if rr.status_code != 200:
        loads_ok = False
        break
check(5, "GET /login x10 -> all 200, never 429", loads_ok)

# allow_redirects=False: requests auto-follows the 302 to /feed by default,
# so the asserted status would be the final 200, not the redirect itself.
r = s.post(
    BASE + "/login",
    data={
        "user_id": "MEM-LIVE1",
        "password": "secret123456",
        "csrf_token": _csrf_field(rr.text),
    },
    timeout=5,
    allow_redirects=False,
)
check(
    6,
    "POST /login valid -> redirect to feed",
    r.status_code in (301, 302),
    f"got {r.status_code}",
)

# ═══════════════════════════════════════════════════════════════════
print("== E. Phase gates over real HTTP (CSRF + per-user limits) ==")

# Settings journeys key on the ACCOUNT (per-user budget), independent of the
# per-IP login budget — but they still need a logged-in session.
page = _get(s, "/settings")
check(7, "GET /settings page loads (logged in)", page.status_code == 200)
meta_token = _csrf_meta(page.text)

# Gate #43: a POST without a CSRF token is rejected. Empty body on purpose
# (CSRFProtect rejects the tokenless POST before the view ever parses it).
r = _post(s, "/api/settings/save", data="", headers={"Content-Type": "application/json"})
check(
    8,
    "POST /api/settings/save without CSRF token -> 400",
    r.status_code == 400,
    f"got {r.status_code}",
)

# Fetch-style POST with the X-CSRFToken header works (like the frontend).
r = _post(
    s,
    "/api/settings/save",
    data='{"theme":"dark"}',
    headers={"Content-Type": "application/json", "X-CSRFToken": meta_token},
)
ok8 = r.status_code == 200 and "success" in r.text.lower()
check(9, "POST /api/settings/save with X-CSRFToken -> 200", ok8, f"got {r.status_code}")

# Valid password change succeeds and does NOT consume the per-user budget.
r = _post(
    s,
    "/api/settings/save",
    data='{"current_password":"secret123456","new_password":"newpass456789"}',
    headers={"Content-Type": "application/json", "X-CSRFToken": meta_token},
)
check(10, "Valid password change -> 200 (no budget consumed)", r.status_code == 200)

# Wrong current password x10 -> 200 error each (allowed up to 10/min)...
fails = []
for _i in range(10):
    rr = _post(
        s,
        "/api/settings/save",
        data='{"current_password":"nope","new_password":"x12345678901"}',
        headers={"Content-Type": "application/json", "X-CSRFToken": meta_token},
    )
    fails.append(rr.status_code)
check(
    11,
    "Wrong current password x10 -> all 200 (per-user 10/min)",
    all(c == 200 for c in fails),
    f"statuses={fails}",
)

# ...and the 11th failure trips the per-user throttle.
r = _post(
    s,
    "/api/settings/save",
    data='{"current_password":"nope","new_password":"x12345678901"}',
    headers={"Content-Type": "application/json", "X-CSRFToken": meta_token},
)
check(
    12,
    "Wrong current password #11 -> 429 (per-user throttle)",
    r.status_code == 429,
    f"got {r.status_code}",
)

# Gate #44: health endpoints.
check(13, "GET /healthz -> 200", _get(requests.Session(), "/healthz").status_code == 200)
check(14, "GET /readyz -> 200", _get(requests.Session(), "/readyz").status_code == 200)

# ═══════════════════════════════════════════════════════════════════
print("== A (cont). Failure throttles fire only on abuse ==")

# Login failures: 10 allowed, 11th -> 429 (deduct_when counts only failures).
s = requests.Session()
fails = []
for _i in range(10):
    page = _get(s, "/login")
    rr = _post(
        s,
        "/login",
        {
            "user_id": "MEM-LIVE1",
            "password": "wrong",
            "csrf_token": _csrf_field(page.text),
        },
    )
    fails.append(rr.status_code)
check(
    15,
    "POST /login wrong x10 -> all 200 (allowed up to 10/min)",
    all(c == 200 for c in fails),
    f"statuses={fails}",
)

page = _get(s, "/login")
r = _post(
    s,
    "/login",
    {
        "user_id": "MEM-LIVE1",
        "password": "wrong",
        "csrf_token": _csrf_field(page.text),
    },
)
check(
    16,
    "POST /login wrong #11 -> 429 (per-IP failure throttle)",
    r.status_code == 429,
    f"got {r.status_code}",
)

# Forgot-password: page loads exempt; 5/min all-POST budget.
s = requests.Session()
loads_ok = True
for _i in range(10):
    rr = _get(s, "/forgot-password")
    if rr.status_code != 200:
        loads_ok = False
        break
check(17, "GET /forgot-password x10 -> all 200, never 429", loads_ok)

r = _post(
    s,
    "/forgot-password",
    {
        "identity": "nobody@x.io",
        "csrf_token": _csrf_field(rr.text),
    },
)
check(18, "POST /forgot-password -> 200 anti-enumeration", r.status_code == 200)

burst = []
for _i in range(5):
    page = _get(s, "/forgot-password")
    rr = _post(
        s,
        "/forgot-password",
        {
            "identity": "nobody@x.io",
            "csrf_token": _csrf_field(page.text),
        },
    )
    burst.append(rr.status_code)
check(
    19,
    "POST /forgot-password x5 more -> 429 on the 6th POST",
    all(c == 200 for c in burst[:-1]) and burst[-1] == 429,
    f"statuses={burst}",
)

_server.shutdown()

print("\n" + "=" * 60)
passed = sum(1 for _, _, ok in RESULTS if ok)
failed = [r for r in RESULTS if not r[2]]
print(f"LIVE SMOKE CHECKLIST: {passed}/{len(RESULTS)} passed")
if failed:
    print("FAILED:", ", ".join(f"#{n} {name}" for n, name, _ in failed))
    sys.exit(1)
print("ALL LIVE JOURNEYS PASS with CSRF + rate limiting ENABLED ✅")
sys.exit(0)
