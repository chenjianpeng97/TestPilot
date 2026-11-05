---
name: maintain-behave-steps
version: 1.0.0
group: internal
description: Internal step (usually reached via maintain-bdd-assets). Creates or updates behave step definitions under tests/features/ui_steps and tests/features/api_steps following behave-step-definitions.md. Use when implementing steps for a feature, deduplicating step phrases, or fixing step failures without leaking implementation details. Do NOT use when the user explicitly requests pytest instead of behave steps.
---

# Maintain behave Steps (UI/API layered)

## Scope

- **Primary goal**: thin orchestration layer that calls page/api objects and packages helpers.
- **Write scope**:
  - `tests/features/ui_steps/**`
  - `tests/features/api_steps/**`
- **Must follow**: `behave-step-definitions.md`.
- **Out of scope**: user-explicit **pytest** requests — do not create behave steps to “wrap” pytest; implement pytest tests instead.

## Hard rules

- UI steps:
  - must call `packages/page_objects/` methods only
  - must not contain selectors/css/xpath
  - must not sleep; wait happens in page objects
- API steps:
  - must not craft requests directly (no url/headers/token/body assembly)
  - must call `packages/api_objects/` APIModel via `model.execute()` (optionally with `set_*` / `override_*`)
  - for **form-encoded** POSTs, the APIModel sets `body_format="form"`; steps still use **`set_json({...})`** — never manual `urlencode`.
  - for **file / Excel** responses: after `execute()`, read **`resp.content`** (bytes) and pass to **`tuner_testkit.excel`** (`ExcelWorkbook.from_bytes`, `first_sheet_rows`, `rows_as_records`, …). Map sheet columns to domain models in a **project helper under `packages/`** used by the step — **not** inside `packages/api_objects/`.
- Context governance:
  - use namespaces: `context.vars`, `context.api`, `context.pages`
  - do not pollute `context` top-level with many random keys
  - do not log/persist sensitive values

## Step organization

- Keep separation by keyword files (required):
  - UI: `tests/features/ui_steps/given.py`, `tests/features/ui_steps/when.py`, `tests/features/ui_steps/then.py`
  - API: `tests/features/api_steps/given.py`, `tests/features/api_steps/when.py`, `tests/features/api_steps/then.py`
- **Do not** create per-domain step modules (forbidden examples):
  - `auth_api_then.py`, `order_when.py`, `user_profile_given.py`
  - Rationale: reuse is governed by step phrases and thin orchestration functions, not by multiplying files.

- Stage compatibility (must hold):
  - behave `--stage ui` loads steps from `tests/features/ui_steps/*.py` (top-level only)
  - behave `--stage api` loads steps from `tests/features/api_steps/*.py` (top-level only)
  - Therefore, if steps are organized under subpackages, you must provide a **top-level loader** (e.g. `tests/features/ui_steps/steps.py`) that imports the submodules. Prefer consolidating into the required `given.py/when.py/then.py` layout.

- Prefer one stable sentence pattern per intent; avoid synonym duplication.
- Before adding a new step phrase, search existing steps and reuse if possible.

## Output checklist

- Step sentences match feature wording exactly (or propose feature rewrite to reuse existing steps).
- Then steps focus on one core assertion; complex asserts split.
- Verification commands included:
  - `behave --stage ui <feature>` for UI features
  - `behave --stage api <api-feature>` for API features (or `--dry-run` with documented TODOs if not yet authored)
