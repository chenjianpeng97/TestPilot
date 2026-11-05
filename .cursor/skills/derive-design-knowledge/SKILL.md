---
name: derive-design-knowledge
version: 0.2.0
group: internal
description: Internal step (usually reached via sut-self-learning). Compile knowledge/wiki/design/<app>/<route-slug>.md from open evidence channels (MCP network, DDL, SUT source, optional logs). Schema is docs/spec/design-knowledge-syntax.md v0.1 (draft). Use after an explore session or API freeze when DB effects must ground assertions. Do not invent tables that are not in DDL or source.
---

# Derive design knowledge

## Scope

- **Primary goal**: one route → one `knowledge/wiki/design/<app>/<route-slug>.md`.
- **Write scope**: `knowledge/wiki/design/**` only.
- **Must follow**: `docs/spec/design-knowledge-syntax.md` (v0.1 draft — record schema gaps in `## notes`).
- **Evidence is open**: MCP `network.jsonl`, `knowledge/ddl/**`, SUT source trees the user pointed at, log dumps from `apps/*`. Do not require all channels.

## Steps

1. Collect inputs: `run_id`, frozen `api_object_ref` if any, page trigger if known, DDL dir, optional source path.
2. For each captured **non-static mutating** route (POST/PUT/PATCH/DELETE):
   - Draft front-matter (`confidence`: `observed` only if DB/log proved it; else `inferred`).
   - Fill `writes` / `noise` / `reads` from the **highest quality channel available**:
   1. source (models/views/serializers) — see `.cursor/agents/sut-source-to-design.md`
   2. SQL logs / DB diff
   3. inference from response body + DDL names
   - If source names a table that is not in `knowledge/ddl`, dump it (`tuner-dump-ddl`) before writing `writes`.
   - Skip `operation_log` / `*_activities` / audit tables as `noise` unless the user says they are the assertion target.
3. Every `writes` row must cite evidence or a source path in `## notes`.
4. If the v0.1 schema cannot express something (multi-API button, external side effects), write it under `## notes` and do **not** invent new top-level keys yet — the draft must be stress-tested first.

## Hard rules

- Ground table/column names in `knowledge/ddl` or source. No hallucinated identifiers.
- No secrets.
- Do not generate `db_assert` words here; only the knowledge file.

## Output checklist

- File path matches method+normalized_path slug.
- `api_object_ref` / `page_ref` filled when those assets exist.
- `noise` vs `writes` explicitly split.
- Schema gaps listed for later spec bump.
