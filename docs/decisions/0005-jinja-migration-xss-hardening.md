# ADR-0005: Jinja Migration, Client-Side XSS Hardening, and the Frontend Build

- **Status:** Accepted (2026-08-01)
- **Deciders:** Project owner, acting senior staff engineer
- **Related ADRs:** ADR-0003 (template migration plan — this ADR records the
  pattern actually used and the security hardening it enabled)

---

## Context

Phase 3 of the rebuild targets three overlapping problems the audit found:

1. **Pages were Python strings.** ~30 page-building blocks across
   `page_routes.py`, `social_routes.py`, `new_features_routes.py`, and
   `web_app.py` constructed HTML as Python f-strings / `'''` templates with
   `.replace("TOKEN", html)` substitution, then passed them to
   `render_template('base.html', content=CONTENT)` where `{{ content|safe }}`
   rendered them. Every page manually escaped with an `h()` helper, so one
   missed call was an XSS hole, and the pages were unmaintainable.
2. **Client-side innerHTML sinks.** Search pickers (diary, reading-progress,
   favorites) and the base.html sidebar widgets fetched `/api/books` /
   `/api/analytics/*` and interpolated raw values (`b.title`, `b.author`,
   `b.book_title`, `b.note`, usernames) into `innerHTML` and inline `onclick`
   attributes.
3. **The frontend build existed but was incomplete.** `scripts/build_frontend.mjs`
   (esbuild) already minified + content-hashed every file into
   `static/dist/manifest.json` consumed by the `asset()` Jinja helper — but
   three bundles (`animations.js`, `api.js`, `toast.js`) were never wired into
   `base.html`, so the pipeline produced assets no page loaded.

Also verified as already-done (audit claims were stale): the landing page is a
real Jinja template (`site_pages.py` → `landing.html`), avatar colors use a
stable `zlib.crc32` hash, and auth pages are real templates.

## Decision

### 1. Real Jinja2 templates for converted pages

Converted `books_page` and `notifications_page` from string-built CONTENT to
real templates:

- `templates/books.html` and `templates/notifications.html` extend `base.html`
  and override `{% block content %}` — autoescape is ON by default, so every
  user-controlled field renders escaped with zero per-call `h()` usage.
- Routes pass structured context (`books`, `categories`, `q`, `cat_filter`,
  `groups`, `by_type`, `notif_icons`, `time_ago`, …) instead of pre-built HTML.
- Reusable components live in `templates/macros.html`; this phase added
  `notification_item` and used the existing `book_card`, `empty_state`,
  `stat_card`, `user_avatar` macros.

The remaining ~28 string-built pages are tracked as a mechanical follow-up
(the pattern is proven; each is a copy-page + pass-context conversion).

### 2. Client-side XSS hardening

- `static/js/utils.js` gained `jsStr()` — a JS-string-inside-HTML-attribute
  escaper (backslash → single-quote → double-quote-as-`&quot;`, in that order),
  exported on `window.booktaleUtils` alongside the existing `escapeHtml()`.
- Every innerHTML sink now routes display text through
  `booktaleUtils.escapeHtml(...)` and inline-`onclick` argument values through
  `booktaleUtils.jsStr(...)`:
  - `new_features_routes.py`: reading-progress picker, bookmarks list, diary
    picker + "Selected:" echo.
  - `social_routes.py`: favorites book search.
  - `templates/base.html`: trending-sidebar labels/values, who-to-follow
    usernames.
- The previously-flagged suggestion-moderation `onclick` (new_features_routes)
  was already using the server-side `_js_str` escaper; verified, no change.

### 3. Frontend build completion

- `base.html` now loads all 15 built bundles via `asset()` (animations, api,
  toast added). `toast.js` loads **before** `utils.js` because both define
  `window.showToast`; loading the queue-based toast first lets `utils.js`'s
  version — the one existing inline handlers were written against — win.
- CDN deps are pinned to exact versions (bootstrap@5.3.2, chart.js@4.4.1,
  bootstrap-icons@1.11.2); no `@latest` anywhere.
- `npm run build` regenerates `static/dist/manifest.json` (verified: utils.js
  hash changed when jsStr was added), `asset()` falls back to `/static/<path>`
  when the build hasn't run (dev/tests never 404).

### 4. XSS regression tests

`tests/security/test_web_security.py` gained `TestXssServerSide` (payloads
round-trip escaped through the /books template; search value attribute-escaped;
converted notifications template renders 200) and `TestXssClientSideSinks`
(served client code for diary/progress/bookmarks/base-sidebar calls the escape
guards). Tests were merged into the existing file rather than a new module
because a standalone module that mutated `Config.DATA_DIR` while `web_app` was
already cached corrupted the shared test sandbox (`no such table: users`) —
a concrete lesson recorded here: **test modules that redirect Config paths must
own the single `web_app` import**.

## Consequences

### Positive

- Converted pages are autoescaped by construction — the `h()`-call
  vulnerability class is gone on those pages, and the pattern is mechanical to
  extend to the rest.
- Client-side sinks are hardened with a shared, documented escaper; the XSS
  regression suite pins the guards so a future edit that drops one fails CI
  without needing a browser.
- Every built asset is actually served; the esbuild pipeline is complete and
  reproducible (`npm run build`).

### Negative / Trade-offs

- Only 2 of ~30 string pages are converted; the rest remain string-built
  (escaped via `h()`) and are a tracked backlog. Full conversion is a
  mechanical but large diff — deliberately split into reviewable increments.
- The XSS tests assert the escape guards appear in served HTML (static guard
  pins), not live browser behavior — true DOM-level verification belongs to the
  Phase 8 Playwright suite.
- `toast.js` loading before `utils.js` is order-sensitive; documented in a
  comment at the include site.

## Alternatives considered

- **Convert all ~30 pages in one phase** — rejected: an unverifiable
  multi-thousand-line diff with high regression risk; the phase plan's own rule
  is small reviewable increments ending in green CI.
- **Server-side escape everything, ignore client sinks** — rejected: the API
  must return raw text (the client owns rendering), so client-side escaping is
  the correct layer; server-side only was the original vulnerable design.
- **Bundling JS into one file** — rejected by the existing build script's
  design: classic scripts share global scope via load order, and bundling would
  break globals like `showToast` referenced by inline handlers.

## Tests

`tests/security/test_web_security.py::TestXssServerSide` (4 tests) and
`TestXssClientSideSinks` (4 tests) — payloads render escaped server-side and
the served client code calls `escapeHtml`/`jsStr` at every sink. Full suite:
117 passed. Smoke: 37/37 journeys on the relational layer. pyflakes: clean.
