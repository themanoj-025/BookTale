# SecurityAndCompliance — Book-Tale: Threat Model & Security

| Field | Value |
| --- | --- |
| Version | v0.1 |
| Last Updated | 2026-08-06 |
| Owner | Security Engineer |
| Status | In Review |

---

## 1. Threat Model (STRIDE)

| Threat | Surface | Impact | Mitigation |
| --- | --- | --- | --- |
| Spoofing | Session forgery | Account takeover | Signed cookies, HttpOnly, SameSite=Lax, Secure |
| Tampering | CSRF on state changes | Forged transfers/actions | Flask-WTF CSRF on all state-changing endpoints |
| Repudiation | Admin settings changes | No accountability | Append-only audit trail (IP, old→new, redacted secrets) |
| Info disclosure | XSS, file upload | Data/credential leak | Autoescape, CSP, magic-byte re-encode uploads |
| DoS | Auth brute force | Account lockout/flood | Rate limiting (per-IP + per-account `deduct_when`) |
| Elevation | Privilege escalation | Admin access | Registration role whitelist; escalation tests |

## 2. Auth / Authorization Model

- Session-based auth with signed cookies; bcrypt password hashing (≥12 chars policy).
- RBAC: `user` / `librarian` / `admin`; self-registration hard-capped at `user`.
- DB-backed one-time tokens for verify (24h) and reset (15m); single-use, purge job.
- Account-scoped rate keys prevent distributed bypass.

## 3. Data Classification

| Data | Class | Handling |
| --- | --- | --- |
| Passwords | Credential | bcrypt, never logged |
| Email | PII | Truncated in logs |
| Loan/reading history | Personal | Access-controlled |
| Audit trail | Compliance | Append-only, secrets redacted |
| Book catalog | Public | Publicly readable |

## 4. Encryption Standards

- In transit: TLS (prod), Secure cookies.
- At rest: passwords bcrypt; reset/verify tokens hashed DB-backed.
- Uploads re-encoded server-side (payloads stripped).

## 5. Compliance Checklist

- [ ] CSRF on all state-changing endpoints (tests)
- [ ] Rate limits present + `deduct_when` behavior tested
- [ ] Upload magic-byte validation tested
- [ ] Default-secret boot refused (fail-fast) + tested
- [ ] Privilege escalation regression tests
- [ ] Password policy ≥12 enforced on all surfaces
- [ ] GDPR: user data export/delete (roadmap)

## 6. Incident Response Plan (outline)

1. Detect: monitoring + audit log review.
2. Triage: classify (auth, data, availability).
3. Contain: revoke sessions / rotate secrets.
4. Remediate: patch + regression tests.
5. Recover: re-deploy, verify.
6. Postmortem: blameless writeup (see docs/postmortem-*.md).

## 7. Related Documents

| Document | Relationship |
| --- | --- |
| [Rules.md](../project/Rules.md) | Security baseline |
| [API.md](API.md) | Rate limits + auth endpoints |
| [Schema.md](Schema.md) | Sensitive data map |
| [TechSpec.md](TechSpec.md) | Security NFRs |
| [PRD.md](../product/PRD.md) | Security goals |
| [AppFlow.md](../design/AppFlow.md) | Flows |
| [Design.md](../design/Design.md) | Safe rendering |
| [ImplementationPlan.md](../project/ImplementationPlan.md) | TASK-3.4 |
| [Tracker.md](../project/Tracker.md) | Status |
| [Testing.md](Testing.md) | Security suite (90 tests) |
| [Deployment.md](Deployment.md) | Secret mgmt |
| [Glossary.md](../reference/Glossary.md) | Vocabulary |
| [RiskRegister.md](../project/RiskRegister.md) | Risks |
