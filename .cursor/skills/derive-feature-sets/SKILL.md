---
name: derive-feature-sets
version: 1.0.0
group: internal
description: Internal step (usually reached via maintain-bdd-assets). Turn knowledge/wiki/explore capability notes (plus usecases/domain-notes) into behave Feature Sets under tests/features/. Use after explore-sut, before bdd-asset-pipeline. Do NOT use when the user explicitly requests pytest.
---

# Derive Feature Sets

## Scope

- **Primary goal**: write Gherkin that expresses the explored capability, not the click path.
- **Write scope**: `tests/features/**/*.feature` via `feature-authoring` rules.
- **Inputs**: `knowledge/wiki/explore/**`, optional `knowledge/wiki/usecases/**`, `knowledge/wiki/design/**` (so Then clauses stay honest).

## Steps

1. Read explore notes for the slice. List user-visible capabilities as candidate scenarios.
2. Follow `docs/spec/behave-gerkin-syntax.md` (no selectors/SQL/URLs in the feature).
3. Prefer one Feature per capability area; Rule groups around business rules if needed.
4. Keep scenarios 5–12 steps. Tag `@smoke` only for the thinnest happy path.
5. If design knowledge exists, Then steps should talk about **observable business results**, not audit tables.

## Hand off

After files exist, continue with `bdd-asset-pipeline` (lower half) to freeze objects and implement steps.
