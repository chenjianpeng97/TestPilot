
# TestPilot（tuner-testkit）平台路线图（A → B → C → D）

> 平台路线图。变更请在末尾追加变更说明。`dogfood/` 已于 7.1 移除，A0 / A7 / B0 中的 dogfood 验收已由平台仓单元测试与 scaffold 冒烟取代。
## 1. 愿景

测试工程师本地维护一个自己的 workspace repo（六层：assets / packages / apps / data / tests / docs，
加 `artifacts/` 交付物），用任意 AI IDE / CLI 打开即可工作；轻量用户用一个本地工作台页面调用
团队沉淀的工具；企业平台再从 repo 拉取元数据与交付物。

## 2. 四个阶段

| 阶段 | 目标 | 状态（2026-09） |
| --- | --- | --- |
| A 本地 workspace | 骨架 + DNA + kit 运行库足以支撑 QA 日常；catalog / index / artifacts 确定性化 | 平台层成熟；确定性化进行中 |
| B 本地工作台 workbench | 低代码成员 `git pull` 后在本地页面找到工具、填参运行、看产物 | 未开始（地基：argparse→JSON Schema、catalog 扫描） |
| C 企业信息平台 | 上传「谁创建了什么」：元数据规范、身份来源、报告 skill、publish sink | 阶段 0：先做规范铺垫 |
| D 云端拉取 workspace | 云服务拉取 workspace，agent 在其中协同创建 | 延后；原 Plane Job 协议即其雏形，5.0.0 退场 |

## 3. A 阶段任务

- A0（已取消）：曾用 `dogfood/` 作内置 workspace 示范，7.1 移除。
- A1 tool manifest：`@tool` 装饰 import-safe 的 `build_parser`（`apps/<name>/tool.py`），argparse → `params_schema` + `argv_plan`。
- A2 workspace catalog：`tuner-workspace catalog` → `artifacts/catalogs/workspace.json`（tools / action words / objects / knowledge / tests / docs / artifacts / git）。
- A3 INDEX 自动区：`tuner-workspace index render|check`，`<!-- auto:begin/end -->` 围栏。
- A4 artifacts 规范：`docs/spec/artifacts-layout.md` + run `manifest.json`。
- A5 工程卫生：CI（ruff / pytest / index 与 manifest check / scaffold 冒烟）、pre-commit secret-scan、scaffold `.gitignore`、logging hooks 接线。
- A6 多 IDE：`tuner-dna sync --target`，先覆盖 skills + `AGENTS.md`。
- A7 「QA 一天」验收：五条日常路径（已取消 dogfood，以平台单元测试和 scaffold 冒烟代替）。

## 4. B 阶段任务

- B0 工作台以 `tuner_testkit/workbench/tests` 验收。
- B1 `tuner-workbench`：一条命令刷新 catalog、起服（127.0.0.1）、开浏览器；工具目录 / 表单 / 运行 / 日志 / 运行历史 / 知识浏览 / 环境切换。
- B2 工具输出契约：`--json` envelope + run manifest。
- B3 skill / rule：`create-app` 默认生成 `tool.py`；`create-action-word` 要求参数 `description`；「工作台可见」约束。
- B4 轻量用户入口：scaffold 生成 `workbench.cmd` / `workbench.sh`；README「三步」。

## 5. C 阶段（阶段 0）

- C0 `docs/spec/metadata-conventions.md`：apps README / action word / testreport / inbox / run manifest 的统一 front-matter（含 `author`）。
- C1 `tuner-workspace meta stamp`：读 `git config user.email` 写 front-matter；catalog 用 `git log` 兜底校验。
- C2 `generate-test-report` skill：固定落点 `assets/testreport/<sut>/<yyyy-mm>/<slug>.md` + 固定章节。
- C3（畅想）`tuner-publish --sink`、`artifacts/exports/` 暂存区、MCP server 入口。

## 5.1 TestPilot 7.0（对照 `testpilot框架设计.excalidraw` 的收口）

心智模型：测试工程师 → TestPilot（rules / hooks 约束层 + 三组 skill）→ WorkSpace（知识层、资产层、工具、数据、测试、配置）→ 四条通道 → 被测系统。

| 主题 | 7.0 落地 | 后续 |
| --- | --- | --- |
| 知识与资产分离 | 顶层 `knowledge/`（ddl / raw / wiki / requirements / defects）；`assets/` 只留测试资产；`migrate knowledge` | wiki lint 的自动化程度、需求覆盖率进报告 |
| 可用性 | `health-check`（`tuner-workspace doctor`）、`upgrade-framework`（`.tuner-dna.json` + `--prune`）、`maintain-config` | doctor 进 CI 的 strict 门槛 |
| 配置 | `OPS / PORTS / CHANNELS / KNOWLEDGE`；`show --json`、`validate` | 环境间差异对比 |
| 端口与自定义 apps | `log-source`；`@tool(port=)` | 只在取数方式各团队不同时加端口（如 Rancher 操作） |
| 缺陷库 | 像用例一样：`knowledge/defects/<DEF-ID>.md` 固定模板、`tuner_testkit.defects` 校验、`maintain-defectlib` | 缺陷趋势进报告 |
| 浏览器通道 | `CHANNELS.browser`：Playwright MCP / Cursor 浏览器 | Cursor 浏览器的网络证据补全 |
| 追溯 | 对象级 changelog + version bump，pre-commit 校验；inbox 只给 agents | changelog 进工作台 |
| 收敛 | 对外 13 个入口 skill（知识 3 / 动作 6 / 可用性 4），其余 `internal` | 按使用数据继续合并 |
| DNA 两份视图 | 平台专属路径与 `platform-only` 块不下发 | — |

## 6. 版本节奏

- 先行（不发版）：A0。
- 5.0.0：Plane Job 协议退场 + A1 + A2（一次破坏性发行；下游删 `packages/*/plane.py`、去 `@plane_*`）。
- 5.x：A3–A7。5.y：B（新增 `[workbench]` extra）。C0–C2 与 B 并行。

## 变更说明

- 1.0.0（2026-09-22）：首版，来自评估复盘。
- 1.1.0（2026-11-04）：加 5.1 节 TestPilot 7.0：知识层、可用性、配置、端口、浏览器通道、追溯、收敛；产品名统一为 TestPilot。


- 1.2.0（2026-11-04）：从 dogfood 迁入根 ROADMAP.md；dogfood 目录移除。
