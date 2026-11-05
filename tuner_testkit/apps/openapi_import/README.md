# openapi_import — 从 OpenAPI 文档冻结 API Objects

## 需求背景

`packages/api_objects` 以前只能靠抓包冻结（`tuner-recorder`、`tuner-api-recorder`、Playwright MCP）。
被测系统有 OpenAPI / Swagger 文档时，可以先按文档把路由一次性冻结下来，再用抓包补真实样例。
两条通道走同一个冻结内核，同一路由会合并到一个资产里，不会重复。

## 试用场景

- 适用：后端提供 OpenAPI 3.x 或 Swagger 2.0 文档（JSON；YAML 需要本仓装了 PyYAML）。
- 适用：先建立接口资产清单，再挑重点路由抓包补断言。
- 不适用：文档与实现不一致的系统。断言来自文档里的示例或类型推断，执行前仍要用真实请求核对。
- 前置：文档放在 `knowledge/raw/`（原件只读），并登记到 config 的 `KNOWLEDGE.api_docs`（`maintain-config`）。

## 运行方式

在业务仓根目录，用业务仓 `.venv`：

```bash
uv run tuner-openapi-import knowledge/raw/api/openapi.json --dry-run
uv run tuner-openapi-import knowledge/raw/api/openapi.json --path-prefix /api/orders
uv run tuner-openapi-import knowledge/raw/api/openapi.json --tag order --write-mocks --json
```

- 整数路径参数写成 `1`、UUID 参数写成固定 UUID，归一后和抓包一样是 `{id}` / `{uuid}`；其他路径参数保留 `{name}`。
- 文档里声明了 `security` 的接口带一个占位 Bearer 头，冻结时按鉴权接口处理，不写任何真实凭据。
- 写完会在 `packages/api_objects/CHANGELOG.md` 追加一行（`tool=openapi_import`）。

## 运行示例

```bash
uv run tuner-openapi-import knowledge/raw/api/openapi.json --path-prefix /api --json
```

预期产出：`packages/api_objects/<路由>/` 下的 `APIModel` 资产与 `__init__.py` 导出；加 `--write-mocks` 时还有 `data/mocks/<路由>/`。
之后跑 `tuner-workspace index render` 刷新 `INDEX.project.md` 的 API Objects 区。
