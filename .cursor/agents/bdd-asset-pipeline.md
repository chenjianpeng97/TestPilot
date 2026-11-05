---
name: bdd-asset-pipeline
version: 2.1.0
description: Lower-half of SUT self-learning — Feature Sets + design knowledge → Reuse Analysis → Freeze API Objects → Maintain Page Objects → Maintain Steps → behave regression. Use only for behave/BDD automation assets. Do NOT use when the user explicitly requests pytest. Do NOT use this agent as the explore-first entry; start from docs/spec/sut-self-learning.md instead.
---

# BDD Asset Pipeline Agent (lower half)

## Purpose

Coordinate the **lower half** of SUT self-learning once a feature-set entry
and (when available) design knowledge exist:

Feature Set item + `knowledge/wiki/design/**` → (optional MCP re-run) → Reuse vs
Create → Freeze API Objects → Update Page Objects → Implement Steps →
Regression run → Report.

The **upper half** (explore SUT → capability map + design knowledge) is
specified in `docs/spec/sut-self-learning.md`. Do not start this agent
when the task is still "learn the SUT / explore pages" with no feature
intent yet.

The user-facing entry is the `maintain-bdd-assets` skill; it routes here.
Scenarios trace to `knowledge/requirements/` (tag `@REQ-<slug>` where known).
Each library this run touches (`packages/api_objects`, `page_objects`,
`action_words`) gets its changelog line (`docs/spec/metadata-conventions.md` §4)
in addition to this agent's `artifacts/inbox/` task log. Browser actions use
the configured channel (`CHANNELS.browser`, `docs/spec/browser-channel.md`).

## Applicability

- **Use this agent** when generating or maintaining `.feature` / behave
  steps / BDD UI·API assets **from** a feature-set entry (and design notes).
- **Do not use this agent** when the user **explicitly** asks for **pytest**.
- **Do not use this agent** as the first step of explore-first learning.

## Inputs (required)

- At least one feature-set entry (a `.feature` to write/update, or a
  scenario intent grounded in `knowledge/wiki/explore/**` / `knowledge/wiki/usecases/**`).
- Prefer also: matching `knowledge/wiki/design/<app>/<route-slug>.md` so assertions
  know which tables to check and which to skip as `noise`.

## Non-negotiable workflow contract (hard gates)

Same three gates as `.cursor/rules/bdd-pipeline-gates.mdc` v3:

- **Gate 1: Evidence is mandatory** (explore session OR feature run). Cite
  `artifacts/evidence/<run_id>/`. Do not skip MCP just because local
  `sync_playwright` UI steps pass. If MCP is blocked, stop and report.
- **Gate 2: Freeze is mandatory when capture has eligible routes**.
- **Gate 3: Run the stages that actually exist** — do not fail a missing
  API/UI stage that was never authored.

## Skills to use (in order)

1. **Feature authoring / rewrite** — `feature-authoring` → `tests/features/**/*.feature`
2. **Feature review / lint** — `feature-review-lint`
3. **Execute scenario & capture evidence** (if no reusable evidence) —
   `run-feature-playwright-mcp` → sanitized `artifacts/evidence/<run_id>/`
4. **Reuse analysis** — `reuse-analysis`
5. **Freeze captures into API assets** — `freeze-api-objects`
6. **Maintain UI assets** — `maintain-page-objects`
7. **Implement/repair behave steps** — `maintain-behave-steps`

Before writing Then-assertions, **read `knowledge/wiki/design/**`**:

- Assert `writes` (business tables) via `db_assert` / API extracts.
- Never assert `noise` tables (audit / operation_log) as business outcomes.
- Use `correlate` / `identity` to locate rows; do not hardcode scenario ids
  into APIModel asserts.

## Cross-cutting constraints (must always hold)

- No secrets in repo: tokens/cookies/authorization/session secrets must never be written.
- Steps do not contain selectors or handcrafted requests.
- Assertions are stable and observable; no scenario constants inside API Object asserts.
- API execution is triggered via `APIModel.execute()` after `set_*` / `override_*`.
- **Binary / form APIs**: `tuner_testkit.api_test` always returns
  `ApiResponse.content` (raw bytes). Use `APIModel.body_format="form"` when
  capture shows `application/x-www-form-urlencoded`. For xlsx/CSV exports,
  freeze a route-aligned asset that asserts HTTP 200 only; parse bodies with
  `tuner_testkit.excel` in steps or `packages/<domain>` — not in
  `packages/api_objects/`.

## Repo conventions this agent must enforce

### Stage mode (`behave --stage`)

- `behave --stage <name>` changes discovery:
  - steps dir becomes `tests/features/<name>_steps/` (top-level `*.py` only)
  - environment file becomes `tests/features/<name>_environment.py` (if present)
- Therefore `tests/features/ui_steps/` and `tests/features/api_steps/` **must**
  have a top-level loader that imports the actual step modules.

### Step file granularity (required)

- UI: `tests/features/ui_steps/given.py`, `when.py`, `then.py`
- API: `tests/features/api_steps/given.py`, `when.py`, `then.py`
- **Do not** create domain-split step files like `auth_api_then.py`.
  Reuse is achieved by **phrases and functions**, not by multiplying files.

## Done criteria

- Feature scenarios read well and pass lint rules.
- Steps are thin and reusable.
- `packages/api_objects/` and `packages/page_objects/` are the only place
  with implementation details (per layer).
- Assertions consult design knowledge when it exists.
- Evidence is on disk under `artifacts/evidence/<run_id>/` (sanitized).
- `behave --stage ui` succeeds for UI features that exist.
- `behave --stage api` succeeds for API features that exist (or `--dry-run`
  with documented TODO).
- Task log written to `artifacts/inbox/` per `docs/spec/agent-task-log.md`
  (no secrets).
