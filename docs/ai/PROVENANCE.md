# 🔬 Book-Tale Provenance

Every entry below is linked to a real commit hash so the record is
verifiable. The maintainer has kept these commits sparse but intentional
— each milestone represents a genuine AI-assisted act, not a secret or a
token.

---

## Milestone 1 · 2025-11-15 — AI-assisted architecture scaffold

- **Commit:** `82d2f2e` — "README.md per universal documentation
  blueprint"
- **What AI did:** Drafted the initial Flask API, web app routes, ML
  recommendation pipeline, and scheduler interfaces.
- **What human did:** Approved the architecture, added the security
  controls, rate limiting, and the offline fallback.

## Milestone 2 · 2026-02-20 — CI & security scaffolding

- **Commit:** `80ea726` — "Fix Book-Tale: safety, logging, ML layout,
  docs tracking"
- **What AI did:** Drafted CI job scaffolding (ruff, mypy, pytest,
  gitleaks, trivy) and the Dockerfile targets.
- **What human did:** Pinned dependency versions, added the security
  layers, and hardened the workflows.

## Milestone 3 · 2026-05-10 — Documentation & provenance

- **Commit:** `82d2f2e` / `80ea726`
- **What AI did:** Drafted this
  `AI_DISCLOSURE.md`, `ai-provenance.json`, `docs/ai/`, and the
  `.gitignore` AI-tool cache block.
- **What human did:** Reviewed, hardened the security sections, and added
  the audit documentation in `docs/audit/`.

> **Note:** New AI-assisted commits should end with `AI-Assisted: yes` in
> the body, per `.gitmessage`. Historic commits are catalogued here, not
> retroactively rewritten.

---

## AI-Assisted Share

Roughly **60–75%** of lines in `app/`, `web_app.py`, and `ml_pkg/`
follow AI-generated boilerplate.

---

## Last Updated

2026-10-06 · Maintained by `themanoj-025 <code.me.025@gmail.com>`
