# 🧪 Smoke Test Checklist — Book-Tale

This checklist covers the ~30 core user journeys. It is re-run after **every** phase
of the rebuild. Any failure = regression = stop and fix before proceeding.

**How to run:** boot the app (`python web_app.py` or `python start.py --web`), log in
with a fresh browser session, and walk through each journey. Record the result in the
Status column (`✅` / `❌` + note). Automated equivalents live in `tests/`.

Legend: `L` = logged-out, `U` = regular user, `A` = admin, `Lb` = librarian.

---

## A. Auth & Accounts

| #   | Journey                                                            | Role | Status |
| --- | ------------------------------------------------------------------ | ---- | ------ |
| 1   | Landing page loads with hero, stats, and CTA buttons               | L    |        |
| 2   | Register a new MEM-XXXX account (role selector shows Reader only)  | L    |        |
| 3   | POST /register with `role=admin` is silently downgraded to `user`  | L    |        |
| 4   | Login with valid credentials redirects to feed                     | U    |        |
| 5   | Login with wrong password shows error (no crash, no stack trace)   | U    |        |
| 6   | Logout clears session and returns to login                         | U    |        |
| 7   | Forgot-password flow returns anti-enumeration success page         | U    |        |
| 8   | Reset-password with a valid token changes the password             | U    |        |
| 9   | Boot refuses to start with default/insecure SECRET_KEY             | A    |        |
| 10  | Admin settings override (FINE_PER_DAY etc.) persists after restart | A    |        |

## B. Library Core

| #   | Journey                                                         | Role | Status |
| --- | --------------------------------------------------------------- | ---- | ------ |
| 11  | Browse /books (grid + list views render, no 500)                | U    |        |
| 12  | Search books by title/author; category filter works             | U    |        |
| 13  | Book detail page renders cover, availability, borrow button     | U    |        |
| 14  | Issue a book (available) → success + transaction recorded       | Lb   |        |
| 15  | Issue the last copy → clean "unavailable" + reservation offered | Lb   |        |
| 16  | Exceed borrow limit → clean rejection                           | Lb   |        |
| 17  | Return a book → copy availability restored                      | Lb   |        |
| 18  | Overdue list shows late books with correct days/fines           | A    |        |
| 19  | Admin can add/edit/soft-delete a book                           | A    |        |
| 20  | Admin user management (filter by role/status, no 500)           | A    |        |

## C. Social & Community

| #   | Journey                                                                      | Role | Status |
| --- | ---------------------------------------------------------------------------- | ---- | ------ |
| 21  | Feed loads posts; create a post with text                                    | U    |        |
| 22  | Like a post (count updates, realtime event in 2nd tab)                       | U    |        |
| 23  | Comment on a post                                                            | U    |        |
| 24  | Follow a user; following tab shows their posts                               | U    |        |
| 25  | Profile page renders (avatar, favorites grid, heatmap, badges)               | U    |        |
| 26  | Profile page of a user **with favorites** renders (regression: line 151 fix) | U    |        |
| 27  | Write a review with rating on a book                                         | U    |        |
| 28  | Join/set a reading challenge goal; leaderboard renders                       | U    |        |
| 29  | Diary entry + reading calendar page renders (no 500)                         | U    |        |
| 30  | Reading analytics page renders charts (no 500)                               | U    |        |
| 31  | Wishlist: suggest a book, vote, comment; admin moderates                     | U/A  |        |
| 32  | Reading progress: update page, add bookmark, finish book                     | U    |        |

## D. Admin / Settings / Content

| #   | Journey                                                         | Role | Status |
| --- | --------------------------------------------------------------- | ---- | ------ |
| 33  | Settings page: update profile, toggles, theme, font size        | U    |        |
| 34  | Upload avatar (valid image) works; renamed HTML-as-PNG rejected | U    |        |
| 35  | Admin reports page renders all metric sections                  | A    |        |
| 36  | Admin settings page saves an override that survives restart     | A    |        |
| 37  | Series: create, detail, add books                               | A    |        |
| 38  | Communities: join/create community                              | U    |        |
| 39  | Notifications: unread badge, mark-as-read                       | U    |        |
| 40  | Keyboard-only pass: all clickable divs reachable (Phase 3 gate) | U    |        |

## E. Stability & Security (spot checks)

| #   | Journey                                                                  | Role | Status |
| --- | ------------------------------------------------------------------------ | ---- | ------ |
| 41  | App survives server restart; data persists (JSON files)                  | A    |        |
| 42  | Two concurrent users can issue books without double-issue (Phase 2 gate) | Lb   |        |
| 43  | POST without CSRF token rejected (Phase 4 gate)                          | U    |        |
| 44  | /healthz and /readyz respond (Phase 7 gate)                              | L    |        |

---

## Current Baseline (Phase 3)

**Date:** 2026-08-01
**Commit:** (after Phase 3 Jinja + XSS hardening commit)

**Automated suite:** `python -m pytest tests/ -q` → **117 passed** (110 pre-existing +
7 Phase 3 tests: 6 XSS regression tests in `tests/security/test_web_security.py`
plus the converted-template render test).

**Phase 3 (Jinja + XSS + build):**

- Books and notifications pages converted to real Jinja2 templates
  (`templates/books.html`, `templates/notifications.html`) extending `base.html`
  with macros (`book_card`, `empty_state`, `notification_item`). Autoescape ON.
- All client-side innerHTML sinks hardened: diary/reading-progress pickers,
  bookmarks list, favorites search, base.html trending sidebar + who-to-follow
  now route display text through `booktaleUtils.escapeHtml` and inline-`onclick`
  args through `booktaleUtils.jsStr` (new helper in `static/js/utils.js`).
- Frontend build completed: all 15 bundles loaded via `asset()` (animations,
  api, toast added), `npm run build` verified regenerating the manifest.
- ADR-0005 records the migration pattern + the test-isolation lesson.

Remaining string-built pages (~28 CONTENT blocks) are a tracked mechanical
follow-up; the two converted pages prove the pattern end-to-end.

**Automated smoke run:** `python scripts/smoke_checklist.py` → **37/37 journeys pass**
against the relational (SQLAlchemy/SQLite) backend. The runner walks the journeys
below marked with `(auto)` and asserts real behavior (login redirects, seeded books
render, issue → reservation → return round-trips, fine accrual, overdue report,
social posts/comments/follows, challenge/diary/wishlist/progress flows, admin
reports/settings, notification badge, restart persistence, and a 20-thread race for
the last copy yielding exactly one winner).

Journey status key for the tables above:

- `✅ (auto)` — covered by `scripts/smoke_checklist.py` and passing
- `✅ (test)` — covered by a unit/route test in `tests/`
- `⛔ manual` — requires a real browser session (not yet automated)
- `⏭️ Phase N gate` — intentionally deferred to a later phase's gate

| #   | Status          | How                                                |
| --- | --------------- | -------------------------------------------------- |
| 1   | ⛔ manual       | landing page render                                |
| 2   | ✅ (test)       | role whitelist regression test                     |
| 3   | ✅ (test)       | privilege-escalation test (`tests/security/`)      |
| 4   | ✅ (auto)       | login → feed redirect                              |
| 5   | ✅ (auto)       | wrong-password rejection message                   |
| 6   | ✅ (auto)       | logout clears session                              |
| 7   | ✅ (test)       | anti-enumeration page                              |
| 8   | ⛔ manual       | reset-token flow                                   |
| 9   | ✅ (test)       | fail-fast SECRET_KEY test                          |
| 10  | ⛔ manual       | admin settings restart persistence                 |
| 11  | ✅ (auto)       | /books renders after login                         |
| 12  | ✅ (auto)       | search + category filter                           |
| 13  | ✅ (auto)       | book detail renders                                |
| 14  | ✅ (auto)       | issue → txn recorded                               |
| 15  | ✅ (auto)       | last-copy reservation offered                      |
| 16  | ✅ (auto)       | borrow-limit rejection                             |
| 17  | ✅ (auto)       | return restores availability + fine                |
| 18  | ✅ (auto)       | overdue list correctness                           |
| 19  | ✅ (test)       | add/edit/soft-delete (soft-delete round-trip test) |
| 20  | ⛔ manual       | admin user management UI                           |
| 21  | ✅ (auto)       | feed post create                                   |
| 22  | ✅ (auto)       | like post                                          |
| 23  | ✅ (auto)       | comment on post                                    |
| 24  | ✅ (auto)       | follow / unfollow                                  |
| 25  | ⛔ manual       | profile render (favorites/heatmap/badges)          |
| 26  | ⛔ manual       | profile-with-favorites regression                  |
| 27  | ✅ (auto)       | review with rating                                 |
| 28  | ✅ (auto)       | challenge goal + set_goal                          |
| 29  | ✅ (auto)       | diary entry + calendar data                        |
| 30  | ✅ (auto)       | reading analytics data path                        |
| 31  | ✅ (auto)       | wishlist suggest → admin moderation data           |
| 32  | ✅ (auto)       | reading progress update + bookmark                 |
| 33  | ⛔ manual       | settings page (theme/font toggles)                 |
| 34  | ⛔ manual       | avatar upload (Phase 4 gate for magic-byte check)  |
| 35  | ✅ (auto)       | admin reports render data                          |
| 36  | ⛔ manual       | admin settings override persistence                |
| 37  | ✅ (auto)       | series create/detail/add                           |
| 38  | ✅ (auto)       | community join/create                              |
| 39  | ✅ (auto)       | notification unread badge                          |
| 40  | ⏭️ Phase 3 gate | keyboard-only accessibility pass                   |
| 41  | ✅ (auto)       | restart persistence (fresh storage reads same DB)  |
| 42  | ✅ (auto)       | 20-thread race → 1 winner (no oversell)            |
| 43  | ⏭️ Phase 4 gate | CSRF rejection                                     |
| 44  | ⏭️ Phase 7 gate | /healthz + /readyz                                 |

**Not yet automated (manual browser walks):** #1, #8, #10, #20, #25, #26, #33, #34, #36.
**Deferred by phase gate:** #40 (Phase 3), #43 (Phase 4), #44 (Phase 7).
