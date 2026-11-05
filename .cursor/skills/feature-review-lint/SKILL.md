---
name: feature-review-lint
version: 1.0.0
group: internal
description: Internal step (usually reached via maintain-bdd-assets). Reviews and lints behave .feature files against behave-gerkin-syntax.md with actionable rewrite suggestions. Use when a feature is flaky/too long/too imperative, or before implementing steps. Do NOT use when the user explicitly requests pytest instead of behave/Gherkin.
---

# Feature Review / Lint

## Scope

- **Read/Review scope**: `tests/features/**/*.feature`
- **Primary goal**: ensure features are automation-ready and stable for AI + humans.
- **Must follow**: `behave-gerkin-syntax.md`.

## Review checklist

- **Automation readiness**
  - No “差不多就行/接口正常” type unverifiable statements.
  - No fixed sleeps; only condition-based outcomes.
- **Given/When/Then semantics**
  - Given = state, When = action, Then = assertion (no actions).
- **Step count & cohesion**
  - 5–12 steps preferred; if >12, propose split or abstraction.
- **Parameterization**
  - Prefer DataTable / Outline where it reduces duplication.
- **Tag governance**
  - Add `@flaky` only with reason; `@skip` only with explicit reason.
- **Boundary enforcement**
  - No selectors, API urls/headers/tokens, SQL.

## Output format (required)

Return findings grouped as:

- **Must fix**: items that violate hard rules or break automation.
- **Should improve**: maintainability issues (length, naming, reuse).
- **Suggested rewrite**: provide a rewritten snippet for the highest-impact part.
