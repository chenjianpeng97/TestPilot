---
name: explore-sut
version: 1.3.0
group: internal
description: Explore-first session against a live SUT through the configured browser channel (config CHANNELS.browser - Playwright MCP by default, or the Cursor browser). Produces sanitized artifacts/evidence/<run_id>/ plus knowledge/wiki/explore capability notes. Use when learning a web SUT, mapping pages/buttons, or gathering evidence before any .feature exists. Do NOT use when the user already has a feature to implement — use run-feature-playwright-mcp instead.
---

# Explore SUT (browser channel)

## Scope

- **Primary goal**: walk a live web SUT, record what exists (pages, controls, APIs), persist evidence.
- **Write scope**: `artifacts/evidence/<run_id>/` (required); `knowledge/wiki/explore/<app>/*.md` (capability notes).
- **Must follow**: `docs/spec/sut-self-learning.md`, `docs/spec/browser-channel.md`, `docs/spec/bdd-run-gherkin-in-playwrightMCP.md`.
- **Out of scope**: freezing API/page objects (hand off to `freeze-api-objects` / `maintain-page-objects`); writing `.feature` (hand off to `feature-authoring`).

## Safety (live SUT)

- Prefer **read / create-on-throwaway-data**. Do not delete production-looking records without an explicit user OK.
- Do not submit payments, change other users' permissions, or hit admin destructive actions.
- Stop on captcha / SSO / OTP and report the blocker.
- Never persist secrets (same sanitizer as `run-feature-playwright-mcp`).

## Steps

1. Read `INDEX.project.md` and `knowledge/wiki/index.md`. Run `uv run tuner-config show --json`: note `ui_base_url`,
   `api_base_url`, `active_env`, and `channels.browser` (the browser channel to drive).
   Load login from **`data/sut-accounts.local.yaml`** (the only account source). Copy
   `data/sut-accounts.example.yaml` when it is missing and **stop**. Never write the password into evidence,
   explore notes, inbox, or git.
2. Pick a **vertical slice** (e.g. workspace → project → issue), not a full-site crawl.
3. Navigate with the configured browser channel (tool mapping in `docs/spec/browser-channel.md`). After each meaningful
   action, dump network + snapshot. If that channel's MCP is not connected, stop and tell the user; do not silently switch.
4. Persist with **`tuner-evidence persist`** (do not leave captures only in chat):

```bash
uv run python -m tuner_testkit.apps.evidence persist \
  --run-id YYYYMMDDTHHMMSSZ-<slice> \
  --scenario explore:<intent> \
  --network captures.jsonl \
  --intent "short vertical-slice intent"
```

   Manual fallback (same files):
   - `artifacts/evidence/<run_id>/run_summary.md`
   - `artifacts/evidence/<run_id>/network.jsonl` (sanitized)
   - optional `actions.jsonl` / `snapshots/`
5. Write/update `knowledge/wiki/explore/<app>/<slice>.md` with front-matter
   (`domain/source/date/version/confidence/evidence`) listing:
   - pages visited (url pattern, title)
   - primary actions (button labels)
   - APIs observed (method + path only)
   - blockers / i18n / env notes
   - browser channel used
   Register the note in `knowledge/wiki/index.md` and append `tuner-workspace changelog append --area wiki --skill explore-sut --action explore --items <note>`.
6. Stop. Next: `tuner-evidence routes --run-id …` then freeze / derive-design / author feature.

## Output checklist

- `run_id` and evidence directory exist.
- Sanitizer applied statement in `run_summary.md`.
- Explore note cites `evidence`.
- Next-step: `tuner-evidence routes` then freeze / derive-design / author feature.
