---
name: bdd-run-gherkin-in-playwrightMCP
user-invocable: false
description: Spec for running Gherkin scenarios (or explore sessions) via Playwright MCP, capturing network context to artifacts/evidence, and freezing it into route-aligned API Objects safely (sanitize, dedupe, versioning). Design/DB effects live in docs/spec/design-knowledge-syntax.md.
---

# behave-run-gherkin-in-playwrightMCP

## 适用范围

- 本规范服务于 **浏览器通道 → 持久 evidence → API Object freeze** 路径。浏览器通道由 config
  `CHANNELS.browser` 选择（默认 `playwright-mcp`，也可 `cursor-browser`），工具映射与证据落盘见
  `docs/spec/browser-channel.md`；下文写「Playwright MCP」处按所选通道替换工具名。
- 既覆盖「已有 `.feature` 的 Run→Capture」，也覆盖
  **explore-first**（尚无 `.feature`）的同等落盘。总流程见
  `docs/spec/sut-self-learning.md`。
- API↔DB 副作用、`writes` / `correlate` / `noise` 不在本文件展开，见
  `docs/spec/design-knowledge-syntax.md`。
- 当用户**明确要求用 pytest** 且无需从 MCP 抓网沉淀时，**不要**强制走本流程。

## 目标

- 让 AI 能通过 Playwright MCP 执行场景或探索会话，并将过程中的网络请求/响应、
  DOM 快照、操作序列**脱敏后持久化**到 `artifacts/evidence/<run_id>/`，
  进而稳定生成/更新 `packages/api_objects/`、`packages/page_objects/`、
  `knowledge/wiki/design/`。
- **必须落盘**：不接受「只在 LLM 上下文里留一份摘要」。没有带时间戳的
  持久 trace，就无法做 API 与 DB 写入的时间窗关联。

## 总体流程（Run → Capture → Freeze）

```text
feature/scenario  或  explore session
  ↓
Playwright MCP 运行（UI 操作 + 断言 / 探索）
  ↓
落盘 artifacts/evidence/<run_id>/（脱敏）
  ↓
Fingerprint 匹配已有 api_objects
  ↓
生成/更新 APIModel（只补稳定契约、稳定断言、稳定提取）
  ↓
（可选）结合 DDL / 源码 / 日志 → knowledge/wiki/design/**
```

## Evidence 落盘（强制）

每次 MCP 运行必须创建：

```text
artifacts/evidence/<run_id>/
├── run_summary.md          # 必填：场景/会话、通过失败、路由列表、脱敏声明
├── network.jsonl           # 必填：每行一条脱敏 Capture（见下节最小字段）
├── actions.jsonl           # 建议：MCP 动作序列（click/fill/navigate）
└── snapshots/              # 可选：关键页 accessibility snapshot
```

`run_id` 建议 `YYYYMMDDTHHMMSSZ-<short>`，只含 ASCII。

## Capture 规范（结构化输出）

### 1) Capture 最小字段

- `scenario_id`: string（feature 路径，或 `explore:<intent>`）
- `run_id`: string
- `timestamp`: ISO string
- `request`:
  - `method`
  - `url`（完整 url，仅用于解析；落盘时拆出 host/path/query）
  - `host`
  - `path`
  - `query`: dict（已脱敏）
  - `headers`: dict（已脱敏，且过滤 forbidden keys）
  - `body`: object|string|null（已脱敏）
- `response`:
  - `status`
  - `headers`（脱敏）
  - `body_sample`（脱敏；允许截断）
- `timing`（可选）

### 2) 脱敏（Sanitize）硬规则

#### 禁止落盘的 header key（大小写不敏感）

- `Authorization`
- `Cookie` / `Set-Cookie`
- `X-Token` / `*token*`
- `*secret*` / `*password*` / `*session*`

#### 值脱敏（适用于 query/body/response_sample）

- 长 token/疑似 JWT：只保留前后各 4-6 位，中间掩码
- 手机/邮箱/证件：按规则掩码（保留可定位的部分）
- 任何可能的私钥/签名：全部替换为 `***`

> 规则目的：即使 evidence 被误提交仓库，也不会泄露凭证。

## 从 Capture 冻结为 API Object（Freeze to Asset）

### 1) 归一化（Normalization）

从 Capture 计算：

- `method`
- `normalized_path`（动态段归一：数字/uuid 等）
- `query_keys`（只取 key）
- `body_keys`（只取 key；json body 才可取）
- `content_type`

### 2) 指纹（Fingerprint）

- `fingerprint = method + normalized_path + sorted(query_keys) + sorted(body_keys)`

### 3) 匹配策略

- **命中**：更新既有 APIModel（v1 内兼容补全）
- **未命中**：创建新 APIModel（`v1`）

## APIModel 运行时调用约定（set/override/execute）

- 小改动：`model.set_query(...)` / `model.set_json(...)`
- 大改动：`model.override_json(...)`

### 4) 版本策略（何时 v2）

触发 v2 的典型信号：

- 同 fingerprint 的响应结构发生不兼容变化（关键字段缺失/改名）
- 必填参数发生变化导致既有 steps 不兼容

除非明确不兼容，不自动升 v2；只输出「建议升 v2」的评审意见。

## 冻结时的「禁止/必须」列表

### 禁止

- 在 `packages/api_objects/` 中写入任何真实 token/cookie
- 把 host 写入 APIModel 的 `path/url`
- 把 Referer/User-Agent 这类噪声 header 当成契约固化
- 把场景常量断言写入 APIModel（例如某个 BU 名称）

### 必须

- 新建前必须做 fingerprint 匹配，避免重复资产
- APIModel 必须声明 `auth_policy` 与 `headers_policy`
- asserts/extracts 必须按「稳定/场景」分层
- 资产注释或 CHANGELOG 引用 `run_id`

## 冲突与重复资产处理

当发现重复 APIModel（同 method/path，但 query/body keys 不同）：

- **优先合并**到同一资产（v1）：将字段标记为可选
- 无法兼容时：输出「建议升 v2 / 拆分为 v2」；不自动重构旧资产

## 失败分类（用于后续 triage）

- **UI 失败**：元素不可见/定位不稳定/页面跳转异常
- **API 失败**：HTTP 非 2xx、业务码非 200、返回缺字段
- **环境失败**：域名不可达、证书/代理、登录态失效
- **脚本失败**：步骤定义缺失、参数绑定错误
