---
name: maintain-testsheet
version: 1.5.1
group: action
description: Builds and updates a test sheet under assets/testsheet/<round>/testsheet.md, copying the selected ready cases from assets/testcases into that round's testcase/ folder and linking only those copies. Use when the user asks to 生成测试单, 维护测试单, 测试单, or mentions assets/testsheet or testsheet.md. Executing the sheet and writing results case by case is execute-testsheet. Do not use to edit the case library, write a testdesign, or curate assets/testreport.
---

# Maintain testsheet

## Scope

- **Write**: `assets/testsheet/<轮次>/testsheet.md`，同目录 `testcase/` 里的用例副本，`assets/testsheet/CHANGELOG.md`。
- **Read**: `assets/testcases/`。有 `INDEX.project.md` 时先读，只采用已有事实。
- **Out of scope**: 改 `assets/testcases/`（用 `maintain-testcases`）、写 `assets/testdesign/`、写 `assets/testreport/`（测试单出报告用 `generate-testsheet-report`）。已有的 `assets/testreports/**/测试单.md` 不搬，除非用户明确要求迁移。

## Layout

```text
assets/testsheet/<轮次>/
  testsheet.md
  testcase/<模块>/README.md
  testcase/<模块>/<套件>/README.md
  testcase/<模块>/<套件>/<用例ID>.md
  evidence/
```

`<轮次>` 用用户给的目录名。没给就用 `yyMMdd` 加模块名，例如 `260101登录`。一轮一个目录。

做完的轮次归档到 `assets/testsheet/archived/<轮次>/`（见下「归档」）。找「当前轮次」时跳过 `archived/`，它不是一个轮次。

## Generate

1. 读模块 README 和相关套件 README。范围按用户点名的模块、套件或用例 ID。没点名到单条时，纳入该范围内 `status: 就绪` 的用例。`status: 废弃` 不复制、不进表，在测试单开头点名。
2. 用文件复制，不要重写正文。用例文件、该模块 README、被选中套件的 README 都复制到上面的 `testcase/` 路径。复制后不再从用例库刷新，除非用户要求重新提取。
3. 写 `testsheet.md`。不写 YAML 头。用例列只链副本：

```text
[User-Login-open](testcase/登录/登录页/User-Login-open.md)
```

不要链 `assets/testcases/` 或 `../../testcases/`。

从副本填列，不要另编业务规则：

| 列 | 来源 |
| --- | --- |
| 用例 | 副本文件名，链到副本 |
| 测试点 | `<type>-<title>`，如 `正向-打开登录页` |
| 数据 | `## 测试数据` 的第一句。没有则用 `## 前置条件` 的第一句 |
| 预期要点 | 第一步 `预期` 收成一句 |
| 结果 | 空（还没执行） |
| 实测记录 | 空 |

分组：模块 README 的 `## 范围` 已有编号块时，用那些块做 `##`。块内按套件 README 的顺序各做一个 `###` 和一张表。没有范围编号时，一个套件一个 `##`。不要把一个套件拆进两张表，除非用户要求。

## Sheet

```markdown
# <主题>测试单

共 N 条。步骤在本目录 `testcase/`。`<废弃ID>` 已废弃，不在本单。

依据：<用户给出的需求或来源路径>。

## 怎么填

- 「结果」只写四个词：通过、失败、阻塞、忽略；还没测就留空。没有「部分通过」「未执行」。
  失败 = 产品行为与预期不符；阻塞 = 执行不下去、给不出通过或失败的结论；忽略 = 本轮有意不测，「实测记录」必须写原因。
- 「实测记录」写看到的文案、单号、库存状态。不写密码、token、Cookie。账号只写 `account_id` 或登录名。
- 截图放本目录，文件名用用例 ID。
- 缺陷「严重程度」只写：致命、严重、一般、轻微。「类型」只写：需求、设计、编码、文档、其它。「状态」只写：激活、已解决、关闭。

## 本轮信息

| 项 | 填写 |
| --- | --- |
| 测试人 | |
| 日期 | |
| 版本 | |
| 环境 | |
| 证据 | 本目录 `evidence/` |
| 通过 | 0 |
| 失败 | 0 |
| 阻塞 | 0 |
| 忽略 | 0 |

## 测的时候先记住

- <会改变通过或失败判定的规则。来自套件 README 的「详情」，或用户本轮原话。没有就写「无」。>

## 1. <范围块>

### 1.1 <套件名>

| 用例 | 测试点 | 数据 | 预期要点 | 结果 | 实测记录 |
| --- | --- | --- | --- | --- | --- |
| [<用例ID>](testcase/<模块>/<套件>/<用例ID>.md) | 正向-<title> | <数据> | <预期要点> | | |

## 缺陷

| 编号 | 用例 | 现象 | 严重程度 | 类型 | 状态 | 是否阻塞后续 |
| --- | --- | --- | --- | --- | --- | --- |
| 无 | | | | | | |
```

四个计数加上结果为空的行数（待执行）等于表内行数。新建时四个计数都是 0，所有行的结果为空。

「日期」写起止，例如 `2026-10-21 ~ 2026-10-23`，只测一天写一个日期。「版本」写被测版本号，不知道留空。

缺陷表各列：

| 列 | 写法 |
| --- | --- |
| 编号 | `D1`、`D2` 按出现顺序编，删掉的编号不复用。没有缺陷时只留一行 `无`，其余格子空着 |
| 用例 | 用例 ID。不对应任何一条用例时写 `/` |
| 严重程度 | 致命、严重、一般、轻微。报告里依次是 1 到 4 级 |
| 类型 | 需求、设计、编码、文档、其它 |
| 状态 | 激活：待开发处理。已解决：开发已修复，等回归。关闭：回归通过，或确认不再跟踪 |
| 是否阻塞后续 | 是、否 |

报告里「关闭」算归零，「激活」「已解决」算遗留。用例的首轮结果不另记：出现在缺陷表里的用例，报告按首轮未通过统计；缺陷已解决或关闭后，按它现在的结果统计回归。

## Update

- 回写时改 `testsheet.md` 的结果、实测记录、计数和缺陷。结果只用四个词（通过、失败、阻塞、忽略），没测的留空。
- 步骤级的执行情况（卡在哪一步、为什么、缺什么、证据）写在 `testcase/` 副本对应步骤下，格式见 `docs/spec/testsheet-step-record.md`；
  `testsheet.md` 的「实测记录」只写一句摘要。副本里步骤的「操作」「预期」不因执行记录而改动。
- 增删一行或改了结果后，跑 `uv run tuner-testreport stats assets/testsheet/<轮次> --check`。「共 N 条」和五个计数按它输出的 `rows` 计数改，不手算。它报的取值或缺陷列问题一并改掉。
- 缺陷修好并回归后，不要删缺陷行，把状态改为关闭，用例结果改成回归的结果。
- 从本单移除一条：删表行，删 `testcase/` 里对应副本。开头写明 ID 和原因。菜单权限这类配置问题、以及改由别的页面跟踪的条目，是移除，不记失败，也不进缺陷表。
- 缺陷只记产品行为。
- 本轮步骤缺前置或判定规则：改 `testcase/` 里副本的步骤正文（执行记录之外的部分）。要沉淀回用例库时另走 `maintain-testcases`，改完不要把测试单的链接改回用例库。
- 截图放本目录，文件名用用例 ID。一组结果的图放在对应小节下，写成 `![](文件名.png)`。接口 JSON 放 `evidence/`。造数写 `packages/action_words/db_seed/`，不在 `assets/testsheet/` 里放可执行脚本。

## 归档

是否归档由用户决定，工具不拦截、不自动归档。用户提出要归档某一轮时，LLM 协助：

```bash
uv run tuner-testreport archive <轮次> --check   # 预览：只列 warn，不移动
uv run tuner-testreport archive <轮次>           # 用户确认后：移到 assets/testsheet/archived/<轮次>/，自动写 changelog
```

- `--check` 输出的 `warn archive …`（还有待执行的用例、阻塞用例、`stats --check` 的 error）要原样告诉用户，问一句「仍要归档吗」。用户说归档就归档，不替用户拒绝。
- 归档时 warning 会写进 changelog 的 reason，事后可追溯。

- 归档只是搬目录，内容不改。要对已归档的轮次出报告，把路径写成 `assets/testsheet/archived/<轮次>` 传给 `tuner-testreport stats` / `draft`。
- 缺陷的 `found_in` 仍可写原路径 `assets/testsheet/<轮次>/testsheet.md#D1`，校验会同时认 `archived/` 下的位置。
- 已归档的轮次不再回写；要重测就新开一轮。

## 留痕

组单、增删行、手工回写后各追加一行（逐条执行回写由 `execute-testsheet` 负责并自己写 changelog）：

```bash
uv run tuner-workspace changelog append --area testsheet --skill maintain-testsheet \
  --action <组单|更新|移除> --items <轮次> --reason "<共 N 条 / 改了什么>"
```

## Hard rules

- 不写密码、token、Cookie。
- 不编用例库和套件详情里没有、用户本轮也没说的业务规则。
- 测试单生成后，步骤以副本为准。
