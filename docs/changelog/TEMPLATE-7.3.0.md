# tuner-testkit 7.3.0 — 工作台看板（离线统计 + 只读展示）

MINOR，向后兼容：下游无需迁移；升级后执行一次 `refresh-dashboard` 生成 `DASHBOARD.md`。

## 变化

- **离线统计 `tuner-dashboard`**：`refresh` 统计用例、测试单、缺陷、API / 页面对象、动作词与 db_seed、BDD、pytest、工具、doctor 自检与环境概览；写入库的 `DASHBOARD.md`（计数变了才重写，`updated` 是计数最后一次变化的时间）与本机 `artifacts/catalogs/dashboard.json`（gitignore，含全部明细）。`status` 只读已有结果。`--out-dir` 可把两份结果写到别处。工具与动作词用 AST 静态解析，不导入 workspace 的 `apps/` 或动作词。
- **skill `refresh-dashboard`**（可用性组，入口 skill 13 → 14）：手动触发统计；`DASHBOARD.md` 有变化时按 `chore(index): refresh dashboard counts` 提交；自检缺口交给 `health-check`。
- **工作台只读看板**：首页改为看板概览；新增 `/dashboard/assets|automation|tools|doctor|config` 与 `/api/dashboard`；左侧编号导航（看板 1–6、操作 7–12）。请求只读结果文件，按 mtime 缓存。启动时 `workspace.json` 改后台线程刷新；`/knowledge` 懒加载缓存，`?refresh=1` 重建。
- **环境配置白名单**：`config.describe_environments()` 只输出环境名、接口 / 前端地址，以及数据源别名、类型、host、端口、库名；密码、令牌、账号不读。敏感键名也不会出现在「其它配置段」里。
- **提交规范**：根目录 `DASHBOARD.md` 归 `index` scope；新仓 `INDEX.project.md` stub 登记该文件。

## 下游怎么用

`uv tool upgrade tuner-testkit` → `uv add "tuner-testkit[<原来的 extras>]==7.3.0"` → `uv sync` → `tuner-dna sync --prune` → 让 AI 执行 `refresh-dashboard`（或 `uv run tuner-dashboard refresh`）→ `uv run tuner-workbench`

## 需要迁移

不需要。旧工作台首页的「造数 / 工具」卡片改成了看板，原操作入口仍在左侧导航。
