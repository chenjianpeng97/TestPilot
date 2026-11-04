---
name: maintain-testcases
version: 1.6.0
description: Creates and updates functional testcases so each case is its own Markdown file under assets/testcases/<module>/<suite>/<Case-ID>.md, with suite notes in that folder's README. Uses a TestLink-style template (summary, preconditions, numbered steps, expected results, status). One maintain-testcases session is one git commit; the body lists each case as 首次创建 or 变更原因 so the IDE Timeline on that file shows the changelog. Use when the user asks to 编写/生成/维护测试用例, add a module or suite, or mentions assets/testcases or a case ID. Do not use for testdesign click-paths or behave .feature files.
---

# Maintain testcases

## Scope

- **Write**: `assets/testcases/**` only.
- **Must follow**: `docs/spec/testcase-syntax.md`.
- **Out of scope**: `assets/testdesign/`（用 `derive-test-design`）、`tests/features/**`（用 `feature-authoring`）、pytest。

## Before writing

1. 读 `assets/testcases/README.md`、目标模块的 `README.md`、目标套件的 `README.md`（没有就先按下面的模板建）。
2. 读 `INDEX.md`；存在 `INDEX.project.md` 时一并读。只采用已有 usecase / domain-notes / explore / design，或用户本次给出的事实。
3. 套件 README 已有 `id_prefix` 就沿用，不要另起缩写。新建套件时用套件名的英文词，每词首字母大写、`-` 连接（`用户登录` → `User-Login`）。确认这个前缀没有被别的套件占用。
4. 新用例 ID 为 `<id_prefix>-<slug>`，文件名就是 `<用例ID>.md`。`slug` 是测试点的英文短名：小写 kebab-case，2–5 个词，只含 `[a-z0-9]` 与 `-`。从测试点提炼条件，不翻译整段步骤，不加序号，不把正向/反向写进 slug。
5. 查重：`rg -N "^id: User-Login-valid-credentials$" assets/testcases`。完整 ID 全库唯一。已出现过的 slug 不复用（含已从树里删除、仍被报告或 evidence 引用的 ID）。

## Where a case goes

- 已有同名 `<模块>/<套件>/`：只新增或修改其中的 `<用例ID>.md`，并改套件 README 的用例表。不把多条用例写回一个文件。
- 模块已存在、套件没有：新建 `assets/testcases/<模块>/<套件>/README.md` 和用例文件，并在该模块 README 的套件清单加一行。
- 模块也没有：新建模块目录和模块 README，再在总索引的模块表加一行，然后写套件。

套件级说明（数据流、共同前置、本套件特有的边界）不属于任何一条用例时，只写在套件 `README.md` 的 `## 详情`。没有这种说明就不写 `## 详情`。

## Templates

用例文件。空的可选节不要写出。步骤从 1 编号；原来只有一段操作和一段预期时保持一步。

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
source: <依据路径或需求名>
version: 1.0.0
confidence: medium
---

# User-Login-valid-credentials 正确账号密码

## 前置条件

账号已注册。

## 步骤

### 1

- 操作：输入已注册账号与正确密码，点击登录
- 预期：进入首页或个人中心
```

反向用例是另一个文件，例如 `User-Login-wrong-password.md`，`type: 反向`。可选节：`## 摘要`、`## 测试数据`、`## 备注`。不知道重要性就不写 `importance`。`stages` 可选，列表元素只取 `冒烟` 或 `系统测试`，例如 `stages: [冒烟]` 或 `stages: [冒烟, 系统测试]`；不标注就省略。

套件 README：

```markdown
---
kind: testcase-suite
id: user-login
id_prefix: User-Login
title: 用户登录
module: 用户系统
source: <依据路径或需求名>
version: 1.0.0
confidence: medium
---

# 用户登录

## 详情

不属于任何一条用例的说明。没有就不写这一节。

## 用例

| ID | 名称 | 类型 | 状态 |
| --- | --- | --- | --- |
| [User-Login-valid-credentials](User-Login-valid-credentials.md) | 正确账号密码 | 正向 | 就绪 |
```

总索引 `assets/testcases/README.md`：

```markdown
---
kind: testcase-index
title: 测试用例模块索引
version: 1.0.0
confidence: high
---

# 测试用例模块索引

规范：`docs/spec/testcase-syntax.md`。一个套件一个目录，一条用例一个文件。ID 全库唯一。删除一条用例不改其余 ID，不复用 slug。

## 放置规则

- 新用例归入已有模块的套件目录；对不上时才新增模块目录。
- 套件目录名 = 套件标题。用例文件名 = 用例 ID。
- 不写密码、token、Cookie。账号只写 `account_id`。

## 模块

| 模块 | 目录 | 范围 | 状态 |
| --- | --- | --- | --- |
| <模块> | `assets/testcases/<模块>/` | <一句话> | 在用 |
```

模块 README：

```markdown
---
kind: testcase-module
id: <ascii-slug>
title: <模块>
module: <模块>
version: 1.0.0
confidence: high
---

# <模块>

## 范围

## 不测

## 套件

| 套件 | 目录 |
| --- | --- |
| <套件> | [<套件>](<套件>/README.md) |

## 相关知识

无
```

字段和 TestLink 的对应关系见 `docs/spec/testcase-syntax.md`。

## Update rules

- 改操作或预期：保留原 ID，只 bump 该用例文件的 `version`。套件详情或用例表变了，再 bump 套件 README。
- 测试点含义变了才换 slug，新建文件。旧 ID 不复用。在 `## 备注` 写 `曾用：<旧 ID>`。
- 删除：删掉该 `<用例ID>.md`，并从套件用例表去掉这一行。不改其他用例的 ID。
- 废弃：`status` 改为 `废弃`，在备注写原因。不删除文件，不把 ID 让给新用例，标题不加 `（废弃）`。
- 拆套件或改套件名：用例带着原 ID 搬家，并改两边 README 的链接。每条用例的 `suite` 改成新目录名。
- 上面每一种落盘（新建、修改、废弃、删除、搬家）都记在同一次维护的那一个提交里。文件变更日志以 git 为准，不要另写变更日志。

## Commit

同一次 `maintain-testcases` 工作只做 **一个** commit。目的是让每个被改到的用例文件，在 IDE 的 Timeline 里都能看到这次变更日志。用户没有再说「提交」也要做。不要 push。不要改 git config，不要 `--no-verify`。不要按用例拆成多次提交。

校验前的来回修改并进这一个提交。没有文件变化就不提交。

这次提交只暂存本次维护动过的路径：

- 新建或修改的 `<用例ID>.md`（含删除）
- 因此改动的套件 `README.md`、模块 `README.md`、`assets/testcases/README.md`
- 因此在 `INDEX.project.md` 新增或修改的行

工作区里其他改动不要放进来。

提交信息遵循 `docs/spec/commit-convention.md`。`scope` 必须盖住暂存路径：只有 `assets/testcases/**` 时用 `assets`；同一次还改了 `INDEX.project.md` 时用 `assets,index`。subject 概括这一次（套件或模块，加上新建或更新）。全是新建用 `feat`；只改正错误的操作或预期用 `fix`；只做废弃、删除、搬家或索引调整用 `chore`；几种混在一起用 `feat`。

正文每个用例文件一段，打开该文件的 Timeline 时能对上自己的那一段。原词不要改：

- 新文件：`<用例ID>：首次创建。<一句测试点>`。换 slug 的新文件在这句里写 `曾用：<旧 ID>`。
- 已有文件：`<用例ID>：变更原因：<改了什么、为什么>`。
- 只改了套件详情或索引、没有动用例正文：`<套件名>：变更原因：<改了什么、为什么>`。

```bash
git add -- <本次维护相关路径>
git commit -m "<type>(<scope>): <subject>" -m "<用例ID>：首次创建。<测试点>" -m "<用例ID>：变更原因：<改了什么、为什么>"
```

多个用例就多个 `-m`，一段一个文件。只有一条时保留一段即可。

例子：

```text
feat(assets): 新增用户登录用例 2 条

User-Login-valid-credentials：首次创建。已注册账号与正确密码可以登录。

User-Login-wrong-password：首次创建。错误密码不能登录。
```

```text
fix(assets): 更新 User-Login-valid-credentials 正确账号密码

User-Login-valid-credentials：变更原因：登录成功后的预期由首页改为个人中心。
```

提交前看 `git status` 和 `git diff --cached`，确认暂存只有这次维护的文件。`commit-msg` 失败就改正后再提交一次，不要 amend 那次失败的提交。说明里不写密码、token、Cookie。

## Finish

```bash
python -m tuner_testkit.testcases assets/testcases
uv run tuner-workspace meta stamp <改过的.md> --kind <testcase|testcase-suite|testcase-module|testcase-index>
```

校验失败就改文件再跑。本次要写的用例都通过后，按 Commit 做这一个提交，然后停。有 `INDEX.project.md` 时在其知识表登记新套件 README 的路径（只读 front-matter），放进同一次提交；平台仓没有业务用例时不要往根 `INDEX.md` 填模块明细。
