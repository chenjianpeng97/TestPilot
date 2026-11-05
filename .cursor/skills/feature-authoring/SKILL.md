---
name: feature-authoring
version: 1.0.0
group: internal
description: Internal step (usually reached via maintain-bdd-assets). Creates or rewrites behave Gherkin .feature files following behave-gerkin-syntax.md. Use when generating new BDD scenarios, converting testcases to .feature, or standardizing feature wording/tags/parameterization. Do NOT use when the user explicitly requests pytest instead of behave/Gherkin.
---

# Feature Authoring (behave / Gherkin)

## Scope

- **Primary goal**: produce maintainable `.feature` files that express business behavior, not implementation.
- **Write scope**: `tests/features/**/*.feature` only.
- **Must follow**: `behave-gerkin-syntax.md`.
- **Out of scope**: user-explicit **pytest** requests (performance, DB checks, etc.) — do not invent `.feature` files to satisfy those; implement pytest instead.

## Hard rules (do not violate)

- Feature content **must not** contain selectors/xpath/css, API urls/headers/tokens, SQL/table names.
- `Then` (and `And` under Then) **assertions only**; no actions/click/input/request.
- Avoid fixed waits like “等 5 秒”；express **condition-based** outcomes.
- Keep scenarios short: **5–12 steps** recommended; >12 steps must be split or abstracted.
- Prefer a small set of stable step sentence patterns; avoid synonyms explosion.

## Output checklist

- Tags are meaningful and minimal (`@smoke`, `@critical`, `@regression`, `@slow`, `@flaky`, `@skip`, optional `@env_*`).
- Background contains only stable preconditions.
- Parameters use one of:
  - quoted strings: `"..."`,
  - DataTable for structured input,
  - Scenario Outline for data-driven batches.
- Scenario titles are searchable and business-meaningful.

## Suggested structure template

```gherkin
@smoke
Feature: <业务能力>
  <why>

  Background:
    Given <稳定前置>

  Scenario: <可检索的业务结果>
    When <业务动作>
    Then <可观测结果>
```

## When updating existing features

- Prefer refactoring to **reuse existing step phrases** already present in repo.
- If a step phrase must change, keep semantic intent stable and minimize ripple effects.
