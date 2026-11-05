---
name: execute-testsheet
version: 1.2.0
group: action
description: Executes a test sheet round under assets/testsheet/<round>/ case by case - guided manual steps with the tester, the configured browser channel, or existing action words / page objects / API objects - and writes back results (通过 / 失败 / 阻塞 / 忽略), observations, evidence, and defects, then checks counts with tuner-testreport stats. Use when the user says 执行测试单, 跑测试单, execute-testsheet, 回归这一轮, or wants results filled into a testsheet.
---

# execute-testsheet — 按测试单逐条执行并回写

测试单由 `maintain-testsheet` 组好；本 skill 负责「执行 + 回写」。步骤以本轮 `testcase/` 副本为准。
测试单格式与取值见 `.cursor/skills/maintain-testsheet/SKILL.md` 的 Sheet / Update 两节。

## Scope

- **读**：`assets/testsheet/<轮次>/testsheet.md`、`testcase/` 副本、`uv run tuner-config show --json`（环境与浏览器通道）、
  `data/sut-accounts.local.yaml`（按 `role` 挑账号，只在本机用）、`INDEX.project.md`（已有 action words / page objects / api objects / 端口）。
- **写**：`testsheet.md` 的结果、实测记录（一句摘要）、计数、缺陷表、本轮信息；**本轮 `testcase/` 副本里每个步骤下的执行记录**
  （格式见 `docs/spec/testsheet-step-record.md`）；`assets/testsheet/<轮次>/evidence/` 与截图；`assets/testsheet/CHANGELOG.md`。
- **不写**：用例库 `assets/testcases/`（需要沉淀时另走 `maintain-testcases`）；不在测试单目录放可执行脚本。

## 1. 开轮

1. 问用户轮次（目录名）、执行范围（全部 / 某个范围块 / 指定用例）、测试人、环境、被测版本。
2. `uv run tuner-config show --json` 确认 `active_env` 与用户说的环境一致；不一致先停下问，必要时 `tuner-config use`。
3. 把测试人、日期、版本、环境填进「本轮信息」。

## 2. 逐条执行

对范围内每条结果为空（待执行）或用户点名重跑的用例，读副本的前置条件、测试数据、步骤，选执行方式：

| 方式 | 何时用 | 怎么做 |
| --- | --- | --- |
| 人工引导 | `execution: 手工`，或需要人看 / 人判断 | 一步一步把「操作」告诉测试人，问看到的结果；按「预期」判定 |
| 浏览器通道 | 页面操作且用户同意由你来点 | 读 `channels.browser`，按 `docs/spec/browser-channel.md` 操作与截图；每步对照「预期」 |
| 已有自动化资产 | `execution: 自动`，或 INDEX 里已有对应 action word / page object / api object | `uv run tuner-action-words run <word_id> …`、`uv run tuner-page-test run <page_id> --flow …`；只调用现有资产，不临时拼请求或选择器 |

- 账号按副本的 `data: [account:<id>]` 或权限要求的 `role` 选；对话里只说 `account_id`。
- 需要数据层判定（「数据级」预期：状态、库存、消息）时，用现有 db_assert 类 action word 或 `tuner_testkit.db` 查询（只读），把 SQL 副本放 `assets/sql/`；不改数据。
- 需要后端日志判定时，先看 `doctor` 的 `ports.log-source`：已绑定就 `uv run python -m <模块> --since … --until … --trace-id … --json`，
  结果写进实测记录，原文存 `evidence/`；未绑定就把这条日志判定记为「阻塞」并说明，**不要临时写取日志代码**。

## 3. 回写（每条用例执行完就写，不攒到最后）

- **步骤级执行记录写在用例副本里**（规范 `docs/spec/testsheet-step-record.md`）：每执行完一步，就在该步骤块「预期」后面追加
  `- 执行：通过|失败|阻塞`；失败、阻塞再写 `- 实际：`（看到了什么）和 `- 卡点：`（卡在哪个动作、接口、元素，返回了什么，写具体）；
  阻塞还要写 `- 缺少：`（缺环境、数据、账号、权限、日志通道、判定规则……什么才能继续）；有截图或接口 JSON 写 `- 证据：`（相对测试单目录）。
  不改「操作」「预期」原文。没执行到的步骤不写记录。
- 「结果」只写四个词：通过、失败、阻塞、忽略；还没测就留空。没有「部分通过」：有一步产品行为不符就是失败，步骤写清哪步通过、哪步失败。
  结果是失败、阻塞的用例，副本里必须有带「卡点」的失败或阻塞步骤；忽略（用户明确说本轮不测）的用例在「实测记录」写原因，不写步骤记录。
  `testsheet.md` 的「实测记录」写一句摘要（如「第 2 步阻塞：登录接口 502，详见副本」）；不写密码、token、Cookie。
- 截图放本目录，文件名用用例 ID；接口 JSON、日志片段放 `evidence/`。
- 失败的产品问题进「缺陷」表：编号 `D<n>` 顺延不复用，严重程度 / 类型 / 状态只用测试单规定的词。
  步骤本身有误（不是产品问题）：改本轮 `testcase/` 副本的步骤正文并在实测记录说明，不记缺陷。
- 回归：缺陷修好后重跑对应用例，结果改为回归结果，缺陷行状态改为「关闭」，不删行。

## 4. 收口

1. `uv run tuner-testreport stats assets/testsheet/<轮次> --check`；按输出的 `rows` 更新「共 N 条」和五个计数，修掉它报的取值问题。
   它也校验步骤级执行记录（`step_record_*`）：阻塞缺「缺少」、失败缺「卡点」、结果为失败或阻塞但副本没有卡点记录，都按 error 处理，补全后再收口。
2. 留痕：
   ```bash
   uv run tuner-workspace changelog append --area testsheet --skill execute-testsheet --action 执行 \
     --items <轮次> --reason "通过 a / 失败 b / 阻塞 c；新缺陷 D3,D4"
   ```
3. 有缺陷时接着用 `maintain-defectlib` 把每个 `D<n>` 记录成 `knowledge/defects/DEF-…`（固定模板，`python -m tuner_testkit.defects new`），
   回归已有缺陷时更新原文件；本轮测完要出报告时走 `generate-test-report`。
4. 一次执行会话一个提交，scope `assets`（如 `test(assets): execute 261104订单 round 1`）。

## Hard rules

- 不编副本和用户都没给的判定规则；预期不清楚时问用户，结果先记「阻塞」，并在对应步骤写清「卡点」和「缺少」。
- 卡点要具体到步骤：不能只在实测记录写「阻塞」或「失败」而不在副本对应步骤下说明。
- 不把「页面提示成功」当作数据已正确：副本预期写到数据层的，就要有数据层证据，否则记「失败」并在卡点里写「只有页面证据、没有数据层证据」。
- 不改用例库；不在测试单目录放脚本；不写密钥。
