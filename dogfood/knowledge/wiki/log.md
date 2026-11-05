# wiki log — 维护流水

> Append-only，一次 `maintain-wiki`（ingest / lint）一行，用 `tuner-workspace changelog append --area wiki` 追加。
> 格式：`- <iso-ts> | <skill> | <action> | items=<页面> | key=value ...`
- 2026-11-04T17:56:20+0800 | maintain-wiki | 迁移 | items=domain-notes/platform/roadmap.md,usecases/platform/qa-daily-journeys.md,usecases/workbench/lightweight-user.md | reason=migrate knowledge: assets/ -> knowledge/wiki/ | author=chenjianpeng@innovamed.com.cn
- 2026-11-04T17:56:20+0800 | maintain-wiki | 更新 | items=domain-notes/platform/roadmap.md | version=1.0.0->1.1.0 | reason=TestPilot 7.0 收口 | author=chenjianpeng@innovamed.com.cn
