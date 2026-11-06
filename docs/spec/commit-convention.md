# 提交规范（commit-convention）— 单一事实源

> 采用 **Conventional Commits**，并用一套**对齐分层与资产类别的 scope**，让每次提交
> 一眼看出"改了什么层/什么资产"。本文件是 type/scope 的唯一事实源，`commit-msg`
> 校验脚本（`tools/git-hooks/`）与 `.cursor/rules/commit-convention.mdc` 都以此为准。

## 1. 格式

```text
<type>(<scope>): <subject>

[optional body]

[optional footer]
```

- `type(scope): subject` 为首行；不兼容变更加 `!`（如 `feat(api_objects)!: ...`）。
- 一次提交涉及多层时，scope 可用逗号分隔：`feat(apps,packages): ...`。
- subject 用祈使句、简洁；中英文皆可。

## 2. type（允许集合）

| type | 含义 |
| --- | --- |
| `feat` | 新增能力（新工具、新资产、新用例、录制新接口） |
| `fix` | 修复缺陷 |
| `refactor` | 重构，不改行为 |
| `docs` | 文档/规范 |
| `test` | 测试代码 |
| `perf` | 性能 |
| `chore` | 杂项（依赖、刷新自动区资产等） |
| `build` / `ci` | 构建 / CI |
| `style` | 纯格式 |
| `revert` | 回滚 |

## 3. scope（对齐分层与资产类别）

| scope | 对应路径 | 典型场景 |
| --- | --- | --- |
| `knowledge` | `knowledge/**` | 刷新 DDL、ingest 需求与 wiki、沉淀缺陷 |
| `assets` | `assets/**` | 更新测试设计/用例/测试单/报告/业务 SQL |
| `apps` | `apps/**`、`tuner_testkit/apps/**` | 新增/修改工具（SUT 私有 + kit CLI） |
| `packages` | `packages/**`、`tuner_testkit/**`（通用运行库） | db/logging/api_test/excel/config |
| `api_objects` | `packages/api_objects/**` | 录制/冻结接口资产 |
| `page_objects` | `packages/page_objects/**` | UI 资产 |
| `action_words` | `packages/action_words/**` | 业务动作 |
| `tests` | `tests/**` | feature/steps/pytest |
| `docs` | `docs/**` | 规范/说明 |
| `rules` | `.cursor/rules/**` | 规则 |
| `skills` | `.cursor/skills/**` | 技能 |
| `agents` | `.cursor/agents/**` | 编排 |
| `hooks` | `.cursor/hooks*`、`tools/git-hooks/**` | 钩子 |
| `init_repo` | `tuner_testkit/apps/init_repo/**` | 初始化工具与 release |
| `index` | `INDEX.md`、`INDEX.project.md`、`.cursor/REGISTRY.md` | 索引/注册表 |
| `work` | `work/**` | 入库的任务（`work/tasks`，含附件）与任务上的 Decision |

> `packages` 视为 `api_objects` / `page_objects` / `action_words` 的**上位 scope**：
> 声明 `packages` 可覆盖这三者的改动。

## 4. 示例

```text
feat(api_objects): record login and checkout routes
chore(knowledge): refresh order ddl via dump_ddl
feat(knowledge,assets): ingest refund PRD and add refund cases
feat(apps): add data export checker tool
docs(spec): add apps-authoring-syntax
chore(rules): scope bdd-pipeline-gates off always-apply
feat(apps,packages): add init_repo and release manifest surface
```

## 5. 校验（commit-msg hook）

`tools/git-hooks/commit-msg` 在提交时校验：

1. 首行符合上面的 Conventional Commits 语法，`type`/`scope` 在允许集合内；
2. **声明的 scope 与实际改动文件一致**：取 `git diff --cached --name-only`，把路径映射到层，
   断言声明 scope 覆盖了所有被改动且可识别的层（`packages` 覆盖三个子资产层）。

安装（本地一次性；不改全局配置）：

```bash
git config core.hooksPath tools/git-hooks
```

CI 可复用同一校验脚本。合并/回滚提交（`Merge`/`Revert` 开头）跳过校验。
测试或活文档可用环境变量 `TUNER_COMMIT_STAGED`（换行分隔的路径列表）注入"已暂存文件"，替代 `git diff --cached`。
