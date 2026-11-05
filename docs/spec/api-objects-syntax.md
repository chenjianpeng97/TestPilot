---
name: api-objects-syntax
user-invocable: false
description: API Objects (APIModel) spec for an AI-assisted automation repo. Focus on route-aligned assets, dedupe, sanitization, runtime auth injection, stable asserts/extracts, and versioning.
---

# api-objects-syntax

## 目标与边界

- **目标**：在团队缺少 API 文档习惯的前提下，将从浏览器通道（默认 Playwright MCP）运行过程中捕获到的网络请求/响应沉淀为**可复用、可维护、可审计**的 API 资产（`packages/api_objects/`），供 behave steps **或** 用户明确选择的 pytest 用例调用。
- **第二通道**：被测系统有 OpenAPI / Swagger 文档时（原件放 `knowledge/raw/`，登记在 config `KNOWLEDGE.api_docs`），
  `tuner-openapi-import <spec>` 走同一个冻结内核先建资产，之后抓到的真实流量合并进同一资产（同 method + normalized_path）。
  文档生成的断言来自示例或类型推断，执行前要用真实请求核对。
- **边界**：
  - **API Object = 路由资产**（按后端路由对齐），不是“某个场景的一次回放脚本”。
  - **不得持久化任何敏感凭证**（token/cookie 等）。
  - **behave steps 不允许直接拼 request**；必须调用 API Object。pytest 用例同样应优先调用既有 API Object，而不是手写等价 request。

## 术语

- **API Object / API Asset**：以“后端路由”为单位的接口资产（`method + path` 为核心）。
- **Capture**：一次运行中捕获的请求/响应上下文（来源：Playwright MCP）。
- **Fingerprint**：用于去重/匹配资产的指纹。
- **Invocation**：一次具体调用（由 steps 提供参数/认证注入等运行时信息）。

## 资产对齐原则（按后端路由）

- **唯一对齐**：`method + normalized_path` 决定“落到哪个资产”。
- **禁止**：同一路由为不同场景重复创建多个 API Object（除非重大变更需要升级版本）。

## 目录可见性（workspace catalog）

`tuner-workspace catalog` 用静态扫描（`method = ...` / `path = ...`）列出全部冻结资产，不需要任何装饰器；
`auth.py` / `registry.py` / `recording/` 等辅助模块会被跳过。API Object 在工作台只做只读展示，不从工作台发请求。

## 目录结构与命名规范

> 以“路由树”组织，便于人和 AI 通过路径快速定位。

- **推荐结构**（示例）：
  - `packages/api_objects/example/users/list/GET.v1.py`
  - `packages/api_objects/example/users/list/GET.v2.py`（破坏性变更）
  - `packages/api_objects/example/users/list/__init__.py`（可选，导出别名）

- **文件命名**：
  - `<METHOD>.v<MAJOR>.py`（如 `GET.v1.py`）
  - **仅在破坏性变更**时升级 `MAJOR`（v1 -> v2）

## APIModel 最小字段规范（资产层）

APIModel 的字段被分为三类：**Identity**、**Contract**、**Operations**。

### 1) Identity（必须稳定）

- `id`: string
  - 规则：`<service>.<METHOD>.<normalized_path>@v<MAJOR>`
  - 示例：`example.GET./api/users/list@v1`
- `name`: string（可中文）
- `description`: string（允许 Markdown，建议结构化）
- `method`: string（GET/POST/PUT/DELETE/…）
- `path`: string（只允许 path，不允许写 host）。动态段写成 `{workspace_slug}` /
  `{project_id}` / `{uuid}` 等；调用时用 **`set_path({...})`** 替换（4.3.0）。
  `normalize_path` 只自动识别 uuid 与纯数字，**slug 不会被工具改写**，冻结时请手写占位名。

### 2) Contract（弱 schema 也可，但必须可约束）

- `query_schema`: dict（字段名 -> 类型/是否必填/备注；弱即可）
- `body_schema`: dict（同上；GET 可为空；multipart 下表示**文本**伴生字段）
- `files_schema`: dict（可选；仅 `body_format="multipart"`）：文件字段名 -> `{type:"file", required?, note?}`。**永不**写入文件内容或本地路径。
- `body_format`（可选，默认 `json`）：
  - `json`：请求体以 JSON 发送（`requests` 的 `json=`），与历史行为一致。
  - `form`：请求体以 `application/x-www-form-urlencoded` 发送（`data=`）。调用方仍使用 `set_json({...})` 传入键值，由 `tuner_testkit.api_test` 映射为 form。**适用于**捕获显示为 form 的导出/筛选类 POST（如 DMS 授权结果导出）。
  - `multipart`：文本字段走 `set_json` → `data=`，文件字段走 `set_files` → `files=`。**适用于** Excel 导入等 `Content-Type: multipart/form-data`。不要手动设置 `Content-Type`（由 requests 生成 boundary）。
- `response_hints`: dict（关键字段路径提示，用于断言/提取）
- `headers_policy`: dict（见下）
- `auth_policy`: dict（见下）

### 3) Operations（稳定断言 + 稳定提取）

- `asserts`: list[AssertOperation]
  - 只允许**稳定断言**：HTTP 状态、`$.code`、关键字段存在性
  - 禁止把某条业务数据（如某个 BU 名称）固化为断言
- `extracts`: list[ExtractVariableOperation]
  - 用于为后续 steps 提供变量（token/id/list 等）

## Headers / Auth 的硬约束（必须遵守）

### 禁止持久化（任何情况下不得写入仓库）

- `Authorization`
- `Cookie` / `Set-Cookie`
- `X-Token` / `*token*`（大小写不敏感）
- `*secret*` / `*password*` / `*session*`（大小写不敏感）

### 允许持久化的 header（默认白名单，仍建议最小化）

- `Content-Type`
- `Accept`
- `Content-Language`
- `Accept-Language`
- `X-Request-Id`（如确有需要）

### auth_policy（运行时注入）

API Object 只声明“需要认证”和“认证来自哪里”，不保存凭证：

- `auth_policy.required`: bool
- `auth_policy.strategy`: `bearer_token` | `cookie_session` | `none`
- `auth_policy.source`: `context.token` | `context.session` | `client.default`

## Fingerprint（去重/匹配规则）

用于将 Capture 匹配到已有 API Object。

- **基础指纹**：
  - `fingerprint = method + normalized_path + sorted(query_keys) + sorted(body_keys) [+ sorted(files_keys)]`
  - multipart 时追加 `|files:<sorted file field names>`
  - `normalized_path` 要做基础归一（避免同一路由因动态段裂变）：
  - 连续数字段（如 `/users/123`）可归一为 `/users/{id}`
  - UUID 段归一为 `{uuid}`
  - 归一规则由框架固定，AI 不得自行更改

## 参数设置与覆写（Invocation 规则）

steps 调用 APIModel 时允许在运行时调整参数，但必须通过 APIModel 的链式调用表达，并遵守 schema/allowlist 约束。

### 1) set\_\*（merge-set，小改动：单值覆盖 + 可选补字段）

- `set_query({...})`：对 query 做浅合并；同名 key 覆盖；若 schema 中缺失字段，允许将该字段补齐进 `query_schema`（默认可选）。
- `set_json({...})`：对 json/form/multipart **文本** body 做浅合并；同名 key 覆盖；若 schema 中缺失字段，允许将该字段补齐进 `body_schema`（默认可选）。
- `set_files({...})`：仅 `body_format="multipart"`；对文件字段浅合并；值可为路径 / `(filename, bytes|path, content_type?)` / `{filename, content|path, content_type?}`。资产内禁止写真实路径或 bytes。
- `set_headers({...})`：对 headers 做浅合并；仅允许 allowlist keys。

适用：分页参数（pageNum/pageSize）、查询条件的临时覆盖（例如从“小明”改查“小红”）、Excel 导入时注入本地样例文件。

### 2) override\_\*（override-rebuild，大改动：整段重构）

- `override_query({...})`：整段替换 query
- `override_json({...})`：整段替换 json body
- `override_files({...})`：整段替换 multipart 文件映射（仍要求 `body_format="multipart"`）
- `override_headers({...})`：整段替换 headers（仍需过滤 forbidden keys）

适用：接口被大量复用但 payload 结构整体变更，需要在特定调用点手动重构请求体。

## 断言与提取的分层（防止模型被场景绑死）

### 允许放在 API Object 的（稳定）

- `http_status == 200`
- `$.code == 200`（**仅当**响应体为 JSON 且存在 `code` 字段时）
- `$.data exists` / `$.data is list`（**仅当**响应为 JSON 时）

### 非 JSON 响应（文件下载、二进制流）

- 当响应为 **xlsx / 二进制** 时，`json` 解析通常失败，**`execute()` 仍返回** `ApiResponse`，其中：
  - `json` 可能为 `None`
  - **`content: bytes` 恒为原始响应体**（由 `ApiClient` 从 `requests.Response.content` 填充）
- **资产内断言**：优先只断言 **`$.http_status == 200`**（评估对象在无非 dict JSON 时为 `{http_status, body}` 形态，见 `tuner_testkit.api_test.model`）。**不要**在资产中断言响应体长度、Content-Type 具体值、或文件名（易随网关变化）。
- **提取字段**：不要对二进制体写 `jsonpath: $.data.rows` 类 extracts。应在 **steps** 或 **`tuner_testkit.excel`** 中读取 `resp.content` 并解析。`tuner_testkit.excel` 为**无业务**的表读取（`ExcelWorkbook.from_bytes` / `first_sheet_rows` 等），列到领域模型的映射由调用方完成。

### 不允许放在 API Object 的（场景相关）

- `$.data[0].categoryName == "介入东部,T-LAB百院千万"`
- 任何依赖当前用例输入的特定值断言

场景相关断言应该放在：

- steps 的断言步骤，或
- 调用层的专用断言 operation（不写回资产）

## 版本策略（v1 / v2）

### 何时升级 v2（破坏性变更）

- path 或 method 变化
- response 关键字段语义变化导致既有 steps 不能兼容
- 必填参数变化导致既有调用不兼容

### 何时只更新 v1（兼容性补全）

- 新增可选字段到 schema
- 新增稳定断言/提取（不改变既有行为）
- headers_policy 更收敛（更安全）

## 示例模板（Python 风格，供 AI 生成时遵循）

> 注意：示例中不包含真实 token/cookie。

```python
from tuner_testkit.api_test.model import APIModel, AssertOperation, ExtractVariableOperation

get_category_tree_v1 = APIModel(
    id="example.GET./api/users/list@v1",
    name="获取用户可授权产品",
    description="""
inputs:
  - query.categoryName: 来自上游业务变量（由 steps 传入）
outputs:
  - data: $.data
notes:
  - 资产按路由对齐；认证由运行时注入，不在此处固化
""".strip(),
    method="GET",
    path="/api/users/list",
    query_schema={
        "categoryName": {"type": "string", "required": False, "note": "按名称过滤"},
    },
    headers_policy={
        "allowlist": ["Accept", "Content-Language", "Accept-Language", "Content-Type"],
        "forbidden": ["Authorization", "Cookie", "Set-Cookie"],
    },
    auth_policy={
        "required": True,
        "strategy": "bearer_token",
        "source": "context.token",
    },
    asserts=[
        AssertOperation(name="http status", jsonpath="$.http_status", operator="eq", expected=200),
        AssertOperation(name="业务码", jsonpath="$.code", operator="eq", expected=200),
        AssertOperation(name="data存在", jsonpath="$.data", operator="exists", expected=True),
    ],
    extracts=[
        ExtractVariableOperation(name="提取data", jsonpath="$.data", variable_name="data"),
    ],
)
```

## Steps 调用规范（必须通过 API Object）

```python
resp = (
    get_category_tree_v1
    .set_query({"categoryName": subbu})
    .execute(auth={"bearer_token": token})  # 运行时注入
)
```

## 审计清单（Reviewer/Subagent 必查）

- 是否存在任何敏感 header/value 被写入仓库
- 是否把 host 写入 path/url
- 是否按 fingerprint 复用已有资产，而非重复创建
- asserts 是否只包含稳定断言（无业务常量）
- 提取变量是否命名清晰、不会污染全局上下文
