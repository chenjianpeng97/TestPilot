# Framework changelog（公共组件变更记录）

本仓库是测试框架模板仓。从业务试验田验证通过后回灌的**公共框架能力**记录于此，
便于对照来源 commit 与同步路径。4.x 起运行库在 `tuner_testkit/`（PyPI `tuner-testkit`），
迁移见 [`TEMPLATE-4.0.0.md`](TEMPLATE-4.0.0.md)。

## 维护约定

- **何时写**：改动下列任一可回灌 / 已回灌路径时，同一提交必须追加条目：
  - `tuner_testkit/api_test/**`
  - `tuner_testkit/page_test/**`
  - `packages/page_objects/session.py`（凭据与回放接缝，非业务资产）
  - `tuner_testkit/db/**`
  - `packages/config.py`
  - `tuner_testkit/logging/**`
  - `tuner_testkit/excel/**`
  - `tuner_testkit/fake/**`
  - `tuner_testkit/apps/recorder/**`
  - `tuner_testkit/apps/api_recorder/**`
  - `tuner_testkit/apps/page_recorder/**`
  - `tuner_testkit/apps/dump_ddl.py`
  - `tuner_testkit/apps/_shared/**`
  - `tuner_testkit/tools/**`、`tuner_testkit/catalog/**`、`tuner_testkit/workspace/**`
  - `docs/spec/**`（框架规范）
  - `.cursor/skills/**` / `.cursor/rules/**`
  - 本文件 `docs/changelog/FRAMEWORK.md`
- **不写**：业务资产（具体 `packages/api_objects/<业务路由>/...`）、业务 `action_words`、业务 feature/场景。
- **commit**：提交产生后用 `git rev-parse HEAD`（或 short hash）回填；未提交前写 `TBD`。
- **来源**：条目可注明试验田来源 hash，便于追溯。

## 条目模板

```markdown
## YYYY-MM-DD — <short-title>

- **commit**: `<hash>`
- **来源**: `trial-repo@<hash>`（可选）
- **目的**: …
- **路径**:
  - `…`
- **不在同步范围**: …
- **验证**: …
```

---

## 2026-11-04 — tuner-testkit 7.0.0（TestPilot：知识层、配置、端口、可用性）

- **commit**: `TBD`
- **来源**: `testpilot框架设计.excalidraw` 心智模型与 6.3.0 实现的对照评价（vault `raw/projects/testpilot/`）
- **目的**: 让仓库同时约束 AI 的行为、承载测试工程师的全部工作信息：被测系统知识与测试资产分层；配置成为「在哪、用什么」的唯一来源；
  差异化能力（后端日志）只定端口契约、由 workspace 自定义 app 实现；缺陷像用例一样有固定目录、模板与校验；补齐体检、升级、配置三个可用性入口；
  对外 skill 收敛成知识 / 动作 / 可用性三组；下游拿到的 DNA 不再含平台专属内容。产品名统一为 TestPilot（发行名、导入名、命令不变）。
- **路径**:
  - `tuner_testkit/apps/dna/**`（`PLATFORM_ONLY_PATHS`、平台块剔除、`.tuner-dna.json`、`sync --prune`、`check --json`）
  - `tuner_testkit/config.py`、`tuner_testkit/config_schema.py`（`show --json`、`validate`、`OPS / PORTS / CHANNELS / KNOWLEDGE`）
  - `tuner_testkit/ports.py`、`tuner_testkit/tools/manifest.py`（`port` 字段）
  - `tuner_testkit/defects/**`（缺陷库 `check` / `new` / `next-id`）；`docs/spec/defect-syntax.md`；`.cursor/rules/defects.mdc`
  - `tuner_testkit/workspace/{changelog,doctor,migrate,index_render,cli}.py`、`tuner_testkit/catalog/scan.py`、`tuner_testkit/project.py`
  - `tuner_testkit/apps/openapi_import/**`（`tuner-openapi-import`）、`tuner_testkit/apps/dump_ddl.py`、`tuner_testkit/apps/testreport/cli.py`、`tuner_testkit/apps/task/**`
  - `tuner_testkit/apps/_shared/changelog.py`、`tuner_testkit/testcases/validate.py`、`tuner_testkit/apps/index_ai/registry.py`、`tuner_testkit/workbench/templates/ai.html`
  - `tuner_testkit/apps/init_repo/scaffold.py`、`stubs/**`（`knowledge/`、`config/env_local.py.example`、`INDEX.project.md` 0.2.0）
  - `tools/git-hooks/{pre-commit,pre-push,validate_commit_msg.py}`
  - `AGENTS.md` 2.0.0；`docs/spec/{knowledge-syntax,config-syntax,ports,data-syntax,browser-channel}.md`（新）及多份 spec 更新
  - `.cursor/rules/**`（新增 `knowledge`、`config`）、`.cursor/skills/**`（新增 8 个、删除 `init-content`、全部加 `group`）、`.cursor/agents/**`
  - `dogfood/**`（迁到 `knowledge/`、`apps/sample_log_source` 参考适配器、`PORTS` 绑定）
  - `pyproject.toml` `[tool.ruff]`（钉 0.17.3，规则 E4 / E7 / E9 / F / B / BLE）、`.github/workflows/ci.yml`；按规则修复既有代码：
    删除未用导入与无占位 f-string、`normalize.py` 里被覆盖的重复 `skip_api_flow`、`client.py` 未用变量；`zip(strict=True)`；
    `DbClient` 健康检查只捕获 `SQLAlchemyError`、`ApiResponse` 解析只捕获 `ValueError` / 解码错误；其余宽泛 except 补 `noqa: BLE001` 理由
- **不在同步范围**: 下游业务数据；下游需按 `TEMPLATE-7.0.0.md` 迁移布局与 `config/env.py`
- **验证**: `uv run pytest`；`uv run --directory dogfood pytest`；`uv run --directory dogfood behave --stage api --tags "@offline" --tags "~@wip"`；
  `tuner-index-ai --check`；`manifest --check`；临时目录 `tuner-init scaffold` → `tuner-dna check` → `tuner-workspace doctor`

## 2026-10-29 — tuner-testkit 6.3.0（测试单出 GJB438B 测试报告）

- **commit**: `5f13876`
- **来源**: `trial-repo@4d1b1a3` 的 `apps/testreport`、`generate-testsheet-report` 1.1.0、`maintain-testsheet` 1.1.0；在两份下游试验田各出过一份报告
- **目的**: 测试单填完后直接出 GJB438B 软件测试报告。数字从测试单算，不随轮次变化的信息放画像，报告 Markdown 入库审阅，docx 每次重渲染。
- **路径**:
  - `tuner_testkit/apps/testreport/**`（`tuner-testreport`，extra `[report]`）
  - `.cursor/skills/generate-testsheet-report/SKILL.md`
  - `.cursor/skills/maintain-testsheet/SKILL.md`
  - `tuner_testkit/apps/init_repo/scaffold.py`
  - `tools/git-hooks/secret_scan.py`、`tools/git-hooks/validate_commit_msg.py`
  - `AGENTS.md`、`INDEX.md`、`README.md`
- **同版发布**: `4d1dd24` 的 skill `init-content` 1.0.0、`sut-self-learning` 1.0.1、`sut-source-to-design` 1.0.2
- **不在同步范围**: 下游的画像 `assets/domain-notes/testreport/*.md`、报告 `assets/testreport/**`、测试单
- **验证**: `uv run --extra test --extra report pytest tuner_testkit/apps/testreport tuner_testkit/apps/init_repo`；`tuner-index-ai --check`；`python -m tuner_testkit.apps.init_repo manifest --check`

## 2026-10-15 — tuner-testkit 6.2.0（测试单 skill，用例维护一次一个提交）

- **commit**: `ab75e96`
- **来源**: 试验田的 `maintain-testcases` 1.5.0、`maintain-testsheet` 1.0.0
- **目的**: 一轮测试单从用例库复制步骤，不链回用例库。维护用例时一次工作只做一个提交，正文按用例写下首次创建或变更原因。
- **路径**:
  - `.cursor/skills/maintain-testcases/SKILL.md`
  - `.cursor/skills/maintain-testsheet/SKILL.md`
  - `.cursor/rules/assets-knowledge.mdc`
  - `docs/spec/assets-knowledge-syntax.md`
  - `tuner_testkit/apps/init_repo/scaffold.py`
- **不在同步范围**: 试验田的业务测试单 `assets/testsheet/**`
- **验证**: `uv run pytest tuner_testkit/apps/init_repo/tests/test_scaffold.py`；`tuner-index-ai --check`；`python -m tuner_testkit.apps.init_repo manifest --check`

## 2026-10-12 — tuner-testkit 6.1.0（scaffold 项目名跟随文件夹）

- **commit**: `2919822`
- **目的**: 新建业务仓时可以指定项目名；省略时用目标文件夹名。依赖下限改为执行 scaffold 的 kit 版本，避免新仓再锁在已过期的 `>=4.3.0`。
- **路径**:
  - `tuner_testkit/apps/init_repo/scaffold.py`
  - `tuner_testkit/apps/init_repo/__main__.py`
- **验证**: `uv run pytest tuner_testkit/apps/init_repo/tests/test_scaffold.py`；`manifest --check`

## 2026-10-10 — tuner-testkit 6.0.0（功能用例改为一条一个文件）

- **commit**: `TBD`
- **来源**: 试验田的 `maintain-testcases` 1.3.0（套件目录 + `<id_prefix>-<slug>`）
- **目的**: 功能用例集与下游试验田对齐。5.3.0 的「一个功能一个文件、四级标题、`User-Login0001`」不再新发。
- **路径**:
  - `docs/spec/testcase-syntax.md`
  - `.cursor/skills/maintain-testcases/SKILL.md`、`.cursor/rules/testcases.mdc`
  - `tuner_testkit/testcases/**`
  - `assets/testcases/README.md`
- **不在同步范围**: 试验田里的业务用例正文
- **验证**: `uv run pytest tuner_testkit/testcases/tests`；`python -m tuner_testkit.testcases`；`tuner-index-ai --check`；`python -m tuner_testkit.apps.init_repo manifest --check`

## 2026-09-24 — tuner-testkit 5.3.1（已回答提问归档）

- **commit**: `TBD`
- **目的**: 回答后的问题离开未回答信箱，避免和待回答的问题混在一起。
- **路径**:
  - `tuner_testkit/apps/task/store.py`
  - `docs/spec/work-task.md`、`artifacts-layout.md`
  - `.cursor/rules/work-task.mdc`
- **验证**: `uv run pytest tuner_testkit/apps/task/tests`；`tuner-index-ai --check`；`python -m tuner_testkit.apps.init_repo manifest --check`

## 2026-09-24 — tuner-testkit 5.3.0（功能用例集）

- **commit**: `TBD`
- **目的**: 给 workspace 一套可维护的功能用例目录：模块 README、按功能分文件、四级标题和稳定 CASE ID。
- **路径**:
  - `docs/spec/testcase-syntax.md`
  - `.cursor/skills/maintain-testcases/SKILL.md`、`.cursor/rules/testcases.mdc`
  - `tuner_testkit/testcases/**`
  - `assets/testcases/README.md`
- **验证**: `uv run pytest tuner_testkit/testcases/tests`；`python -m tuner_testkit.testcases`；`tuner-index-ai --check`；`python -m tuner_testkit.apps.init_repo manifest --check`

## 2026-09-24 — tuner-testkit 5.2.0（work task、测试设计、证据附件、人类提问）

- **commit**: `74b1aa8`
- **目的**: 把一次人工发布的任务收成可入库的 `work/tasks`，测试设计与端到端执行互相引用；证据 run 能挂上截图、脱敏日志和接口响应；缺日志来源时立刻写 inbox 问题并挡住任务，等人异步回答。
- **路径**:
  - `docs/spec/work-task.md`、`docs/spec/test-design-syntax.md`
  - `docs/spec/artifacts-layout.md`、`agent-task-log.md`、`metadata-conventions.md`、`assets-knowledge-syntax.md`
  - `tuner_testkit/apps/task/**`、`tuner_testkit/apps/evidence/**`
  - `.cursor/rules/work-task.mdc`、`.cursor/skills/derive-test-design`、`.cursor/skills/run-test-execution`
- **验证**: `uv run pytest tuner_testkit/apps/task/tests tuner_testkit/apps/evidence/tests`；`tuner-index-ai --check`；`python -m tuner_testkit.apps.init_repo manifest --check`

## 2026-09-23 — 工作台展示 AI 组件注册表

- **commit**: `7dfba1c`
- **目的**: 非编码成员在工作台能看到当前 rule / skill / agent / hook 的名称、版本、触发与职责，不必打开 IDE 读 REGISTRY.md。
- **路径**:
  - `tuner_testkit/apps/index_ai/registry.py`（`collect_catalog`，与 REGISTRY 同源扫描）
  - `tuner_testkit/workbench/app.py`、`templates/ai.html`、`templates/ai_detail.html`、`/api/ai`
  - `tuner_testkit/workbench/tests/test_app.py`
- **验证**: `uv run python -m pytest tuner_testkit/workbench/tests/test_app.py`

## 2026-09-22 — action word 嵌套子包发现

- **commit**: `213eb39`
- **目的**: 下游仓把 `db_seed` 按业务域分子目录（`db_seed/audit/*.py`）时，kit `discover` 与工作台 `entry_mtimes` 原先只扫一层，词条进不了 `/words/db_seed`。改为递归导入 + `rglob`。
- **路径**:
  - `tuner_testkit/action_words/registry.py`（`_import_word_package`）
  - `tuner_testkit/catalog/directory.py`（类别目录 `rglob`，跳过 `_` / `__pycache__`）
  - `tuner_testkit/catalog/tests/test_directory.py`
  - `docs/spec/action-words-syntax.md`
  - `.cursor/skills/create-action-word/SKILL.md`（1.1.4：必须接到 kit `@register`，允许嵌套）
- **不在同步范围**: 下游本地 `packages.action_words.registry` 若不双写 kit，仍不可见
- **验证**: `uv run python -m pytest tuner_testkit/catalog/tests/test_directory.py`；innovamed-standard `build_directory` 扫到 63 个 `db_seed`（9 个业务子目录）

## 2026-09-22 — 工作台目录切片 + db_seed 特化页

- **commit**: `6d79804`
- **目的**: 工作台热路径不再每次 `build_catalog`（全仓 + 每文件 `git log`）。只扫规范登记的 `@tool` / `@register` 入口，并按 kit 类别做可演进的特化 UI（先做 `db_seed`）。
- **路径**:
  - `tuner_testkit/catalog/directory.py`（`build_directory`、入口 mtime 缓存）
  - `tuner_testkit/catalog/scan.py`（`scan_action_words(..., isolate=)`）
  - `tuner_testkit/action_words/{base,registry}.py`（`visibility`）
  - `tuner_testkit/workbench/app.py`、`templates/**`、`kinds/`（kind 插件、`/words/db_seed`）
  - `docs/spec/apps-authoring-syntax.md` §8、`docs/spec/action-words-syntax.md`
  - `.cursor/skills/create-app`、`create-action-word`、`.cursor/rules/apps-authoring.mdc`
  - `dogfood/tests/features/workbench/tool_catalog.feature`
- **不在同步范围**: 下游未 re-export kit `@register` 的旧词条（如仍走 `packages.action_words.registry` 的仓）
- **验证**: `uv run pytest tuner_testkit/catalog/tests/test_directory.py tuner_testkit/workbench/tests/test_app.py`；`uv run --directory dogfood behave --stage api --tags "@offline" --tags "~@wip"`

## 2026-09-22 — tuner-testkit 5.1.0（A 收口 + 本地工作台 + C0 元数据）

- **commit**: `ae0a72a`
- **目的**: 收口 workspace 内核（run manifest、CI、多 IDE DNA），并补上本机工作台与元数据铺垫：`tuner-workspace run` / `meta stamp`、`tuner-workbench`、apps `--json`、`metadata-conventions`、`generate-test-report`；dogfood 解除离线子集 `@wip`。
- **路径**:
  - `docs/spec/artifacts-layout.md`、`tuner_testkit/artifacts.py`、`docs/spec/metadata-conventions.md`、`docs/spec/apps-authoring-syntax.md` §7
  - `tuner_testkit/tools/runner.py`、`tuner_testkit/workspace/meta.py`、`tuner_testkit/workbench/**`
  - `.cursor/skills/create-app`、`create-action-word`、`generate-test-report`
  - `tuner_testkit/apps/init_repo/stubs/**`（含 `workbench.cmd` / `workbench.sh`）、`.github/workflows/ci.yml`
  - `tuner_testkit/apps/dna/targets.py`、`tools/git-hooks/secret_scan.py`
  - `dogfood/**`（离线 behave 步骤、工作台入口）
- **不在同步范围**: 下游业务资产；下游 `.gitignore` 由 scaffold 首次生成
- **验证**: `uv run pytest`；`uv run --directory dogfood behave --stage api --tags "@offline" --tags "~@wip"`；`tuner-index-ai --check`；`manifest --check`

## 2026-09-22 — tuner-testkit 5.0.0（Plane Job 协议退场；tool manifest + workspace catalog 中立化）

- **commit**: `968ba3c`
- **来源**: 路线图重排 A→B→C→D（`dogfood/assets/domain-notes/platform/roadmap.md`）；企业 Runner 协议属 D 阶段，步子跨大
- **目的**: 删除 `@plane_app` / `@plane_*` / `index_platform`，把「argparse → JSON Schema + argv_plan」与「workspace 静态扫描」抽成中立模块，供 A（catalog / INDEX 自动区）与 B（本地工作台）复用。
- **路径**:
  - `tuner_testkit/tools/**`（`@tool` 清单、`build_argv` / `validate_params`）
  - `tuner_testkit/catalog/**`（catalog v3、front-matter 读写器）
  - `tuner_testkit/workspace/**`（`tuner-workspace catalog` / `index render|check`）
  - `tuner_testkit/apps/mock_server/tool.py`（原 `plane.py`）
  - 删除：`tuner_testkit/apps/_shared/plane*.py`、`tuner_testkit/action_words/plane.py`、`tuner_testkit/apps/index_platform/**`、`packages/*/plane.py`、`init_repo/stubs/packages/*/plane.py`
  - `.cursor/rules/apps-authoring.mdc`（2.0.0）、`bdd-asset-layering.mdc`、`.cursor/skills/maintain-page-objects`
  - `docs/spec/apps-authoring-syntax.md`、`action-words-syntax.md`、`api-objects-syntax.md`、`page-objects-syntax.md`
  - `pyproject.toml`（5.0.0；`tuner-workspace` 替代 `tuner-index-platform`；uv workspace 成员 `dogfood`）
  - `dogfood/**`（A0 dogfood workspace）、`INDEX.md`、`AGENTS.md`
- **不在同步范围**: 下游业务资产；下游需按 `TEMPLATE-5.0.0.md` 删 `plane.py` 桩
- **验证**: `uv run pytest`；`uv run --directory dogfood tuner-workspace catalog --out -`；`uv run --directory dogfood tuner-workspace index check`；`tuner-index-ai --check`；`manifest --check`

## 2026-09-14 — tuner-testkit 4.4.0（自学习编排 agent + inbox 任务 log）

- **commit**: `27bd59c`
- **来源**: Plane 下游第二轮探索前补齐「可复用账号 + 可编排 workflow + 任务记录」
- **目的**: LLM 下次能自主登录探索；agent 必须把本轮页面与新增资产写入 `artifacts/inbox/`。
- **路径**:
  - `.cursor/agents/sut-self-learning.md`
  - `.cursor/rules/agent-task-log.mdc`
  - `.cursor/agents/bdd-asset-pipeline.md`、`sut-source-to-design.md`
  - `.cursor/skills/explore-sut/SKILL.md`
  - `docs/spec/agent-task-log.md`、`docs/spec/sut-self-learning.md`、`AGENTS.md`
  - `tuner_testkit/apps/init_repo/scaffold.py`（`artifacts/inbox/`、`data/sut-accounts.example.yaml`）
  - `tuner_testkit/apps/dna/build.py`（wheel 构建始终从源树重打 DNA payload，避免旧 payload 短路）
- **不在同步范围**: 下游 `data/sut-accounts.local.yaml` 与业务资产
- **验证**: `tuner-index-ai --check`；`python -m tuner_testkit.apps.init_repo manifest --check`；scaffold 单测

## 2026-09-13 — tuner-testkit 4.3.0（dogfood 回流：evidence CLI + path 插值）

- **commit**: `3697f41`
- **来源**: Plane 下游 `tuner-test-platform-testrepo` workspace→project→issue 切片
- **目的**: 把「capture 必须落盘」做成确定性 CLI；补齐 slug path / url_path 占位；把 UI base URL 纳入 named env；钉 Python 3.12。
- **路径**:
  - `tuner_testkit/apps/evidence/**`
  - `tuner_testkit/api_test/model.py`（`set_path` / `interpolate_path`）
  - `tuner_testkit/page_test/driver.py`（Goto 插值 `url_path`）
  - `tuner_testkit/config.py` / `config/env.py`（`TEST_UI_BASE_URL` profile）
  - `tuner_testkit/apps/init_repo/scaffold.py`（`.python-version`、`<3.14`）
  - `.cursor/skills/analyze-mcp-network/`、`explore-sut`、`derive-design-knowledge`、`freeze-api-objects`
  - `.cursor/agents/sut-source-to-design.md`
  - `docs/spec/design-knowledge-syntax.md` §6、`docs/spec/api-objects-syntax.md`
- **不在同步范围**: 下游 Plane 业务资产（testrepo 的 api/page/design）
- **验证**: `uv run pytest packages/tests/test_execute_build_request.py packages/tests/test_page_test_driver.py packages/tests/test_config_env_profiles.py tuner_testkit/apps/evidence tuner_testkit/apps/init_repo/tests`；`tuner-index-ai --check`；`python -m tuner_testkit.apps.init_repo manifest --check`

## 2026-09-13 — tuner-testkit 4.2.0（SUT 自学习契约 / explore-first）

- **commit**: `c530bc3`
- **目的**: 纠偏 BDD 流水线为 explore-first；统一 evidence 落盘；新增 design/explore
  知识类别与配套 skill/rule。下游 DNA 需 `tuner-dna sync`。
- **路径**:
  - `docs/spec/sut-self-learning.md`、`docs/spec/design-knowledge-syntax.md`
  - `docs/spec/assets-knowledge-syntax.md`、`docs/spec/bdd-run-gherkin-in-playwrightMCP.md`
  - `.cursor/rules/bdd-pipeline-gates.mdc`、`explore-safety.mdc`、`assets-knowledge.mdc`
  - `.cursor/agents/bdd-asset-pipeline.md`
  - `.cursor/skills/explore-sut/`、`derive-design-knowledge/`、`derive-feature-sets/`
  - `AGENTS.md`、`INDEX.md`
  - `tuner_testkit/apps/init_repo/scaffold.py`
- **不在同步范围**: 业务资产（具体 api_objects / features）
- **验证**: `python -m tuner_testkit.apps.init_repo manifest --check`；`tuner-index-ai --check`

## 2026-09-07 — tuner-testkit 4.1.0（元 extra `[all]`）

- **commit**: `TBD`
- **目的**: 新增元 extra `[all]`（能力 extra 并集）；`[dev]` 改为引用 `[all]`。
  下游 tool 域只装默认 wheel 跑 `tuner-init`；`[db]`/`[api]` 等装进业务仓 `.venv`。
  狗食/全能力仓用 `tuner-testkit[all]`。无运行库行为变更。
- **路径**:
  - `pyproject.toml`
  - `README.md`、`INDEX.md`
  - `docs/changelog/TEMPLATE-4.1.0.md`
- **不在同步范围**: 业务资产；DNA 文件哈希未变
- **验证**: `python -m tuner_testkit.apps.init_repo manifest --check`

## 2026-09-06 — tuner-init scaffold works from a blank directory

- **commit**: `TBD`
- **目的**: `uv tool install` 后在非 SUT 目录执行 `tuner-init scaffold` 不再调用
  `project_root()`（鸡生蛋）。骨架文件打进 wheel 的 `init_repo/stubs/`。发布 **4.0.2**。
- **路径**:
  - `tuner_testkit/apps/init_repo/scaffold.py`
  - `tuner_testkit/apps/init_repo/stubs/**`
- **不在同步范围**: 业务资产
- **验证**: 在空目录 `tuner-init scaffold ./new-repo`；pytest `test_scaffold.py`

## 2026-09-06 — isolated `uv build` can bundle DNA

- **commit**: `TBD`
- **目的**: PEP 517 隔离构建里尚未安装本包，`dna/build.py` 直接 `import tuner_testkit` 会失败。
  构建钩子先把源码根加入 `sys.path` 再 bundle。setuptools sdist 会丢掉 ``.*``，
  因此额外把 `dna_payload/.cursor` 拷进 sdist/wheel。顺带改 `project.license` 为 SPDX。
- **路径**:
  - `tuner_testkit/apps/dna/build.py`
  - `pyproject.toml`
- **不在同步范围**: 业务资产
- **验证**: `uv build` 产出 wheel/sdist；wheel 内含 `dna_payload/.cursor/rules`

## 2026-09-04 — DNA 描述对齐 tuner-testkit 分层

- **commit**: `TBD`
- **目的**: rules/skills/agents/specs 不再把运行库写成仓内 `packages/`，不再把平台 CLI
  写成 `apps.recorder`；SUT `python -m apps.<name>` 与 kit `tuner-*` 入口分开；
  changelog/Plane 共享走 `tuner_testkit.apps._shared`。
- **路径**:
  - `.cursor/rules/bdd-asset-layering.mdc`、`apps-authoring.mdc`、`apps-handover.mdc`、
    `bdd-pipeline-gates.mdc`、`index-hygiene.mdc`
  - `.cursor/skills/create-app/SKILL.md`、`create-action-word`、`maintain-page-objects`、
    `release-template`
  - `.cursor/agents/bdd-asset-pipeline.md`、`AGENTS.md`
  - `docs/spec/apps-authoring-syntax.md`、`page-objects-syntax.md`、`action-words-syntax.md`、
    `behave-step-definitions.md`、`assets-knowledge-syntax.md`
- **不在同步范围**: 业务 `packages/api_objects` / `page_objects`；旧运行库树清理另开任务
- **验证**: `python -m tuner_testkit.apps.index_ai`；`python -m tuner_testkit.apps.init_repo manifest --check`

## 2026-09-04 — tuner-testkit 4.0.0（PyPI extras + DNA sync）

- **commit**: `TBD`
- **目的**: 运行库从仓内 `packages/` / `apps/` 迁入 `tuner_testkit/`，发行名 `tuner-testkit`；
  extras 含 `[web-ui]`（预留 `[phone-ui]`）；项目根用 `TUNER_ROOT` / cwd，禁止 kit `__file__`；
  DNA 用 `tuner-dna sync`。破坏性：导入、`TUNER_*`、scaffold 不再拷运行库。
- **路径**:
  - `tuner_testkit/**`、`pyproject.toml`、`LICENSE`
  - `tuner_testkit/apps/dna/**`、`tuner_testkit/apps/init_repo/**`
  - `docs/changelog/TEMPLATE-4.0.0.md`
- **不在同步范围**: 各仓业务 `packages/api_objects` / `page_objects` / `config/env_local.py`
- **验证**: `uv sync --extra dev` 后 pytest；`tuner-dna check`

## 2026-08-31 — recorder 改名合录 + API 冻结内核下沉

- **commit**: `TBD`
- **目的**: 不兼容变更：`python -m tuner_testkit.apps.recorder` 从 mitmproxy 代理改为 headed 合录
  （同一 Playwright 会话默认同时冻 PageObject 与 APIObject；`--page-only` /
  `--api-only` 关一边）。旧代理迁到 `python -m tuner_testkit.apps.api_recorder`。收到 `--port` /
  `--listen_host` **不**静默转发。冻结内核下沉到 `tuner_testkit.api_objects.recording`
  （离线可测；registry/catalog 跳过 `recording/`）。**不替代** BDD Gate 1 的 MCP 网络捕获。
- **路径**:
  - `packages/api_objects/recording/**`（capture / normalize / sanitize / codegen / freeze / mocks / pipeline）
  - `tuner_testkit/apps/api_recorder/**`（mitmproxy CLI + `PlaywrightApiTap`）
  - `tuner_testkit/apps/recorder/**`（合录门面：复用 `PageRecorderSession` + tap）
  - `tuner_testkit/apps/page_recorder/session.py`（`on_page_ready` / `freeze_pages`）
  - `packages/tests/test_api_objects_recording_*.py`、`tuner_testkit/apps/api_recorder/tests/**`、`tuner_testkit/apps/recorder/tests/**`
  - `INDEX.md` §3、`AGENTS.md`、`apps/README.md`、`docs/spec/apps-authoring-syntax.md`
  - `tuner_testkit/apps/init_repo/manifest.py`（`PLATFORM_PATHS` 追加 `tuner_testkit/apps/api_recorder`）
  - `pyproject.toml`（version 3.0.0）
- **不在同步范围**: 具体业务 `packages/api_objects/<路由>/`、`packages/page_objects/<app>/*.py` 正文
- **验证**: `uv run --extra test pytest packages/tests/test_api_objects_recording_*.py packages/tests/test_api_objects_auth.py tuner_testkit/apps/api_recorder/tests tuner_testkit/apps/recorder/tests -q`；
  `uv run python -m tuner_testkit.apps.recorder --help`；`uv run python -m tuner_testkit.apps.api_recorder --help`
  （CI 不启 headed 浏览器、不启 mitmproxy）

## 2026-08-31 — page_recorder：手点冻结 PageModel

- **commit**: `TBD`
- **目的**: 补齐 page_test 的录制接缝：headed Playwright 打开真实页面，人工点/填/浏览时
  直播冻结声明式 `PageModel`（多候选 LocatorSpec + 当前 flow）到 `packages/page_objects/`，
  对标 `apps.recorder` 的「抓一条冻一条」。不使用 `playwright codegen`（无 fallback、
  无 `{{password}}`、不过 `locator_policy`）。绝对 XPath 在 harvest 阶段即丢弃。
  本地 CLI，不加 `@plane_app`；**不替代** BDD Gate 1 的 MCP 网络捕获。
- **路径**:
  - `tuner_testkit/page_test/harvest.py`（DOM 快照 → 排序后的 LocatorSpec；离线可测）
  - `tuner_testkit/apps/page_recorder/**`（session / capture / freeze / codegen / cli）
  - `packages/tests/test_page_test_harvest.py`、`tuner_testkit/apps/page_recorder/tests/**`
  - `docs/spec/page-objects-syntax.md`（录制小节）
  - `docs/spec/apps-authoring-syntax.md`（changelog 覆盖 `packages/page_objects/**`）
  - `.cursor/rules/apps-authoring.mdc` / `index-hygiene.mdc`
  - `.cursor/skills/create-app` / `maintain-index` / `maintain-page-objects`
  - `INDEX.md` §3、`apps/README.md`、`tuner_testkit/page_test/USAGE.md`
  - `tuner_testkit/apps/init_repo/manifest.py`（`PLATFORM_PATHS` 追加 `tuner_testkit/apps/page_recorder`）
  - `pyproject.toml`（version 2.6.0）
- **不在同步范围**: 具体业务页面资产（`packages/page_objects/<app>/*.py` 正文）
- **验证**: `uv run --extra test pytest packages/tests/test_page_test_harvest.py tuner_testkit/apps/page_recorder/tests -q`；
  `uv run python -m tuner_testkit.apps.page_recorder --help`（CI 不启 headed 浏览器）

## 2026-08-31 — api_objects 可回放为 mock server（packages.api_mock / apps.mock_server）

- **commit**: `ca0ebc6`
- **目的**: 让冻结的 `APIModel` 资产能直接起一个可在运行时改返回值的 mock 服务，
  供后端未就绪 / 造异常分支 / 测试平台按需定义响应时使用。
  `APIModel` 只描述请求契约（`response_hints` 仅有顶层键名、状态码只藏在 asserts 里、
  真实样例 `_RECORDED_RESPONSE` 在 `__main__` 块内 import 不到），
  因此**响应契约外置**到 `data/mocks/**.json`，按路由树与资产一一对照，
  `tuner_testkit/api_test` 与 `tuner_testkit/apps/recorder` 均未改动。
- **路径**:
  - `tuner_testkit/api_mock/**`（`spec` 定义 / `store` 磁盘+内存覆盖 / `router` 占位符匹配 / `app` FastAPI）
  - `packages/api_objects/registry.py`（`iter_api_models()`：按文件位置加载，
    修正了按点分模块名发现会跳过 `prod-api` 这类非标识符路由目录的问题）
  - `tuner_testkit/apps/mock_server/**`（`serve` / `seed` / `routes`；`plane.py` 用 `runtime="long_lived"`
    登记为常驻服务，是本仓第一个使用该 runtime 的 app）
  - `tuner_testkit/apps/recorder/**`（新增 `--write-mocks`：抓包时把**完整**响应另存为 mock 定义。
    资产里的 `_RECORDED_RESPONSE` 仍按 `truncate_sample` 截断以保证源码可读，
    完整体走 `data/mocks/`，两者同路由树同 `v<N>`；`mocks.py` + `FreezeResult.major`）
  - `tuner_testkit/apps/init_repo/manifest.py`（`PLATFORM_PATHS` 追加 `tuner_testkit/apps/mock_server`）
  - `pyproject.toml`（新增 `mock` extra：fastapi / uvicorn / httpx）
  - `packages/tests/test_api_mock_*.py`、`test_api_objects_registry.py`、`test_mock_server_seed.py`、
    `tuner_testkit/apps/recorder/tests/test_mock_samples.py`
- **不在同步范围**: `data/mocks/**`（项目业务资产，不随平台 DNA 分发）
- **验证**: `uv run --extra test --extra mock pytest packages/tests apps -q`（+88 用例）；
  真实起服后用未改动的 `APIModel` 经 `TEST_BASE_URL` 打通并通过断言/提取；
  `--write-mocks` 抓 137 行响应后由 mock server 原样回放（资产侧仍为 5 行 + 截断标记，凭证仍掩码）；
  `python -m tuner_testkit.apps.index_platform --out -` 可见 `mock_server`（`plane_runnable=false`）；模板版本 2.5.0

## 2026-08-31 — packages.fake 公共造数包

- **commit**: `22ca2c8`
- **目的**: 提供可 seed 的假数据生成器（医疗 UDI/社信码自研 + Faker zh_CN 包装），CLI/`run`/`catalog` 与业务单值函数共用契约，供测试员手工造数与后续平台 Fake 页。
- **路径**:
  - `tuner_testkit/fake/**`
  - `packages/tests/test_fake_*.py`
  - `packages/action_words/_internal/generators.py`（re-export）
  - `pyproject.toml` / `uv.lock`（`faker`）
  - `.cursor/rules/packages-fake.mdc`
  - `.cursor/rules/bdd-asset-layering.mdc`
  - `.cursor/skills/create-action-word/SKILL.md`
  - `INDEX.md` / `AGENTS.md` / `docs/spec/action-words-syntax.md`
- **不在同步范围**: 试验田业务 db_seed 换 import（后续合并后再改）
- **验证**: `uv run --extra test pytest packages/tests/test_fake_medical.py packages/tests/test_fake_china.py packages/tests/test_fake_core.py packages/tests/test_fake_cli.py -q`；`python -m tuner_testkit.fake list`

## 2026-08-29 — page_test 运行库：PageModel 资产 + 多定位器备用 + doctor 体检

- **commit**: `a0193d9`
- **目的**: 把 Page Object 从「手写 class + `@property` locator」升级为与 `tuner_testkit.api_test`
  同构的运行库：`PageModel`（元素表 + 声明式 flow）对位 `APIModel`、`PageDriver` 对位
  `ApiClient`。三个可落地的收益：
  1. **稳定性**：每个元素挂一组按优先级排序的候选定位器，运行时顺序探测；首选失效时
     自动降级（测试不红），并产出健康事件避免资产静默腐烂。`locator_policy` 把
     `page-objects-syntax.md` 的 locator 约束变成运行时可执行的校验（对位
     `headers_policy` 拦截敏感请求头）。
  2. **独立运行**：`python -m tuner_testkit.page_test run/list/describe/validate/catalog/doctor`，
     以及资产文件 `__main__` 单文件回放（对位 api_objects 的 `auth.replay_execute`）。
  3. **平台化 / recorder 接缝**：`describe()` 导出元素表 + 流程步骤表，step 与
     `LocatorSpec` 双向 `to_dict()` / `from_dict()`，`fingerprint()` 供去重。
  复杂交互走 `BasePage` 逃生舱：动作写 Python 方法，元素声明不变，因此照样享受
  fallback、可视化与体检。自愈只做级别一（运行时降级）与级别二（doctor 审计），
  **不做**级别三（自动改写资产源码）。
- **路径**:
  - `tuner_testkit/page_test/**`（`locator` / `steps` / `model` / `driver` / `base` / `health`
    / `registry` / `errors` / `testing` / `__main__` / `USAGE.md`）
  - `packages/page_objects/session.py`（凭据与单文件回放接缝）、`packages/page_objects/__init__.py`
  - `packages/config.py`（新增 `get_ui_base_url()`：`TEST_UI_BASE_URL` → `config.env` → 回落 API host）
  - `packages/tests/test_page_test_{locator,steps,model,driver,health,base,registry}.py`、
    `packages/tests/test_page_objects_session.py`
  - `docs/spec/page-objects-syntax.md`（改写：元素声明表 / 多定位器 / 两种范式 / 独立运行；
    并修订 locator 策略——绝对 XPath 保留硬禁、相对 XPath 放宽为降权候选、索引定位区分
    「消歧」与「寻址」、纯文本定位降档、修正 test_id 优先级的措辞矛盾）
  - `.cursor/rules/packages-page-test.mdc`（新增）
  - `.cursor/skills/maintain-page-objects/SKILL.md`（2.0.0）
  - `pyproject.toml`（version bump）、`INDEX.md` §2 / §2.2
  - `docs/changelog/FRAMEWORK.md`（本条目）
- **不在同步范围**: 具体业务页面资产（`packages/page_objects/<app>/...`）、`tuner_testkit/apps/page_recorder`
  （后续独立任务，本期只留 codegen 接缝与命名约定）、`Pages` 容器与 `context.pages` 注册
  （第二阶段，本期只提供 `PageDriver.attach(page)` 接缝）
- **验证**: `uv run --extra test pytest packages/tests -q`（全程离线：`driver` 惰性 import
  playwright，`tuner_testkit.page_test.testing` 提供 FakePage 替身）；
  `uv run python -m tuner_testkit.page_test validate`

## 2026-08-24 — 本机多套环境一键切换（tuner_testkit.config）

- **commit**: `1acea69`
- **目的**: 在 gitignore 的 `env_local.ENVIRONMENTS` 维护 prd/uat/dev 等目录，用 `.active_env` / `TUNER_ENV` 激活一套，避免注释切换。
- **路径**:
  - `packages/config.py`
  - `config/env.py` / `config/env_local.py.example`
  - `packages/tests/test_config_env_profiles.py`
  - `tuner_testkit/apps/init_repo/manifest.py`（manifest 排除 `env_local.py` / `.active_env`）
- **不在同步范围**: `config/env_local.py`、`config/.active_env`（本机密钥与激活指针）
- **验证**: `uv run --extra test pytest packages/tests/test_config_env_profiles.py -q`；模板版本 2.4.0

## 2026-08-19 — 细分 @plane_* 资产注册，Formulation 不再文件扫描

- **commit**: `a1f75b5`
- **来源**: `plane-dogfood@e04974d`
- **目的**: 能在 Plane 上架的 action words / API / Page 必须 opt-in；执行走 `python -m tuner_testkit.action_words`，不再把 packages 伪装成 `apps.action_runner`。
- **路径**:
  - `packages/action_words/plane.py`
  - `packages/api_objects/plane.py`
  - `packages/page_objects/plane.py`
  - `tuner_testkit/apps/_shared/plane_asset.py` / `tuner_testkit/apps/_shared/plane.py`
  - `tuner_testkit/apps/index_platform/build.py`
  - 删除 `apps/action_runner/**`
  - `docs/spec/action-words-syntax.md` / `docs/spec/apps-authoring-syntax.md`
  - `.cursor/rules/apps-authoring.mdc` / `.cursor/rules/bdd-asset-layering.mdc`
  - `INDEX.md` / `apps/README.md`
  - `pyproject.toml`（version 2.3.0）
  - `docs/changelog/FRAMEWORK.md`（本条目）
- **不在同步范围**: 业务 action words 实现、具体 `.feature`
- **验证**: `pytest tuner_testkit/apps/_shared/tests tuner_testkit/apps/index_platform/tests -q`；catalog `tools` 不含 `db_seed`；`components.action_words` 不含 `context`

## 2026-08-19 — apps 作为常规包，保证 python -m 可导入

- **commit**: `20cbc19`
- **来源**: `plane-dogfood@64bf0be`
- **目的**: 补 `apps/__init__.py`，避免 uv 安装后 `python -m tuner_testkit.apps.index_platform` 找不到模块。mitmproxy 移到 `recorder` extra，Runner 的 `uv sync --no-dev` 不再拉 cryptography。
- **路径**:
  - `apps/__init__.py`
  - `pyproject.toml`（`namespaces = true`；mitmproxy 仅 recorder extra）
  - `uv.lock`
  - `tuner_testkit/apps/init_repo/manifest.py`
  - `docs/spec/apps-authoring-syntax.md`
  - `.cursor/rules/apps-authoring.mdc`
  - `docs/changelog/FRAMEWORK.md`（本条目）
- **不在同步范围**: 业务 action words、具体 `.feature`
- **验证**: `python -m tuner_testkit.apps.index_platform --out -` 在干净 venv 中可启动

## 2026-08-19 — Plane Job 协议：@plane_app + action_runner + index_platform

- **commit**: `02dc0f8`
- **来源**: `plane-dogfood@03c3bc2`
- **目的**: 本地维护工具（dump_ddl / recorder / init_repo / index_ai）不上 Plane；造数/API 动作经 `apps.action_runner` 浅封装 `tuner_testkit.action_words`；Sync 用 `apps.index_platform` 导出 catalog。BDD/pytest 仍只引用 packages。
- **路径**:
  - `tuner_testkit/apps/_shared/plane_app.py`
  - `apps/action_runner/**`
  - `tuner_testkit/apps/index_platform/**`
  - `tuner_testkit/apps/init_repo/manifest.py`（PLATFORM_PATHS）
  - `docs/spec/apps-authoring-syntax.md` / `docs/spec/action-words-syntax.md`
  - `.cursor/rules/apps-authoring.mdc` / `.cursor/rules/bdd-asset-layering.mdc`
  - `INDEX.md` / `apps/README.md`
  - `pyproject.toml`（version 2.2.0）
  - `docs/changelog/FRAMEWORK.md`（本条目）
- **不在同步范围**: 业务 action words 实现、具体 `.feature`
- **验证**: `uv run pytest apps/action_runner/tests tuner_testkit/apps/index_platform/tests -q`；`python -m tuner_testkit.apps.index_platform --out -` 的 tools 含 `db_seed` 不含 `dump_ddl`

## 2026-08-18 — dump_ddl 样例 INSERT 剔除密钥列并限制体积

- **commit**: `72e2a7d`
- **目的**: 恢复默认「注释掉的最新一行 INSERT」，同时避免 password/token/session 与超长 stdout 进入 `assets/ddl`。
- **路径**:
  - `tuner_testkit/apps/dump_ddl.py`
  - `.cursor/skills/dump-ddl/SKILL.md`
  - `apps/README.md`
  - `docs/changelog/FRAMEWORK.md`（本条目）
- **不在同步范围**: 业务 `assets/ddl` 正文
- **验证**: `python -m tuner_testkit.apps.dump_ddl --all --datasource main` 后 `.sql` 末尾有 `-- INSERT` 或省略说明，且不含 `password`/`token` 字面量

## 2026-08-18 — PostgreSQL 数据源 + dump_ddl pg_catalog + /dump-ddl skill

- **commit**: `48eb39d`
- **目的**: 让平台能对接 Plane 等 PostgreSQL 库：`tuner_testkit.db` 增加 `type: postgres`（psycopg3）；`dump_ddl` 从 `pg_catalog` 导出 DDL；新增 on-demand skill `/dump-ddl` 固化「配 env → 拉表结构 → 更新索引」流程。
- **路径**:
  - `tuner_testkit/db/**`（`connection` / `client` / `__init__`）
  - `packages/action_words/_internal/db.py` / `base.py`
  - `packages/tests/test_db_multidatasource.py`
  - `tuner_testkit/apps/dump_ddl.py` / `apps/README.md`
  - `config/env.py` / `config/env_local.py.example`
  - `pyproject.toml`（`psycopg[binary]>=3.2`，version 2.1.0）
  - `.cursor/rules/packages-db.mdc`
  - `.cursor/skills/dump-ddl/SKILL.md`
  - `.cursor/skills/create-action-word/SKILL.md`
  - `docs/spec/action-words-syntax.md` / `docs/spec/apps-authoring-syntax.md`
  - `INDEX.md`
  - `docs/changelog/FRAMEWORK.md`（本条目）
- **不在同步范围**: 业务 `assets/ddl` 内容、`config/env_local.py`、`config/env_overlay.py`（试验田覆盖）
- **验证**: `uv run pytest packages/tests/test_db_multidatasource.py -q`；有 Plane 本地库时 `python -m tuner_testkit.apps.dump_ddl --all --datasource main`

## 2026-08-14 — 多数据源 SQLAlchemy（packages.db + dump_ddl + action word datasource）

- **commit**: `642abf7`
- **来源**: `trial-repo@f2ccb95`
- **目的**: 引入 SQLAlchemy 引擎内核与命名数据源（`DATABASES` 别名），使测试框架可同时对接 MySQL / SQL Server；action word 类元数据 `datasource` 显式声明目标库；`dump_ddl` 双方言导出到 `assets/ddl/<别名>/`。
- **路径**:
  - `tuner_testkit/db/**`（`DbClient` / `connection` / `__init__`）
  - `packages/action_words/base.py` / `context.py` / `_internal/db.py` / `__init__.py`
  - `tuner_testkit/apps/dump_ddl.py` / `apps/README.md`
  - `packages/tests/test_db_multidatasource.py`
  - `config/env.py`（仅 `DATABASES` 结构与占位示例；真实连接信息不入模板）
  - `docs/spec/action-words-syntax.md`
  - `.cursor/rules/packages-db.mdc`
  - `.cursor/skills/create-action-word/SKILL.md`
  - `pyproject.toml`（`sqlalchemy>=2.0`、`pymssql>=2.3.0`）
  - `docs/changelog/FRAMEWORK.md`（本条目）
- **不在同步范围**: 业务 action_words、具体连接凭据、业务 `assets/ddl` 内容
- **验证**: `uv run pytest packages/tests/test_db_multidatasource.py packages/tests/test_action_word_template.py -q`

## 2026-08-14 — APIModel multipart + recorder 冻结 Excel 上传

- **commit**: `3e0c74a`
- **来源**: `trial-repo@fae6d0f`
- **目的**: APIModel 支持 `body_format=multipart` / `set_files`；recorder 正确解析并冻结 multipart（仅字段名，不写文件内容），形成「捕获 → 冻结 → 调用」闭环，便于 Excel 导入类接口自动化。
- **路径**:
  - `tuner_testkit/api_test/**`（`model.py` / `client.py` / `errors.py` / `USAGE.md`）
  - `packages/api_objects/auth.py`（`replay_execute(..., files=)`）
  - `packages/tests/test_multipart_files.py`
  - `tuner_testkit/apps/recorder/**`（`capture` / `normalize` / `codegen` / `freeze` / README / tests）
  - `docs/spec/api-objects-syntax.md`
  - `.cursor/skills/freeze-api-objects/SKILL.md`
  - `docs/changelog/FRAMEWORK.md`（本文件）
- **不在同步范围**: 具体业务 `api_objects` 路由资产、业务 action_words / features
- **验证**: `uv run pytest packages/tests/test_multipart_files.py tuner_testkit/apps/recorder/tests -q`
