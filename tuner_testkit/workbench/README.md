# tuner-workbench

本机工作台：首页是只读看板（测试资产、自动化覆盖、工具、工作台自检、被测系统配置），
另有目录切片（`apps/*/tool.py` 的 `@tool` + 类别目录上的 kit `@register`，
含子目录如 `db_seed/audit/*.py`）渲染成表单，按 `argv_plan` 或
`tuner-action-words run` 执行，产物落 `artifacts/runs/<run_id>/`。
列表/搜索不扫 `assets/`、不跑 `git log`。`db_seed` 有特化页（example / dry_run / cleanup）。

## 需求背景

团队里测开用 A 阶段骨架写好 `apps/` / `db_seed` 并 push；低代码成员 `git pull` 后
需要一个页面填参运行，而不是记 CLI。打开工作台时还要一眼看到这个仓管了多少资产、
自动化覆盖到哪、配置齐不齐。

## 试用场景

- 适用：本机看看板、浏览工具目录、填表单、看运行日志、AI 组件（rule / skill / agent / hook）。
- 不适用：对外网暴露、当企业平台、替代理写业务工具。
- 前置：在 workspace 根（或 `--root`）运行；依赖 `tuner-testkit[workbench]`（含 fastapi / uvicorn / jinja2）。

## 看板只读统计结果

看板的数字由 `tuner-dashboard refresh`（skill `refresh-dashboard`，见 `tuner_testkit/apps/dashboard/README.md`）离线算好，
工作台请求里不扫文件：

- 读本机 `artifacts/catalogs/dashboard.json`，按文件 mtime 缓存，文件不变就不重复解析。
- 本机没有 JSON 时退回入库的 `DASHBOARD.md` 计数，并提示「本机尚未统计」。
- 每页标出「统计于 X（N 分钟前）」；页面上没有刷新按钮，要新数字就让 AI 执行 `refresh-dashboard`。
- 路由：`/`（概览）、`/dashboard/assets|automation|tools|doctor|config`、`GET /api/dashboard`。

## 运行方式

```bash
uv run tuner-workbench
uv run tuner-workbench --no-browser --port 8765
```

只绑定 `127.0.0.1`。非编码成员：`git pull` → `uv sync` → `uv run tuner-workbench`（或仓库里的 `workbench.cmd` / `workbench.sh`）。

## 运行示例

```bash
uv run --directory <workspace> tuner-dashboard refresh
uv run --directory <workspace> tuner-workbench --no-browser
```

打开 `http://127.0.0.1:8765/` 应能看到看板与左侧编号导航；
`http://127.0.0.1:8765/tools` 应能看到该 workspace 的工具；
`http://127.0.0.1:8765/words/db_seed` 应能看到 `db_seed.sample_seed`；
`http://127.0.0.1:8765/ai` 应能看到 rule / skill / agent / hook（与 `.cursor/REGISTRY.md` 同源）。
