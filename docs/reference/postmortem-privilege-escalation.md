# Postmortem: Self-Service Admin Registration (Privilege Escalation)

**Severity:** Critical (P0) · **Component:** `POST /register` · **Status:** Closed, regression-tested

## Summary

Any visitor could register an account as an **admin** (or **librarian**) by
posting a `role` field to the public registration endpoint. The server
accepted the client-supplied value with no whitelist, so a single POST was
enough to obtain a fully privileged session.

## Timeline

| Time | Event |
| ------ | ------- |
| Audit | `POST /register` reads `request.form.get("role", "user")` and passes it straight to `lib.register_user(...)` |
| Audit | Confirmed: no server-side validation of `role` anywhere in the registration path |
| Fix | Registration now only ever accepts `"user"`; any other value (admin, librarian, `""`, crafted payloads) is silently downgraded (CWE-269) |
| Fix | Added `tests/security/test_web_security.py::TestPrivilegeEscalation` — posts `role=admin` / `role=librarian` and asserts the created account is `role == "user"` |
| Fix | Fail-fast boot: a default/empty `SECRET_KEY` now refuses to boot (`validate_secure_config`), closing the session-forgery route that could mint `role=admin` cookies on an unconfigured deploy |

## Root Cause

The endpoint treated `role` as an ordinary form field with no
authorization context. Self-service surfaces must never accept privilege
fields — they belong to admin-only flows backed by an authenticated,
authorized admin session.

## Impact

- **Account takeover:** a self-registered admin could read/modify any user,
  issue/return books at will, change library settings, and export data.
- **Reputation:** a single curl command demonstrated full compromise of a
  system that presented itself as security-conscious.

## Detection Gap

No automated test exercised the registration endpoint with a forged `role`
value. The web-layer security suite (added in Phase 1) now owns this case
permanently.

## Remediation

1. **Whitelist:** `role` is accepted but coerced: `if role not in ("user",): role = "user"` (in `web_app.register_page`).
2. **Regression tests:** three tests assert `role=admin`, `role=librarian`, and duplicate-ID handling all result in a `user` account.
3. **Fail-fast secrets:** booting with a known-default/empty `SECRET_KEY` raises `RuntimeError` (tested by `TestBootSecurity`), so cookie-forgery via a misconfigured deploy is impossible.
4. **Authorization matrix:** `admin_required` / `login_required` decorators gate every elevated route; the audit log (`audit_logs` table) records who changed what admin setting and from where.

## Follow-ups

- Elevate-role operations (librarian/admin creation) should move to an
  explicit admin UI action with audit-log entries (currently admin creation
  is bootstrap-only).
- Consider a periodic scan for accounts whose `role` column was modified
  outside the app's own code paths.
