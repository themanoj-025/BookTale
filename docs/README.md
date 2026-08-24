# Book-Tale — Documentation Index

Single home for all Book-Tale documentation. Book-Tale is a library management
system (Flask + SQLAlchemy + Alembic + RQ) with library, social, reading
challenge, and recommendation features.

**Start here:** [architecture.md](architecture.md) (system map) →
[folder_structure.md](folder_structure.md) (repo tree) →
[technical/TechSpec.md](technical/TechSpec.md) (build details).

## Structure

```
docs/
├── README.md                      ← this index
├── architecture.md                system architecture
├── folder_structure.md            repository + docs tree
├── design/
│   ├── AppFlow.md                 app screens / states / flows
│   └── Design.md                  design decisions
├── product/
│   └── PRD.md                     product requirements
├── project/
│   ├── analysis_report.md         repo inventory & classification
│   ├── ImplementationPlan.md      implementation plan
│   ├── RiskRegister.md            risks & mitigations
│   ├── Rules.md                   engineering rules
│   └── Tracker.md                 status tracker
├── reference/
│   ├── Glossary.md                terminology
│   ├── module_dependency.md       dependency graph
│   ├── package_overview.md        module inventory
│   ├── perf-report.md             performance report
│   ├── postmortem-privilege-escalation.md  incident postmortem
│   └── startup_flow.md            boot + runtime flows
├── technical/
│   ├── API.md                     endpoint reference
│   ├── Deployment.md              deployment guide
│   ├── Schema.md                  data model
│   ├── SecurityAndCompliance.md   security baseline
│   ├── TechSpec.md                technical spec
│   └── Testing.md                 test strategy
├── community/
│   ├── CHANGELOG.md               changelog
│   ├── CODE_OF_CONDUCT.md         code of conduct
│   ├── CONTRIBUTING.md            contribution guide
│   ├── SECURITY.md                security policy
│   └── SUPPORT.md                 support channels
├── decisions/
│   ├── 0001-fail-fast-secret-key-validation.md
│   ├── 0002-registration-role-whitelist.md
│   ├── 0003-template-migration-percent-format-to-jinja.md
│   ├── 0004-db-backed-storage-adapter.md
│   ├── 0005-jinja-migration-xss-hardening.md
│   ├── 0006-structured-logging-rotation.md
│   ├── 0007-csrf-default-on-rate-limited-auth.md
│   ├── 0008-health-endpoints-security-headers.md
│   ├── 0009-multi-stage-dockerfile-compose-stack.md
│   └── 0010-background-jobs-rq.md
├── assets/
│   └── runbooks/
│       ├── deploy.md              deploy runbook
│       ├── incident-response.md   incident response runbook
│       ├── restore-from-backup.md restore runbook
│       ├── rollback.md            rollback runbook
│       └── rotate-secret-key.md   secret rotation runbook
├── migration/
│   ├── migration_summary.md       modernization record
│   ├── old_tree_to_new_tree.md    restructure before/after
│   └── file_move_ledger.md        file-move ledger
└── audit/
    ├── cleanup-audit-2026-08-13.md  previous cleanup audit
    └── cleanup-audit-2026-08-15.md  docs de-LLM-ification audit
```

## Guidance

| You want... | Read |
|---|---|
| How the system works end-to-end | [architecture.md](architecture.md) |
| Where everything lives | [folder_structure.md](folder_structure.md) |
| Architecture decisions | [decisions/0001-fail-fast-secret-key-validation.md](decisions/0001-fail-fast-secret-key-validation.md) |
| Runbooks (deploy/rollback/restore) | [assets/runbooks/deploy.md](assets/runbooks/deploy.md) |
| API surface | [technical/API.md](technical/API.md) |
| Deployment | [technical/Deployment.md](technical/Deployment.md) |
| What's shipped / next | [project/Tracker.md](project/Tracker.md) |
| Risks & follow-ups | [project/RiskRegister.md](project/RiskRegister.md) |
