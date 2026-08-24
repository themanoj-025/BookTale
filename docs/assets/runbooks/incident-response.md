# Runbook: Incident Response

Severity guide: **SEV1** = data breach / privilege escalation / service down;
**SEV2** = partial outage / degraded security; **SEV3** = cosmetic / minor.

## Leaked credential (SEV1)

1. **Contain:** rotate `SECRET_KEY` (`rotate-secret-key.md`), rotate the
   affected account password, revoke its sessions (`session.clear()` / key
   rotation does this).
2. **Assess:** query the audit log for actions by the affected account;
   check recent transactions/notifications for abuse (fines wiped, books
   checked out, settings changed).
3. **Notify:** stakeholders + affected users (forced password change).
4. **Postmortem:** document timeline/root cause/detection gap (template in
   `docs/../../reference/postmortem-privilege-escalation.md`).

## Database down (SEV2)

- `/readyz` returns 503; the app continues serving static/read paths where
  possible.
- Check the DB host + connection pool; restore from backup only if data is
  corrupt (`restore-from-backup.md`), never as a first move.

## Redis down (SEV2)

- Rate-limit budgets degrade to in-process memory (fail-open with a logged
  warning); realtime falls back to the single-process path. No data loss.
- Restart Redis; budgets reset — tighten temporarily if under attack.

## Brute-force / spam wave (SEV2)

- Per-IP and per-account limits absorb most of it. Check the limiter logs for
  the offending IPs; block at the edge if sustained.
- Do **not** disable rate limiting to "fix" it.

## After any incident

- Re-run the full test suite and `scripts/smoke_checklist.py` before
  declaring restored.
- Write or update a postmortem; every incident should leave a regression test
  that would have caught it.
