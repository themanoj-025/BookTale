# ADR 0002 — Server-side role whitelist on self-service registration

- **Status:** Accepted
- **Date:** 2026-08-01
- **Deciders:** Security audit findings; P0 remediation
- **Related code:** `web_app.py` (`register_page`, ~lines 277–361)

## Context

`POST /register` accepted a client-supplied `role` field with **no server-side
whitelist**. The registration form rendered role radio buttons (including
"Librarian"), and the handler passed the submitted role straight into
`lib.register_user(...)`. Because the web app is the only gate, any anonymous
attacker could register as `admin` or `librarian` by submitting
`role=admin` in the form body — a direct privilege escalation.

This was classified as **P0 — critical**: it grants admin (book management,
user blocking, settings, fine control, moderation) to anyone with HTTP access
to the register endpoint. The impact compounds the session-forgery risk from
[ADR 0001](0001-fail-fast-secret-key-validation.md) — together they made an
attacker's `role` claim trivially obtainable **and** forgeable.

## Decision

- The server ignores any role other than the single self-service role:
  ```python
  role = request.form.get("role", "user")
  if role not in ("user",):
      role = "user"
  ```
  (`web_app.py:332–337`) — a **deny-by-default whitelist**: anything that is
  not exactly `"user"` is silently downgraded to `"user"`.
- The rendered form was reduced to a single non-editable role value (the
  librarian/admin radio was removed), so the UI no longer invites the attempt.
- Privileged roles (`admin`, `librarian`) remain **server-originated only**:
  created via seed/bootstrap or by an existing admin action — never via a
  public form field.

## Consequences

### Positive

- Anonymous registration can only ever yield a `user` account. Privilege
  escalation through the register endpoint is closed.
- The whitelist is robust to field removal, tampering, and future form changes:
  the server is the source of truth for role, not the client.

### Negative

- None functional. (Minor: a malicious client could still *send* `role=admin`;
  the server ignores it, so there is no residual risk.)

### Regression coverage

- `tests/security/test_web_security.py::TestPrivilegeEscalation` POSTs
  `role=admin` and `role=librarian` at `/register` and asserts the stored role
  is `"user"` — this test fails against the pre-fix code.

## Alternatives considered

- **Validate and reject** (`400` on any role != "user"). Rejected: silently
  downgrading is friendlier and avoids leaking which roles exist; a strict
  rejection also risks breaking legitimate clients that echo a stale hidden
  field.
- **Role claim from the session only.** Already the case for authorization
  checks; this ADR only concerns how the role gets into the store at
  registration time.
