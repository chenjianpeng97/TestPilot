---
name: reuse-analysis
version: 1.0.0
group: internal
description: Internal step (usually reached via maintain-bdd-assets). Analyzes whether to reuse/add/update Feature steps, Page Objects, and API Objects by searching for existing assets, matching by intent/fingerprint, and minimizing duplication. Use before creating new behave steps/page/api objects. Do NOT force a behave reuse plan when the user explicitly requests pytest.
---

# Reuse Analysis (avoid asset duplication)

## Scope

- **Primary goal**: decide reuse vs new vs version upgrade across layers.
- **Read scope**:
  - `tests/features/**/*.feature`
  - `tests/features/ui_steps/**`, `tests/features/api_steps/**`
  - `packages/page_objects/**`
  - `packages/api_objects/**`
- **Out of scope as a forcing function**: if the user **explicitly** chose **pytest**, do not require Feature/step reuse plans or `behave --stage` compatibility; still search `packages/**` for helpers worth reusing from pytest.

## Decisions to make (required)

- **Steps**:
  - Is there an existing step phrase with same intent?
  - If similar but not identical, can we refactor feature wording to reuse?
- **Page objects**:
  - Is this a new page/component, or an extension of an existing object?
  - Can we add a stable locator strategy without changing step sentences?
- **API objects**:
  - Match by `method + normalized_path` and fingerprint intent.
  - Update v1 only when backward compatible; otherwise recommend v2.

## Output format (required)

- **Reuse**:
  - list of exact files/symbols to reuse and how
- **Update**:
  - minimal, compatible updates and target files
- **Create**:
  - new assets to create with suggested paths/names
- **Risks**:
  - flakiness/security risks and mitigation (e.g. request `data-testid`, sanitize captures)

## Pipeline alignment checks (required)

- **MCP prerequisite**:
  - Confirm whether a browser-channel Run/Capture (Playwright MCP by default) exists for the target scenario(s).
  - If not, the reuse plan must state: **“block on capture”** and list what can/cannot be decided without it.

- **Stage compatibility** (behave path only):
  - Any **behave** steps plan must remain compatible with `behave --stage ui/api` discovery.
  - Prefer the repository-required layout: `given.py/when.py/then.py` per layer (UI/API).
  - Skip this check for user-explicit pytest implementations.
