# tuner-testkit 7.0.0 — TestPilot：知识层、配置、端口、可用性

MAJOR：被测系统知识从 `assets/` 移到顶层 `knowledge/`；对外 skill 收敛成三组入口；配置扩展出运维通道、端口绑定、执行通道、知识位置；
后端日志等差异化能力改为「kit 定端口契约、workspace 写自定义 app」。产品名统一为 **TestPilot**（PyPI 发行名 `tuner-testkit`、导入名 `tuner_testkit`、`tuner-*` 命令都不变）。

## 本版变更

### 分层与知识层

- 新顶层 `knowledge/`：`ddl/`（自动区）、`raw/`（原件只读）、`wiki/`（`index.md`、`log.md`、`domain-notes/`、`usecases/`、`explore/`、`design/`）、
  `requirements/<REQ-ID>.md`、`defects/<DEF-ID>.md`。规范 `docs/spec/knowledge-syntax.md`，规则 `knowledge.mdc`。
- `assets/` 只留随测试工作演进的 Markdown 资产：`sql/`、`testdesign/`、`testcases/`、`testsheet/`、`testreport/`（画像移到 `assets/testreport/profiles/<sut>.md`）。
  Assets 这个概念 = `assets/` + `packages/`（Python 资产不迁移）。
- `tuner-dump-ddl` 默认写 `knowledge/ddl/<别名>/`，流水写 `knowledge/ddl/CHANGELOG.md`（未迁移的仓仍回落 `assets/ddl`）。
- 提交规范新增 scope `knowledge`；`knowledge/**` 的改动必须声明它。
- 用例 front-matter 新增 `requirements: [REQ-…]`、`data: [data/<path>, account:<id>]`，`python -m tuner_testkit.testcases` 校验；`assets/testcases/` 根目录允许 `CHANGELOG.md`。

### 追溯：对象级 changelog

- `artifacts/inbox/` 仍是本机流水、不入库，且只有 `.cursor/agents/*` 编排必须写。skill 维护的库改为：单元 bump `version` + 库根 changelog 一行。
- `tuner-workspace changelog append|check`；`tools/git-hooks/pre-commit` 在密钥扫描后跑 `changelog check --staged`（`TUNER_SKIP_CHANGELOG_CHECK=1` 单次绕过）。
- `maintain-testcases` 1.7.0 不再写「以 git 为准，不要另写变更日志」：git 提交正文照写，另写 `assets/testcases/CHANGELOG.md`。

### 配置

- `config` 分五类：被测系统环境、`OPS`（运维通道，按环境）、`PORTS`（端口绑定）、`CHANNELS`（执行通道，`browser = playwright-mcp | cursor-browser`）、`KNOWLEDGE`（`api_docs`、`source_roots`、`wiki`）。
  规范 `docs/spec/config-syntax.md`，schema `tuner_testkit/config_schema.py`。
- `tuner-config show --json`（密钥打码）、`tuner-config validate`（schema、占位、入库文件里的密钥、`env_local.py` 是否被跟踪、端口绑定与契约）。
- `env_local.py` 顶层的 `CHANNELS` / `PORTS` / `KNOWLEDGE` 对本机所有环境生效。stub `config/env.py` 改为调用 kit 的 `apply_module`，以后新增配置段不用再改下游文件。
- scaffold 带 `config/env_local.py.example`；`data/sut-accounts.example.yaml` 账号加 `role`、`permissions`（`docs/spec/data-syntax.md`）。

### 端口与自定义 apps

- `tuner_testkit.ports`：`log-source`。契约 `docs/spec/ports.md`。端口只用于取数方式各团队不同的能力。
- `@tool(..., port="log-source")`；catalog 行带 `port`；`INDEX.project.md` 新增 `ports` 自动区。
- `tuner-task answer` 回答 `sut-log-source` 后返回 `next`（`create-app` 写适配器、`maintain-config` 绑定）。参考实现在平台仓 `dogfood/apps/sample_log_source/`。

### 浏览器通道与第二条接口通道

- 前端操作按 `CHANNELS.browser` 选择 Playwright MCP 或 Cursor 浏览器；`docs/spec/browser-channel.md` 写明两个通道的工具对照与证据落盘。
- `tuner-openapi-import`：从 OpenAPI 3 / Swagger 2 冻结 `packages/api_objects`（与录制同一冻结内核，同路由合并）。

### 可用性

- `tuner-workspace doctor`：体检 JSON（布局、配置、账号、浏览器通道、端口、DDL 是否过期、源码根、API 文档、wiki、需求追溯、DNA、git hooks）。
- `tuner-workspace migrate knowledge [--apply]`：旧布局迁移。
- `tuner-dna sync` 写 `.tuner-dna.json`（每个文件的哈希）：没被本地改过的文件自动更新；`--prune` 删除上游已移除且没改过的文件；
  本地改过的保留（`--overwrite` 才覆盖）；`*.local.*`、`AGENTS.local.md` 永不触碰。`tuner-dna check --json` 区分 missing / outdated / edited / removed_upstream。
- DNA 分平台与 workspace 两份视图：`release-template`、`FRAMEWORK.md` 不下发；`AGENTS.md` 等文件里的平台段落下发时剔除。`docs/changelog/TEMPLATE-*.md` 随 DNA 下发。

### skill（对外 13 个入口，其余 `group: internal`）

- 知识：`maintain-wiki`（新）、`dump-ddl`、`maintain-defectlib`（新）
- 动作：`maintain-testcases`、`maintain-testsheet`、`execute-testsheet`（新）、`generate-test-report`（报告统一入口）、`maintain-bdd-assets`（新，BDD 统一入口）、`maintain-pytest`（新）
- 可用性：`health-check`（新，`init-content` 并入）、`upgrade-framework`（新）、`maintain-config`（新）、`create-app`（端口适配器模板）
- 删除：`init-content`。新增规则：`knowledge.mdc`、`config.mdc`、`defects.mdc`。

### 缺陷库

- 缺陷和用例一样记录：`knowledge/defects/<DEF-ID>.md`，一个缺陷一个文件，固定 front-matter 与章节（`docs/spec/defect-syntax.md`）。
- `python -m tuner_testkit.defects new …` 按模板建文件、`next-id` 取编号、`check` 校验（字段取值、章节顺序、历史表、指向的测试单 / 用例 / 需求是否存在）。
- skill `maintain-defectlib` 2.0.0：从测试单缺陷表或测试人的描述记录缺陷，跨轮次只更新原文件；`tuner-workspace doctor` 报 `knowledge.defects`。

## 下游怎么升级

推荐直接让 AI 跑 skill `upgrade-framework`。手工步骤：

1. 工作区先提交干净。`uv tool upgrade tuner-testkit`；`uv add "tuner-testkit[<原 extras>]==7.0.0"`；`uv sync`。
2. 第一次带记录的同步（旧仓没有 `.tuner-dna.json`，改过的 DNA 文件会被保留）：`uv run tuner-dna sync --prune`，
   看输出的 `kept_local`；把本仓定制移到 `.cursor/rules/<名字>.local.mdc` 或 `AGENTS.local.md` 后，`uv run tuner-dna sync --prune --overwrite`。
   旧的 `.cursor/skills/init-content/`、`.cursor/skills/release-template/` 若没被改过会被删除；改过的手工删除。
3. 迁移布局：`uv run tuner-workspace migrate knowledge` 看计划，确认后 `--apply`。它移动 `assets/{ddl,domain-notes,usecases,explore,design}`，
   把画像移到 `assets/testreport/profiles/`，改写仓内引用，给 `INDEX.project.md` 补 `knowledge` 与 `ports` 围栏。
   之后 `uv run tuner-workspace index render`。
4. 配置：对照新的 stub（`tuner-init scaffold <临时目录> --no-ai` 生成一份）给 `config/env.py` **补** `OPS`、`CHANNELS`、`PORTS`、`KNOWLEDGE` 四段，
   并把 `_apply_module` 改为调用 `tuner_testkit.config.apply_module`；已有值不动。`env_local.py` 里旧的 `LOG_SOURCE` 搬到对应环境的 `OPS`，
   `data/source-roots.local.yaml` 的路径搬到 `env_local.py` 顶层 `KNOWLEDGE["source_roots"]`。然后 `uv run tuner-config validate`。
5. 旧的 `knowledge/wiki/domain-notes/<sut>/log-source.md` 只保留「通道是什么、为什么」，地址与密钥留在 config。已有私有取日志工具：
   在 `apps/<name>/tool.py` 加 `port="log-source"`，按 `docs/spec/ports.md` 补参数，再在 `PORTS` 绑定。
6. 提交里改到 `knowledge/` 的要用 `knowledge` scope；启用 hooks 后维护区改动需要 changelog 行。
7. `uv run tuner-workspace doctor` 收尾，按 `health-check` 处理剩余缺口。一次提交，例：
   `chore(knowledge,assets,rules,skills,agents,docs,hooks): upgrade TestPilot to tuner-testkit 7.0.0`。
