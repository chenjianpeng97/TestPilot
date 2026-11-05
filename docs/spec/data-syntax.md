---
name: data-syntax
version: 1.0.0
description: data/ 数据层：可复用测试数据、带角色与权限的账号、mock 样例；与用例的双向关联。
---

# 数据层规范（data-syntax）

> `data/` 装可复用的测试数据。账号、造数用的实体数据、mock 样例都在这里；
> 地址与密钥属于 config（`docs/spec/config-syntax.md`）。

## 1. 目录

```text
data/
├── sut-accounts.example.yaml   # 账号模板（入库）
├── sut-accounts.local.yaml     # 真实账号（gitignore）
├── <domain>/<name>.yaml|json|csv  # 可复用的测试数据（入库，不含密钥）
└── mocks/<路由>/…              # mock 样例（tuner-recorder --write-mocks / tuner-openapi-import --write-mocks）
```

`data/**/*.local.{yaml,json,md}` 一律 gitignore，catalog 与工作台不列出。

## 2. 账号

```yaml
sut: acme
ui_base_url: https://uat.acme.example
api_base_url: https://uat-api.acme.example
accounts:
  - id: qa-admin                 # 任务、提问、用例、changelog 里只用 id 指代账号
    role: admin                  # 被测系统里的角色名
    permissions: ["user:manage", "order:approve"]
    email: qa@acme.example       # 登录名；也可写 username
    password: "…"
    notes: 首次登录要改密码
```

- `role` / `permissions` 与被测系统的角色权限表对应。权限表本身是知识，写在 `knowledge/wiki/domain-notes/<sut>/roles.md`。
- 权限类用例按 `role` 挑账号；反向用例用缺少某权限的账号。
- 账号的**唯一来源**是本文件，config 里没有账号字段。代码取账号用 `tuner_testkit.accounts.resolve_account()`：
  默认第一个账号，`TUNER_ACCOUNT=<id>` 或 `role=` 指定其他；`TEST_USERNAME` / `TEST_PASSWORD` 环境变量仅作 CI 注入覆盖，不是账号存放处。
- `tuner-workspace doctor` 的 `data.accounts` 检查账号文件存在、无 `replace-me` 占位、每个账号都有 `role`。

## 3. 测试数据与用例双向关联

- 用例 front-matter 的 `data:` 列出它用到的数据：`data/<path>` 或 `account:<id>`。`tuner_testkit.testcases` 校验路径存在、不指向 `.local.` 文件。
- 数据文件头（YAML 注释或 JSON `_meta`）可写 `used_by: [<用例ID>]`，便于反查。`maintain-testcases` 新增引用时同步补上。
- 特定实体（社信码、UDI、手机号、单据号）优先用 `tuner_testkit.fake` 生成，规则来自 `knowledge/wiki` 的实体说明；
  固定样例才落 `data/`。

## 4. 禁止

- 在 `data/*.yaml`（非 `.local.`）里写真实密码、令牌、个人敏感信息。
- 在用例、测试单里写账号密码：只写 `account:<id>`。
