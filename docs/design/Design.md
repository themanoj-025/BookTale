# Design — Book-Tale: Design System & UX Principles

| Field | Value |
| --- | --- |
| Version | v0.1 |
| Last Updated | 2026-08-06 |
| Owner | Design Lead |
| Status | In Review |

---

## 1. Design Principles

1. **Clarity over cleverness** — labels say exactly what they do.
2. **Calm density** — catalog pages are dense but scannable.
3. **Consistency** — shared tokens + macro library across all 26+ screens.
4. **Feedback everywhere** — loading skeletons, toasts, optimistic updates.
5. **Accessible by default** — WCAG AA, keyboard-first.

## 2. Brand & Visual Identity

- Voice: warm, literate, professional.
- Imagery: book covers as primary imagery; stable deterministic avatar colors (no per-process hash randomness).

## 3. Color System

| Token | Hex | Usage | Contrast (AA) |
| --- | --- | --- | --- |
| color-bg | `#FAF9F6` | Page background | — |
| color-surface | `#FFFFFF` | Cards, nav | — |
| color-primary | `#7C3AED` | CTAs, links | 5.6:1 on white |
| color-primary-hover | `#6D28D9` | Hover states | 6.8:1 |
| color-text | `#1F2937` | Body text | 12.6:1 |
| color-muted | `#6B7280` | Secondary text | 4.8:1 |
| color-success | `#15803D` | Success | 5.2:1 |
| color-danger | `#B91C1C` | Errors, fines | 7:1 |
| color-warning | `#B45309` | Overdue warnings | 5.4:1 |

## 4. Typography Scale

| Token | Font | Size | Weight | Line-height | Usage |
| --- | --- | --- | --- | --- | --- |
| display | serif | 32px | 700 | 1.2 | Page headers |
| heading | serif | 24px | 700 | 1.3 | Section headers |
| subheading | sans | 18px | 600 | 1.4 | Card titles |
| body | sans | 16px | 400 | 1.6 | Body text |
| caption | sans | 13px | 400 | 1.5 | Meta, dates |
| code | mono | 13px | 400 | 1.5 | Code blocks |

## 5. Spacing & Grid System

- Base unit: 4px (4/8/12/16/24/32 grid).
- Breakpoints: 640 / 768 / 1024 / 1280.

| Breakpoint | Layout |
| --- | --- |
| < 640 | Single column, hamburger nav |
| 640–1023 | 2-column cards |
| ≥ 1024 | Multi-column catalog grid + sidebar |

## 6. Component Library

**Button:**

```
┌────────────────┐
│  Issue Book     │ ← primary
└────────────────┘
default | hover (darken) | active (press) | disabled | loading (spinner)
variants: primary, secondary, danger, ghost
```

**Card (book):**

```
┌──────────────────────────────┐
│ [cover]  Title (bold)        │
│          Author · Year       │
│          Availability badge  │
│          [Reserve] [Review]  │
└──────────────────────────────┘
```

Other core components: input (with error/validation state), modal, toast, nav, data table (paginated), notification bell, badge (availability), progress bar (reading), skeleton loader.

## 7. Iconography & Imagery

- Icon set: consistent inline SVG library (bundled via esbuild).
- Imagery: user avatars (deterministic color), book covers (server-re-encoded uploads).

## 8. Accessibility Standards

- Target: WCAG 2.1 AA.
- Keyboard: full tab order, focus rings, skip-to-content.
- Screen readers: semantic HTML, aria-labels on icon-only buttons, live regions for toasts.
- Motion: `prefers-reduced-motion` honored.

## 9. Responsive Behavior

| Breakpoint | Rule |
| --- | --- |
| Mobile | Single column, bottom nav for member flows |
| Tablet | 2-column grids |
| Desktop | 3–4 column catalog, sticky sidebar |

## 10. Motion & Micro-interactions

- Duration tokens: 150ms (hover), 200ms (modals), 300ms (page transitions).
- Curves: ease-out standard.
- What animates: hover lifts on cards, toast slide-in, skeleton shimmer, notification bell pulse. Nothing animates for pure decoration.

## 11. Dark Mode / Theming

- Theme toggle in settings; token mapping table below.

| Token (light) | Token (dark) |
| --- | --- |
| color-bg | `#0F172A` |
| color-surface | `#1E293B` |
| color-text | `#F1F5F9` |
| color-primary | `#8B5CF6` |

## 12. Related Documents

| Document | Relationship |
| --- | --- |
| [AppFlow.md](AppFlow.md) | Screens consuming components (SCR-001…026) |
| [PRD.md](../product/PRD.md) | UX goals |
| [TechSpec.md](../technical/TechSpec.md) | Frontend build (esbuild) |
| [Schema.md](../technical/Schema.md) | Data for cards/tables |
| [ImplementationPlan.md](../project/ImplementationPlan.md) | Tasks |
| [Tracker.md](../project/Tracker.md) | Status |
| [Rules.md](../project/Rules.md) | Standards |
| [API.md](../technical/API.md) | Data contracts |
| [SecurityAndCompliance.md](../technical/SecurityAndCompliance.md) | Safe rendering |
| [Testing.md](../technical/Testing.md) | A11y tests |
| [Deployment.md](../technical/Deployment.md) | Asset pipeline |
| [Glossary.md](../reference/Glossary.md) | Vocabulary |
| [RiskRegister.md](../project/RiskRegister.md) | Risks |
