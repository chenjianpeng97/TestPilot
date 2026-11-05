---
name: maintain-defectlib
version: 2.0.0
group: knowledge
description: Records and maintains defects in the repo defect library knowledge/defects/DEF-<yyyymmdd>-<nnn>.md with a fixed template (python -m tuner_testkit.defects new / check) - from a testsheet defect table or from a tester's description - and updates the same file across rounds (已解决, 关闭, 重开) with a history row and version bump. Use when the user says maintain-defectlib, 记录缺陷, 提缺陷, 缺陷库, 沉淀缺陷, 缺陷回归, 关闭缺陷, or after execute-testsheet recorded defects.
---

# maintain-defectlib — 记录缺陷

缺陷和用例一样：固定目录、固定模板、确定性校验。仓库里的缺陷库就是缺陷的记录处。规范见 `docs/spec/defect-syntax.md`。

## Scope

- **写**：`knowledge/defects/<DEF-ID>.md`、`knowledge/defects/CHANGELOG.md`；记录自测试单时，在该测试单缺陷表对应行的「现象」末尾补 `（DEF-…）`。
- **读**：测试单（`assets/testsheet/<轮次>/testsheet.md` 的「缺陷」表与「本轮信息」）、用例副本（取 `requirements`）、已有 `knowledge/defects/`、证据路径。
- **不写**：测试单的结果与计数（`execute-testsheet` / `maintain-testsheet` 负责）、用例库。

## 1. 收集

两种来源，一次可以混着处理：

- **来自测试单**：用户点名的轮次（没点名就是最近修改的测试单），读缺陷表每一行 `D<n>`：用例、现象、严重程度、类型、状态、是否阻塞后续。「无」行跳过。
- **来自描述**：测试人口述或探索中发现、线上反馈。按模板逐项问清：现象、复现步骤、预期结果、实际结果、严重程度、类型、是否阻塞、对应用例（没有写 `/`）、环境与版本。
  用户没说的不要编；严重程度和类型拿不准时问。

## 2. 先找已有缺陷，避免重复

在 `knowledge/defects/` 里按顺序找同一个缺陷：

1. 某文件的 `found_in` 等于本行 `assets/testsheet/<轮次>/testsheet.md#D<n>` → 就是它。
2. 同一 `testcase` 且现象描述同一产品行为 → 很可能同一个，**问用户确认**后合并。
3. 都不是 → 新缺陷。

## 3. 新缺陷：按模板建文件

```bash
uv run python -m tuner_testkit.defects new --title "<一句话，不含编号>" --severity <致命|严重|一般|轻微> --type <需求|设计|编码|文档|其它> \
  [--blocking] [--date <发现日期>] [--found-in "assets/testsheet/<轮次>/testsheet.md#D<n>"] [--round <轮次>] \
  [--testcase <用例ID>] [--requirements REQ-a,REQ-b] [--sut-version <版本>] [--env <环境>]
```

- 它取下一个编号、写好 front-matter、一级标题、章节骨架和第一行历史，正文是 `（待填）`。
- 打开生成的文件，把每个 `（待填）` 换成事实：现象一句话；复现步骤写成 `1. 2. 3.`（来自用例副本步骤或用户描述，不抄密码，账号写 `account:<id>`）；预期结果；实际结果。
  有截图、日志、接口响应时在「证据」列路径；没有就删掉「证据」整节。环境、前置条件有内容才写，没有就不写这两节。
- `requirements` 取对应用例副本 front-matter 的 `requirements`；没有就省略。
- 来自测试单时，回到测试单缺陷表那一行，在「现象」末尾补 `（DEF-…）`。

## 4. 已有缺陷：更新同一个文件

- 状态变化（激活 → 已解决 → 关闭；回归失败重开为激活）：改 `status`，在「历史」表追加一行 `| 日期 | 轮次 | 状态 | 说明 |`，bump `version`。
- 新轮次复现：历史追加一行说明复现情况；补充新的证据路径；必要时更新实际结果。
- 误报：`status: 关闭`，历史写明原因。不删文件，不复用编号。

## 5. 校验与留痕

```bash
uv run python -m tuner_testkit.defects check
uv run tuner-workspace changelog append --area defects --skill maintain-defectlib \
  --action <新建|更新|关闭|重开> --items DEF-20261104-001[,DEF-…] --version <1.0.0 或 旧->新> --reason "<轮次 D1 / 回归结论>"
uv run tuner-workspace index render
```

`check` 有错就改到没有。一次维护一个提交，scope `knowledge`（测试单也改了就加 `assets`），
例 `feat(knowledge,assets): record defects from 261104订单`。

## Hard rules

- 缺陷只记产品行为；配置、权限菜单之类从测试单移除的条目不进缺陷库（和测试单规则一致）。
- 严重程度、类型、状态只用规定的取值；拿不准时照抄测试单或问用户，不按现象猜。
- 不写密码、token、Cookie；证据只写路径，不贴响应原文。
- 缺陷只记在 `knowledge/defects/`，不留在聊天里，不另起表格。
