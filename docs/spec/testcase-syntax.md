---
name: testcase-syntax
version: 1.5.0
description: assets/testcases 的模块、套件目录、单用例文件，以及和 TestLink 对齐的步骤字段。功能用例集的唯一事实源。
---

# 测试用例（testcase-syntax）

> 一条用例一个 Markdown 文件。一个套件一个目录，不属于任何一条用例的说明写在该目录的 `README.md`。
> 字段对齐 TestLink 的 Test Suite / Test Case：套件详情、摘要、前置条件、分步操作与预期、执行方式、状态。
> 维护流程见 skill `maintain-testcases`。编辑约束见 `.cursor/rules/testcases.mdc`。

## 1. 和相邻知识的分工

| 路径 | 记什么 |
| --- | --- |
| `knowledge/wiki/usecases/` | 导入或讲解过的业务场景，不是带稳定 ID 的用例集 |
| `assets/testdesign/` | 一次任务的范围、策略和点击路径 |
| `assets/testcases/` | 按模块 / 套件维护的用例集。每条用例一个文件、一个稳定 ID |
| `tests/features/` | 已自动化的 Gherkin。本规范不写 `.feature` |

## 2. 目录

```text
assets/testcases/README.md                              # 模块总索引
assets/testcases/<模块>/README.md                       # 模块范围、边界、套件清单
assets/testcases/<模块>/<套件>/README.md                # 套件说明和用例索引
assets/testcases/<模块>/<套件>/<用例ID>.md              # 一条用例
```

例子：`assets/testcases/用户系统/用户登录/User-Login-valid-credentials.md`。

- 模块目录名 = 模块显示名。
- 套件目录名 = 套件显示名 = 套件 README 的 `title` 与一级标题。
- 用例文件名（不含 `.md`）= 该文件 front-matter 的 `id`。
- 只允许这两层：模块下面是套件目录，套件目录里只有 `README.md` 和用例文件。
- 名称不要用 `\ / : * ? " < > |`。

## 3. 套件 README

`kind: testcase-suite`。`id_prefix` 写在这里，之后不得改。同一 `id_prefix` 只能属于一个套件。

```markdown
# 用户登录

## 详情

不属于任何一条用例的说明。没有这种说明就不写这一节。

## 用例

| ID | 名称 | 类型 | 状态 |
| --- | --- | --- | --- |
| [User-Login-valid-credentials](User-Login-valid-credentials.md) | 正确账号密码 | 正向 | 就绪 |
```

一级标题等于套件目录名。用例表的每一行指向同目录下的一个用例文件，不多不少。

## 4. 用例文件

`kind: testcase`。一个文件只有一条用例。

```markdown
---
kind: testcase
id: User-Login-valid-credentials
title: 正确账号密码
suite: 用户登录
module: 用户系统
id_prefix: User-Login
type: 正向
status: 就绪
execution: 手工
stages: [冒烟]
source: knowledge/requirements/REQ-user-login.md
requirements: [REQ-user-login]
data: [account:qa-admin]
version: 1.0.0
confidence: medium
---

# User-Login-valid-credentials 正确账号密码

## 摘要

登录成功后进入已登录页面。

## 前置条件

账号已注册。

## 测试数据

账号 `account_id`。口令不写进本文件。

## 步骤

### 1

- 操作：输入已注册账号与正确密码，点击登录
- 预期：进入首页或个人中心

## 备注

可选。
```

空的可选节不要写出来。节的顺序固定为：摘要、前置条件、测试数据、步骤、备注。

| 节 | 是否必填 | 写什么 |
| --- | --- | --- |
| 摘要 | 否 | 标题里放不下的目的。不要把 `title` 再抄一遍 |
| 前置条件 | 否 | 开测前必须已经成立的状态 |
| 测试数据 | 否 | `account_id` 或数据文件路径。不写密码、token、Cookie |
| 步骤 | 是 | 从 `### 1` 连续编号。每步先 `- 操作：`，再 `- 预期：` |
| 备注 | 否 | 已知限制、曾用 ID、废弃原因 |

原来只有一段操作和一段预期的用例，保持为一步。不要拆成文件里没有写出的多步。

`type` 只取 `正向` 或 `反向`。`status` 只取 `就绪` 或 `废弃`。`execution` 只取 `手工` 或 `自动`，没写自动化的用例用 `手工`。`importance` 可选，只取 `低`、`中`、`高`；不知道就不写。

`stages` 可选，表示这条用例应在哪些测试阶段执行。取值是非空列表，元素只取 `冒烟` 或 `系统测试`，不重复。一条用例可同时属于多个阶段，例如 `stages: [冒烟, 系统测试]`。不知道或不标注就省略该字段。`type` 仍只表示正向/反向，不要把阶段写进 `type`。

`requirements` 可选但推荐：这条用例覆盖的需求 ID 列表（`REQ-<slug>`），文件在 `knowledge/requirements/<REQ-ID>.md`。
需求库存在时 `python -m tuner_testkit.testcases` 校验每个 ID 都有文件；`tuner-workspace doctor` 报告需求覆盖率。
`source` 写最直接的依据（需求文件、wiki 页或原件）。

`data` 可选：用到的测试数据，`data/<path>`（入库的数据文件，必须存在）或 `account:<id>`（`data/sut-accounts.local.yaml` 的账号 id）。
不指向 `.local.` 文件，不写密码。规则见 `docs/spec/data-syntax.md`。

一级标题必须是 `<id> <title>`。`title` 末尾不要加 `（废弃）`。

## 5. 用例 ID

ID 是全库唯一键：`<id_prefix>-<slug>`。

- `id_prefix`：套件名的英文词，每词首字母大写，用 `-` 连接。`用户登录` → `User-Login`。只含字母和连字符，不含数字。
- `slug`：这条用例在验证的条件。英文小写 kebab-case，2–5 个词，每词只含 `[a-z0-9]`。从测试点提炼，不翻译整段步骤，不加序号。正向/反向留在 `type`，不写进 slug。
- 例：`User-Login-valid-credentials`、`User-Login-wrong-password`。不同套件的前缀不同，所以 slug 可以相同。
- 新增前查完整 ID：`rg -N "^id: User-Login-valid-credentials$" assets/testcases`。
- 已发出的 ID 不改、不复用。删除一条用例时删掉该文件，并从其套件 README 的用例表去掉这一行。不改其他 ID。
- 不再新发 `<id_prefix>` 紧接 4 位序号的 ID（如 `User-Login0001`）。
- 测试点含义变了才换 slug，新文件的备注写 `曾用：<旧 ID>`。旧文件删除或标废弃，旧 ID 不复用。
- 废弃：`status` 改为 `废弃`，原因写进备注。保留文件，不把 ID 让给新用例。

`assets/testreport/` 与 `artifacts/evidence/` 里的旧序号是当时的报告键和文件名，不回写。

没有依据的业务规则不要写进操作或预期。依据来自用户说明，或 `INDEX.project.md` 能指向的 `knowledge/requirements/` 需求与 `knowledge/wiki/` 下的 usecase、domain-notes、explore、design。

## 6. 和 TestLink 的对应

| TestLink | 本规范 |
| --- | --- |
| Test Suite | `<套件>/` 目录 |
| Suite details | 套件 README 的 `## 详情` |
| Test Case | `<用例ID>.md` |
| Name | `title` |
| Summary | `## 摘要` |
| Preconditions | `## 前置条件` |
| Step actions | `- 操作：` |
| Expected Results | `- 预期：` |
| Execution Type（Manual / Automated） | `execution`：`手工` / `自动` |
| Importance（Low / Medium / High） | `importance`：`低` / `中` / `高`。不知道省略 |
| Status = Obsolete | `status: 废弃`。在用为 `就绪` |
| （无直接对应；本仓扩展） | `stages`：应执行的测试阶段列表，`冒烟` / `系统测试` |
| 自定义说明 | `## 备注`；账号和夹具写在 `## 测试数据` |

不另造 TestLink 外部编号。`id` 就是稳定键。

## 7. Front-matter

套件 README：

```yaml
---
kind: testcase-suite
id: user-login
id_prefix: User-Login
title: 用户登录
module: 用户系统
sut: <sut 短名，未知可省略>
source: <assets/… 或需求名>
version: 1.0.0
confidence: medium
---
```

用例文件见第 4 节。`suite` 等于套件目录名，`module` 等于模块目录名，`id_prefix` 等于所属套件的 `id_prefix`。

模块 README 用 `kind: testcase-module`。总索引用 `kind: testcase-index`。

人工修改后 bump 被改文件的 `version`。改一条用例的操作或预期时，只 bump 该用例文件。增删用例，或修改套件详情时，bump 套件 README。署名用 `tuner-workspace meta stamp <path> --kind testcase`（套件 README 用 `testcase-suite`，模块 README 用 `testcase-module`，总索引用 `testcase-index`）。

每次维护在 `assets/testcases/CHANGELOG.md` 追加一行（新建、更新、废弃、删除、搬家各写清 `items` 与 `version`）：
`tuner-workspace changelog append --area testcases --skill maintain-testcases --action 更新 --items <用例ID> --version 1.0.0->1.1.0 --reason …`。
pre-commit 的 `tuner-workspace changelog check --staged` 会拒绝没有 changelog 行或没 bump 版本的用例改动。
`CHANGELOG.md` 与 `README.md` 是 `assets/testcases/` 根目录仅允许的两个文件。

## 8. 三份 README

`assets/testcases/README.md` 告诉人和 LLM：模块怎么划分、新套件该进哪个目录、当前有哪些模块。至少包含：

- 放置规则（指向本 spec）
- 模块表：模块名、目录、一句话范围、状态（`在用` / `规划中`）

`assets/testcases/<模块>/README.md` 至少包含：

- 这个模块测什么、不测什么
- 套件清单：每个套件一行，链接到 `<套件>/README.md`
- 相关知识路径（没有就写「无」）

套件 README 的用例表与该目录下的用例文件一致。新增或重命名套件时，模块 README 和总索引一起改。
