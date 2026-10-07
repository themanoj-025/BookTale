# ✦ AI Assistance Disclosure

## Summary

Book-Tale was built with substantial AI assistance. The Flask API,
Streamlit dashboard, ML recommendation pipeline, and the scheduler were
drafted end-to-end by AI. Human maintainers then reviewed every design
decision, tightened the security posture, and wrote the tests and
documentation by hand.

## Tools & Models Used

| Tool | Provider / Model | Interface | Approx. dates used |
|---|---|---|---|
| **Claude / Opus** | Anthropic | CLI agent + web chat | 2025-11 → 2026-09 |
| **Cursor** | Anthropic (via IDE) | IDE agent | 2026-03 → 2026-09 |
| **GitHub Copilot** | GitHub | IDE completion | 2025-11 → 2026-09 |

## Scope — What AI Did vs. What Humans Did

- **AI:**
  - First draft of the Flask API endpoints and the web app routes
  - Scaffolding for the ML recommendation pipeline and the scheduler
  - Initial drafts of `README.md`, `CONTRIBUTING.md`, and the design docs
- **Human:**
  - All architecture decisions (API design, caching strategy, ML models)
  - Security review — secrets handling, SQL injection prevention, rate
    limiting
  - All production tests, CI workflows, and the Dockerfile
  - The open-source stewardship

## Estimated AI-Assisted Share

Roughly **60–75%** of lines in `app/`, `web_app.py`, and `ml_pkg/`
follow AI-generated boilerplate. The business logic, security controls,
and tests are mostly human-authored. This is an estimate, not a measured
statistic — the exact ratio was never instrumented.

## Human Review Process

- Every PR is reviewed line-by-line by the maintainer.
- Security review by maintainer: secrets handling, input validation,
  SQL injection prevention, and gitleaks/bandit findings.
- Automated gates: pre-commit (ruff + mypy), pytest (≥ 80% coverage
  floor), gitleaks, trivy, and an AI-disclosure metadata check.

## Known Limitations & Risks

- **LLM hallucination:** the recommendation engine can suggest an
  incorrect match. The ML pipeline is deterministic and validated
  against a held-out test set.
- **API-rate-limit drift:** the scheduler respects `Retry-After` headers.
- **License-contamination risk:** upstream training data may contain code
  copies. The CI gitleaks/bandit gates catch obvious secrets.

## How to Verify

- `git log --all --oneline --grep="assistant\|ai\|gen"` and the
  `Co-authored-by:` trailers in recent commits.
- `cat docs/audit/*` — per-repo audit reports.
- `git log --all --oneline --grep="ai-assisted\|LLM\|llm"` — the commit
  history trail.

## Last Updated

2026-10-06 · Maintained by `themanoj-025 <code.me.025@gmail.com>`
