---
name: analyze-mcp-network
version: 1.0.0
group: internal
description: Internal step (usually reached via sut-self-learning / freeze-api-objects). Turn a persisted artifacts/evidence/<run_id>/network.jsonl into a unique method+path route table (JSON) for freeze-api-objects. Prefer tuner-evidence routes (deterministic). Use after explore-sut or run-feature-playwright-mcp. Do not invent routes that are not in the JSONL.
---

# Analyze MCP network evidence

## Scope

- **Primary goal**: list freeze candidates from on-disk evidence.
- **Write scope**: none (read-only). Optionally paste the JSON into the freeze handoff.
- **Must follow**: `docs/spec/bdd-run-gherkin-in-playwrightMCP.md` sanitizer — if the JSONL still contains Cookie/Authorization, stop and re-run `tuner-evidence persist`.

## Steps

1. Confirm `artifacts/evidence/<run_id>/network.jsonl` exists.
2. Run (stdout is JSON):

```bash
uv run python -m tuner_testkit.apps.evidence routes --run-id <run_id>
```

3. Hand the `routes[]` list to `freeze-api-objects`. Skip static/HTML. Skip `POST /api/sign-in/` (password body) unless the user explicitly wants a login API asset **without** persisting credentials.
4. For slug paths that `normalize_path` left as literals (e.g. `/api/workspaces/tuner/...`), freeze with `{workspace_slug}` and tell callers to `set_path`.

## Hard rules

- Do not re-fetch live traffic here.
- Do not write api_objects in this skill.
