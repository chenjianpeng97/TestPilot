---
name: generate-testsheet-report
version: 1.2.0
group: internal
description: Turns one or more filled test sheets under assets/testsheet/<round>/ into a GJB438B software test report — a reviewed Markdown at assets/testreport/<sut>/<yyyy-mm>/<slug>.md plus a Word docx rendered by tuner-testreport from the kit GJB438B template into artifacts/runs/. Use when the user asks to 测试单生成测试报告, 出测试报告 docx, GJB438B 报告, 软件测试报告, or mentions a testsheet together with a report. Internal step: usually reached through generate-test-report. Do not use for behave/pytest regression runs or testdesign click reports (run-test-execution).
---

# Generate testsheet report

## Scope

- **Write**: `assets/testreport/<sut>/<yyyy-mm>/<slug>.md`；画像 `assets/testreport/profiles/<sut>.md`；测试单里经用户确认的缺陷列、本轮信息、计数；`work/tasks/TASK-*.md`；`INDEX.project.md`；测试单有改动时 `assets/testsheet/CHANGELOG.md`。
- **Read**: `assets/testsheet/<轮次>/`（含 `testcase/` 副本）、测试单「依据」引用的文档、画像、`INDEX.project.md`。
- **Run**: `tuner-testreport`（`stats` / `draft` / `render`），`render` 要 `report` extra；说明见 `tuner-testreport --help` 与平台仓 `tuner_testkit/apps/testreport/README.md`。docx 落 `artifacts/runs/<run_id>/`，不入库。
- **Out of scope**: 改 `assets/testcases/`（`maintain-testcases`）、改测试单的结果与实测记录（`maintain-testsheet`，结果以测试人填写为准）、改 Word 模板版式。

## Steps

1. **定范围、登记任务**：测试单目录（可多份，同一用例以后者为准）；`<sut>` 取用例副本 front-matter 的 `sut:`，没有再看 `INDEX.project.md` 与已有 `assets/testreport/<sut>/`；`<slug>` 用 ASCII（例 `260101-login`）。用 `tuner-task create --type explore` 登记任务，`--input` 写测试单和它的依据文档。
2. **检查测试单**：

   ```text
   uv run tuner-testreport stats assets/testsheet/<轮次> --check
   ```

   按输出改到 `errors=0`、`warnings=0`：
   - `count_mismatch`：「共 N 条」与五个计数按输出的 `rows` 改。
   - `defect_columns_missing`：缺陷表迁到 `编号 | 用例 | 现象 | 严重程度 | 类型 | 状态 | 是否阻塞后续`（`maintain-testsheet` 1.1），原有内容逐格搬过去，编号改 `D1`、`D2`。没有缺陷时只留一行 `无`。
   - `defect_severity_invalid` / `defect_type_invalid` / `defect_status_invalid`：取值只能是 致命/严重/一般/轻微、需求/设计/编码/文档/其它、激活/已解决/关闭。原表没有的值放进第 3 步一起问，不要按现象猜。
   - `info_missing`（测试人、日期、版本）：放进第 3 步一起问。日期写 `2026-10-21`、`2026.10.21` 或起止两个日期都行。
   - 计数以外的结果和实测记录不改。
3. **一次问全**：读画像（没有就按「画像」一节建骨架，`draft` 会列出空字段），把第 2 步和画像里缺的项合成**一次** AskQuestion，每题给「留空」或「我来填」的选项：
   - 测试人：候选取 `git log --format=%an` 里的作者。
   - 版本：给「未注明」选项。
   - 基本信息：用户常不清楚这些词，题干里一并解释。编制单位是编写这份报告的单位，通常是测试方；需方是提需求、做验收的单位；开发方是研制单位；保障机构是上线后负责运维保障的单位；文档标识号、软件标识号是单位内部编号；程序规模写代码行数的量级。
   - 软件环境、硬件环境、测试环境影响三张表：填写，或留空。
   - 通过准则：给常用组合（例「不允许遗留 1级、2级，允许未执行」）。
   - 提交方式：测试单、用例库还没入库时，问要不要一起按类别提交。

   系统名称、系统简介可以取测试单依据文档的标题和「项目说明」，在画像 `source` 里写明出处。编制单位是必填项：用户答不上来时，可以按证据推断（测试人员提交邮箱的域名、开发方），推断写进画像正文，在总结里请用户确认。
4. **写画像**：用户的回答写进画像。要留空的基本信息格子空着，报告里写「/」。要留空的表格写**一行全是 `/`**，例如 `| / | / | / | / | / | / |`，不要留成空表，否则 `draft` 会出 TODO，下次 `draft --force` 又得手改。
5. **起草**：

   ```text
   uv run tuner-testreport draft assets/testsheet/<轮次> --sut <sut> --slug <slug> --env <env> --task <TASK-…>
   ```

   已有同名报告要用户同意才加 `--force`。`--force` 会覆盖第 6 步的手工整理，覆盖前先看 `git diff` 把要保留的段落记下来。
6. **处理 TODO 与手工整理**：`draft` 打印的每条 `todo` 对应报告里一处 `<!-- TODO … -->`。
   - 画像或测试单缺字段：回到第 3、4 步补源头，再重跑 `draft --force`，不要只改报告。
   - 改进建议：按遗留缺陷与未执行用例写一两句，可引用测试单「实测记录」和「测的时候先记住」；没有建议写「无。」。
   - 结论待评审：画像补「通过准则」后重跑；用户直接给结论时照写，并在「评估说明」末尾写明是谁定的。
   - 「5 注释」：工具只写测试单依据和未执行、部分通过清单。测试单开头写到的范围说明（本轮覆盖的需求、不在本轮的需求及原因）手工补进来，每条一段。
   - 数字、缺陷矩阵、首轮与回归、用例附表由工具算，不手改。要改就改测试单再重跑。
   - 手工改过的段落记进任务的 Decisions，重跑后照着补回。
7. **渲染与核对**：

   ```text
   uv run --extra report tuner-testreport render assets/testreport/<sut>/<yyyy-mm>/<slug>.md
   ```

   默认用 kit 自带的 GJB438B 模板；用户给了版式不同的样例时，先 `tuner-testreport build-template <样例.docx> --out data/testreport/<名称>.docx`，再加 `--template` 渲染。有 TODO 或章节缺失会拒绝。输出的 `check leftover_tags=0 case_rows=<N> ok` 是放行条件：没有残留模板标签，第 6 章行数等于用例数。看版式时可以用 Word 打开，提示更新域时选「是」刷新目录页码。用脚本驱动 Word 导出 PDF 时，如果卡住超过一分钟，结束自己起的 Word 进程（不要动用户开着的窗口），不要反复重试，以 `check` 结果为准。
8. **收尾**：
   - `uv run tuner-workspace meta stamp` 画像与报告。
   - `uv run tuner-workspace catalog`，再 `uv run tuner-workspace index render` 刷新 `INDEX.project.md` 自动区；人工区补一行报告的用途和结论，画像有推断或留空的写明。
   - `tuner-task bind --output` 写报告、画像；任务正文写 Decisions（用户回答、推断、手工整理）和 Result；`tuner-task finish`。
   - 测试单的缺陷列、本轮信息或计数有改动时：`uv run tuner-workspace changelog append --area testsheet --skill generate-testsheet-report --action 更新 --items <轮次> --reason …`。
   - 测试单里有缺陷时建议用户跑 `maintain-defectlib`，报告的缺陷节可引用 `knowledge/defects/DEF-…`。
9. **提交**：按 `docs/spec/commit-convention.md`，不 push。报告、画像、任务一个提交，例 `docs(assets,work,index): 260101 登录测试报告`。用户同意一起提交测试单和用例库时，按类别分开：
   - 用例库：按 `maintain-testcases` 的格式，正文每个用例一段「首次创建」或「变更原因」。
   - 测试单：`assets/testsheet/<轮次>/` 一个提交。
   - 报告：同上。

   工作区里不属于本次的改动不要暂存。`INDEX.project.md` 等共享文件里混着几类改动时，每个提交只暂存属于自己的行：生成该版本的内容，`git hash-object -w --stdin --path <文件>` 后 `git update-index --cacheinfo 100644,<sha>,<文件>`，工作区文件不动。hook 没启用时手动跑 `tools/git-hooks/secret_scan.py` 和 `validate_commit_msg.py`。docx 在 `artifacts/runs/`，告诉用户路径，不提交。

## 折算与结论

| 测试单 | 报告 |
| --- | --- |
| 通过 | 通过 |
| 失败、部分通过 | 未通过 |
| 未执行、阻塞 | 未执行 |
| 缺陷表里出现的用例 | 首轮执行且未通过 |
| 缺陷都已解决或关闭的用例 | 回归重用；缺陷都关闭且有结果的算回归执行 |
| 严重程度 致命/严重/一般/轻微 | 1/2/3/4级 |
| 状态 关闭 | 归零；激活、已解决算遗留，进 3.1 残留问题 |

结论只看画像「通过准则」：遗留了「不允许遗留的缺陷等级」里的等级，或「允许未执行用例」不是「是」却有未执行 → 未通过测试；没有准则、遗留缺陷未定级、有未通过用例却没有遗留缺陷 → 待评审；其余 → 通过测试。

「2 引用文档」除画像列的文档外，自动加测试单本身和测试单「依据」里的每一项。依据写仓内 `.md` 路径时，标题取该文档的 front-matter `title` 或一级标题，发布日期取它的「发布日期」「建立日期」「编制日期」行或 front-matter `date`、`created`。

## 画像

`assets/testreport/profiles/<sut>.md`，`kind: domain-note`、`domain: testreport`。章节名固定，`tuner-testreport` 按名取：

```markdown
## 基本信息

| 项 | 内容 |
| --- | --- |
| 系统名称 | |
| 编制单位 | |
| 文档标识号 | |
| 缩略语 | 无 |
| 需方 | |
| 开发方 | |
| 保障机构 | |
| 软件标识号 | |
| 软件名称 | |
| 编程语言 | |
| 程序规模 | |
| 测试类型 | 功能测试 |

## 系统简介

## 运行现场

## 引用文档

| 文档编号 | 文档标题 | 编写单位 | 发布日期 |

## 软件环境

| 支持软件名称 | 版本号 | 用途 | 介质 | 来源 | 保密性 |

## 硬件环境

| 硬件名称 | 配置 | 推荐型号 | 用途 | 数量 | 保密性 |

## 测试环境影响

| 测试环境 | 实装环境 | 影响分析 | 解决措施 |

## 通过准则

| 项 | 内容 |
| --- | --- |
| 不允许遗留的缺陷等级 | 1级、2级 |
| 允许未执行用例 | 是 |
```

「运行现场」为空时，报告用测试单「本轮信息」的环境。表格要留空时写一行 `/`。「通过准则」的值由用户或评审人定，第一次建画像时问，不要默认填。

## Hard rules

- 不写密码、token、Cookie；账号只写 `account_id`。
- 数字只来自 `tuner-testreport` 的输出。
- 严重程度、类型、状态、版本、单位名称、通过准则这类判断由人给，问了再写；推断的必须在画像和总结里标明。
- 报告 Markdown 是审阅对象；docx 每次从它重渲染，不手改 docx 再回写。
