---
name: sut-source-to-design
version: 1.1.0
description: Walk SUT backend source (Django models/views/serializers, or equivalent) plus knowledge/ddl to draft knowledge/wiki/design/<app>/<route-slug>.md. Use when the engineer points at a source tree. Do not invent tables. Complements derive-design-knowledge; this agent is the source-channel playbook.
---

# SUT source → design knowledge

## Purpose

Highest-quality `writes` / `noise` / `reads` often come from **models.save / views**, not from MCP bodies. Plane dogfood: `Issue.save` showed `issue_sequences` + `_ensure_default_state` before any DB diff existed.

## Inputs

- Source root: config `KNOWLEDGE.source_roots` (`uv run tuner-config show --json` → `knowledge.source_roots`, machine-local paths set by `maintain-config`); pre-7.0 workspaces may still have `data/source-roots.local.yaml`. Otherwise the path the user named this session — offer `maintain-config` to record it. Repo-relative roots and branches are explained in `knowledge/wiki/domain-notes/<sut>/source-roots.md` when that page exists.
- Matching `knowledge/ddl/<datasource>/` if present (dump missing tables rather than hallucinate)
- Optional `artifacts/evidence/<run_id>/` to fill `api_object_ref` / `page_ref`

## Workflow

1. Locate the route: urls.py / router → view/serializer.
2. Locate the model `.save()` / service function for that write.
3. List INSERT/UPDATE/DELETE tables. Audit / `*_activities` / operation_log → `noise`.
4. If a table is named in source but missing from DDL, run `tuner-dump-ddl <table> --datasource …` then continue. Do not skip the table.
5. Write one `knowledge/wiki/design/<app>/<route-slug>.md` per **route** (not per button) using `docs/spec/design-knowledge-syntax.md` v0.1.
6. Record schema gaps under `## notes` (conditional writes, defaulted FKs, dual identity). Do **not** invent new top-level keys yet.

## Hard rules

- Table/column names must appear in DDL or source. No guessed identifiers.
- `confidence: inferred` for source-only; `observed` only with DB/log evidence.
- No secrets.
- Do not generate action words here.
- Write `artifacts/inbox/<utc>-sut-source-to-design-<slice>.md` per
  `docs/spec/agent-task-log.md` (outputs = design files; no secrets).
