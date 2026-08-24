# ADR 0007 — CSRF Enabled by Default + Rate-Limited Auth Endpoints

- **Status:** Accepted (2026-08-01)
- **Deciders:** Project owner, acting senior staff engineer
- **Related code:** `web_app.py` (CSRF block, `_rate_limit`,
  `app.extensions["booktale_limiter"]`, auth + admin routes),
  `social_routes.py` + `new_features_routes.py` (route-module `_rate_limit`
  helpers and per-route decorators), `templates/base.html` (meta csrf-token +
  fetch interceptor), `templates/auth/*.html` (hidden inputs),
  `requirements.txt`
- **Related ADRs:** ADR 0002 (role whitelist — CSRF protects the same session
  cookie that carries `role`)

---

## Context

Roughly 90 state-changing POST/PUT/PATCH/DELETE endpoints shipped with **no CSRF
protection**. The session cookie is the auth mechanism and carries the `role`
claim, so a cross-site request could perform actions (settings changes, posts,
admin operations) as a logged-in victim without their consent.

The first Phase-4 pass made CSRF **opt-in** via an `ENABLE_CSRF=1` env var —
i.e. insecure by default: zero endpoints protected in a default deployment.
`flask-wtf` and `flask-limiter` were also used in code but never declared in
`requirements.txt`. Login/register/forgot-password had no rate limiting beyond
an in-memory per-user lockout (a per-user DoS primitive, not IP throttling).

## Decision

**CSRF — enabled by default:**

- `WTF_CSRF_ENABLED` env var, default `"1"` → `CSRFProtect` is always
  initialized (when flask-wtf imports) and validates a per-session token on
  every POST/PUT/PATCH/DELETE. The flag is read **at request time**, so tests
  can toggle `app.config["WTF_CSRF_ENABLED"]` per-test.
- **Token plumbing app-wide:**
  - hidden `csrf_token` inputs in the login/register/forgot templates and in
    the string-built reset-password and series-create forms;
  - `base.html` emits `<meta name="csrf-token">` plus a small fetch interceptor
    that adds the `X-CSRFToken` header to every non-GET `fetch()`. This covers
    the entire fetch-based JSON API surface (settings, feed actions, wishlist,
    bookmarks, …) without editing 14 JS files.
- **Socket.IO is naturally exempt** — its WSGI middleware
  (`_SocketIOMiddleware`) short-circuits before Flask's `before_request` hooks,
  so long-polling POSTs never hit CSRF validation. No exemption code needed.

**Rate limiting — on by default, applied to auth and sensitive actions:**

- `RATELIMIT_ENABLED` env var, default `"1"`. It must be set in `app.config`
  **before** `limiter.init_app(app)`, because flask-limiter captures
  `self.enabled` from config at init time (and returns early when disabled).
- **Storage backend (Phase 6): Redis, not process memory.** The limiter is
  built with `storage_uri=Config.REDIS_URL` (default
  `redis://localhost:6379/0`; the compose stack passes `redis://redis:6379/0`
  via the already-declared `redis:7-alpine` service) so budgets survive
  process restarts and are shared across multiple gunicorn workers — the two
  properties per-process `memory://` storage cannot provide. Single-process
  runs/tests opt out with `RATELIMIT_STORAGE_URI=memory://` (helper
  `_limiter_storage_uri()`). `in_memory_fallback_enabled=True` degrades to a
  per-process budget (fail-open, logged) if Redis is unreachable, rather than
  500ing every limited request — the same graceful-degradation stance as the
  `/readyz` DB probe. Note the trade-off: while Redis is down, budgets are
  per-worker, so a determined attacker could spread requests across workers
  to evade them; this is accepted in favor of never 500ing a limited request
  (and the outage is logged). Storage is lazy (flask-limiter resolves it on
  first use), so booting without Redis never connects at import time. Smoke
  scripts pin `RATELIMIT_STORAGE_URI=memory://` so their burned per-IP
  budgets never persist in the shared Redis between runs.
- One `_rate_limit(limit_value, **kwargs)` decorator (web_app.py) wraps
  `limiter.limit(...)` and falls back to a no-op when flask-limiter is absent.
  The route modules (`social_routes.py`, `new_features_routes.py`) cannot
  import web_app (circular), so web_app exposes the single Limiter instance as
  `app.extensions["booktale_limiter"]`. This key exists because flask-limiter
  4.x registers itself under `app.extensions["limiter"]` as a **set** — and
  not at all when `RATELIMIT_ENABLED=0` — so that key must not be relied on.
- Limits on top of the app-wide **200/min** default. Most key per remote IP;
  the two password-change endpoints key per **account** (`key_func=_user_key`
  → `user:<user_id>` from the session) so a distributed attacker cannot evade
  the budget by spreading requests across many source IPs:

| Route | Key | Limit | What counts |
| --- | --- | --- | --- |
| `/login` (POST only) | IP | 10/min | `deduct_when` — only **failed** credential attempts; GET page loads exempt |
| `/register`, `/forgot-password`, `/reset-password` (POST only) | IP | 5/min | `methods=["POST"]` + `exempt_when` GET — POST submissions only; GET page loads exempt |
| `/api/settings/save` | **account** | 10/min | `deduct_when` — only **failed password changes** |
| `/api/admin/settings/save` | **account** | 10/min | `deduct_when` — only **failed admin-password verifications** |
| `/api/profile/update` | IP | 10/min | `deduct_when` — only requests that **submit an `email` field** (account-takeover vector; email is a reset identity) |
| `/api/upload` | IP | 10/min | every request (file-write / storage-abuse vector) |
| `/api/series/<series_id>/delete` | IP | 20/min | every request (admin destructive) |
| `/api/wishlist/<suggestion_id>/moderate` | IP | 20/min | every request (admin moderation) |

- **Shared-surface & engagement endpoints** (audit pass over the remaining
  non-sensitive POSTs): every POST that writes shared-surface content (feed
  spam vector) or moves engagement counters gets an explicit ceiling, so one
  compromised session can't flood the feed or stuff votes under the 200/min
  default. Three tiers, all keyed per IP:

| Route | Limit | Why |
| --- | --- | --- |
| `/api/posts` (create), `/api/posts/<id>/repost` | 30/min | content spam / amplification |
| `/api/posts/<id>/comments`, `/api/comments/<id>/reply`, `/api/reviews/<id>/comments` | 30/min (POST only) | comment spam — GET fetches exempt |
| `/api/reviews/<book_id>`, `/api/books/<id>/review` | 30/min | review spam |
| `/api/lists` (create), `/api/shelves/create` | 30/min | public list / shelf spam |
| `/api/wishlist/<id>/comment` | 30/min | suggestion comment spam |
| `/api/clubs/create`, `/api/wishlist/suggest` | 10/min | create-heavy: club spam / moderation-queue flood |
| `/api/ai/chat` | 30/min | companion spam / load |

  The three auth **form** routes were initially scoped as plain `5/min`
  (`@_rate_limit("5 per minute")` with no method restriction), which made GET
  page loads consume the budget — the 6th page load in a minute returned 429
  (a real journey breaker). `scripts/smoke_live.py` (real-HTTP run with
  rate limiting ON) exposed this; all three now mirror the login route's
  GET-exempt split (`methods=["POST"]` + `exempt_when`), and the fix is locked
  by `TestRateLimiting::test_auth_form_*` probes + a decorator-scoping
  assertion.
| `/api/posts/<id>/like`, `/api/posts/<id>/vote`, `/api/reviews/<id>/helpful`, `/api/follow/<user_id>`, `/api/lists/<id>/follow`, `/api/lists/<id>/upvote`, `/api/wishlist/<id>/vote`, `/api/clubs/<id>/join` | 60/min | engagement manipulation (like/vote/helpful farming, follow churn) |

  **Deliberately left at the 200/min default** (self-scoped actions that only
  mutate the caller's own data and have no shared-surface or cross-user side
  effects): notifications read/read-all, bookshelves add/remove,
  `/api/profile/favorites/{add,remove,reorder}`, post/shelf delete + shelf
  rename, club leave, reading-goal/progress updates, bookmarks, diary log.

  `_user_key()` falls back to `ip:<remote_addr>` when no session exists
  (defensive; both password-change endpoints are login/admin-required, so a
  session is always present by the time the limiter runs).

**Session-cookie hardening (same phase):** `SESSION_COOKIE_HTTPONLY=True` and
`SESSION_COOKIE_SAMESITE=Lax` are always set; `SESSION_COOKIE_SECURE` is set in
production (non-debug + `SESSION_COOKIE_SECURE=1` env). HttpOnly keeps the
session cookie out of JS; SameSite=Lax blocks cross-site POSTs from carrying it
— complementary to the CSRF token itself.

**Test / CI opt-out (explicit, documented):**

- `tests/security/test_web_security.py` and `scripts/smoke_checklist.py` set
  `WTF_CSRF_ENABLED=0` and `RATELIMIT_ENABLED=0` before importing the app —
  the test client has no token plumbing and bursts requests.

**Dependencies declared:** `flask-wtf>=1.2.0`, `flask-limiter>=3.5.0` added to
`requirements.txt`.

## Consequences

### Positive

- Secure by default: every state-changing endpoint requires a valid CSRF token.
- One fetch interceptor covers the whole XHR surface; one decorator pattern
  covers auth throttling.
- Per-IP throttling replaces the per-user lockout as the first line of defense
  (the lockout remains, but the *attempt* is throttled, not the victim's
  account).
- Explicit env opt-outs make test-mode behavior visible and auditable.

### Negative / Trade-offs

- Every form and fetch must now carry a token (done app-wide; new forms must
  follow the same pattern).
- Once a key exhausts a failure budget (e.g. 10 failed logins/min for an IP,
  or 10 failed password changes/min for an account), further requests from
  that key on that route return 429 until the window resets — inherent to
  check-before-view per-key limiting. Because `deduct_when` skips successes
  and benign actions, real users are unaffected.
- Tests must remember the two opt-out env vars — a small coupling between the
  test suite and web-app boot.

## Alternatives considered

- **Exempt `/api/*` from CSRF** — rejected: leaves the largest state-changing
  surface unprotected.
- **Per-endpoint opt-in CSRF** (`ENABLE_CSRF`) — rejected: insecure by default;
  this was the status quo being fixed.
- **Referer/origin-only CSRF** — rejected: weaker than a signed token; breaks
  under strict referrer policies.
- **Add the token to every JS file by hand** — rejected: 14-file churn with a
  real risk of missing an endpoint.

## Regression coverage

- `TestCSRFProtection`: tokenless POST → 400; same POST with a session-bound
  token → 302; a subprocess boot with the env var unset proves CSRF **defaults
  ON**.
- `TestRateLimiting`: asserts every limited route carries the limiter decorator
  (login/register/forgot/reset and `api_save_admin_settings` imported from
  web_app; the route-module views — `/api/upload`, `/api/profile/update`,
  `/api/series/<id>/delete`, `/api/wishlist/<id>/moderate` and the shared
  surface/engagement endpoints (posts, comments, replies, reviews, likes,
  votes, follows, shelves, lists, clubs, wishlist suggest/vote/comment, AI
  chat) — asserted via `app.view_functions`), plus standalone probes proving
  429 after a breach, that `deduct_when` never counts successes or benign
  requests (login, password change, admin-password verify, profile email
  change), that plain shared-surface limits breach 429, and that GET fetches on
  the GET+POST comments routes never consume the POST-only budget — including
  the auth form routes (`register`/`forgot-password`/`reset-password`),
  locked by `test_auth_form_get_page_loads_never_consume_budget`,
  `test_auth_form_post_budget_breaches_429`, and
  `test_auth_form_decorators_scope_to_post`. Per-account  keying is covered by probes that exhaust User A's budget and prove User B on
  the **same IP** gets a fresh one, plus a scoping test asserting `_user_key()`
  yields `user:<id>` distinct per account.
- `TestRedisLimiterStorage`: the app limiter's `_storage_uri` resolves to
  `Config.REDIS_URL` (Redis, not `memory://`), the `RATELIMIT_STORAGE_URI`
  override to `memory://` works, and two live probes against a reachable
  Redis prove the two properties in-memory storage can't provide — a budget
  burned through limiter instance A is seen exhausted by instance B on the
  same Redis (multi-worker sharing), and a brand-new limiter inherits the old
  budget (restart persistence). Both skip cleanly when Redis is unreachable.
- `scripts/smoke_live.py`: boots a real HTTP server with CSRF + rate limiting
  **ON** (production defaults) and drives 19 journeys over real sockets — page
  loads never 429, valid register/login/password-change succeed, and the
  per-IP / per-user failure throttles fire 429 only on abuse.

## Known follow-up

`docker-compose.yml` still sets the legacy `ENABLE_CSRF: "1"` env var — now
inert since web_app reads `WTF_CSRF_ENABLED`. Harmless; remove on the next
infrastructure pass.
