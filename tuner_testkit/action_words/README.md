# packages/action_words

Action Word 是本仓库测试资产的**最小可复用业务动作单元**，统一管理六类工作：
DB 造数（db_seed）、DB 断言（db_assert）、接口请求/编排（api_request）、
接口断言（api_assert）、页面操作/断言（ui_action / ui_assert，预留）。

每个 word 满足三个承诺：

1. **独立可运行**：CLI 一键执行，不依赖任何测试框架；
2. **统一数据契约**：入参/出参均为 pydantic v2 模型，可导出 JSON Schema，
   供未来平台做可视化表单与在线执行；
3. **可精确清理**：造数类 word 把插入的行按表登记进 `Result.cleanup`，
   测试夹具场景后逐表删除。

> 完整规范见 [`docs/spec/action-words-syntax.md`](../../docs/spec/action-words-syntax.md)；
> 用 AI 新增 word 时走 `.cursor/skills/create-action-word` 技能。

> **模板说明**：本仓库只提供框架骨架与空分类目录（`.gitkeep`）。业务 word
> 在各项目仓库的对应子包下落地；旧 `apps/data_factory` 造数工厂已迁移为本包
> 的 `db_seed` 类 action words。

## 目录结构

```
packages/action_words/
├── __init__.py          # 导出 ActionWord / ActionResult / ActionContext / register 等
├── __main__.py          # CLI：list / describe / run / catalog
├── base.py              # ActionCategory / TableRows / ActionResult / ActionWord 基类
├── context.py           # ActionContext：DB 连接 + API token 惰性初始化
├── registry.py          # @register / discover / get / list_all / export_catalog
├── models.py            # 跨 word 共享的业务模型（项目自定义）
├── _internal/           # 内部工具（ids/generators/params/db/api/wait），不对外暴露
├── db_seed/             # 造数类 word（一个模块一组强相关 word）
├── db_assert/           # DB 断言类 word
├── api_request/         # 接口请求/编排类 word
├── api_assert/          # 接口断言类 word
├── ui_action/           # 预留
└── ui_assert/           # 预留
```

`registry.discover()` 自动扫描各类别子包并导入其中全部模块，新增 word
**不需要**手工登记——写好文件、加上 `@register` 即完成注册。

## 使用方法

### 1. CLI 独立执行

```bash
uv run python -m tuner_testkit.action_words list
uv run python -m tuner_testkit.action_words describe <word_id>
uv run python -m tuner_testkit.action_words run <word_id> --example
uv run python -m tuner_testkit.action_words run <word_id> --params "{\"count\": 3}"
uv run python -m tuner_testkit.action_words catalog --out artifacts/catalogs/action_words_catalog.json
```

- `run` 不带 `--params` 时以 `{}` 运行（全部默认值）；
- 输出为 `Result` 的 JSON，其中 `cleanup` 列出本次插入的 `表 → 行 id`；
- 退出码 0/1 对应成功/失败；
- API 类 word 需要登录凭据，解析顺序：`--username/--password` >
  环境变量 `TEST_USERNAME` / `TEST_PASSWORD`（CI 注入）> `data/sut-accounts.local.yaml`；
- 登录 API Object 由 `TEST_LOGIN_API_MODULE` / `TEST_LOGIN_API_ATTR` 配置
  （或向 `ActionContext` 显式传入 `bearer_token`）。

### 2. 打开文件直接改参运行（老 data_factory 习惯）

每个 `db_seed/*.py` 文件末尾应有 `if __name__ == "__main__"` 手工入口：

```bash
uv run python -m tuner_testkit.action_words.db_seed.create_example
```

### 3. 在 behave 步骤中调用

`tests/features/api_environment.py` 的 `before_scenario` 创建共享上下文
`context.actions`，步骤层只做「DataTable / 别名 → word 入参」翻译：

```python
from tuner_testkit.action_words.db_seed.create_example import CreateExample

result = CreateExample(context.actions).run(
    CreateExample.Params(count=1)
)
# 将 result.cleanup 登记到场景清理夹具
```

### 4. 在 pytest 中调用

```python
from tuner_testkit.action_words import ActionContext
from tuner_testkit.action_words.db_seed.create_example import CreateExample

with ActionContext() as ctx:
    result = CreateExample(ctx).run(CreateExample.Params(count=1))
```

## 代码规范（模板契约）

以下约束由 `@register`（导入期）与
`packages/tests/test_action_word_template.py`（回归期）双重强制：

```python
@register
class CreateExample(ActionWord):
    """示例造数动作（占位）。

    <业务含义> + <前置条件> + <副作用（含 cleanup 说明）>，不少于 20 字。
    """

    word_id = "db_seed.create_example"    # 必须 "<category>.<snake_name>"
    name = "示例造数"                       # 中文业务名（平台目录展示）
    category = ActionCategory.DB_SEED
    tags = ("example",)
    requires = frozenset({"db"})
    example_params = {"count": 1}

    class Params(ActionWord.Params):
        count: int = Field(1, description="造数条数")

    class Result(ActionResult):
        ids: list[int] = Field(default_factory=list, description="插入行 id")

    def run(self, params: Params) -> "CreateExample.Result":
        ...
```

## 维护方法

1. **先查重**：`uv run python -m tuner_testkit.action_words list`；
2. 选类别与 `word_id`，在对应类别子包下建模块；
3. 造数类先写纯构建函数再落库；列名以 `knowledge/ddl/<table>.sql` 为准；
4. 验证：

```bash
uv run python -m tuner_testkit.action_words describe <word_id>
uv run pytest packages/tests/test_action_word_template.py -q
uv run python -m tuner_testkit.action_words run <word_id> --example
```

### 共享代码的归属

| 内容 | 位置 |
| --- | --- |
| 业务默认常量（主数据样例） | `_internal/params.py`（项目填充） |
| 随机/派生值生成 | `tuner_testkit.fake`（`_internal/generators.py` 为兼容 re-export） |
| 客户端 bigint id 生成 | `_internal/ids.py` |
| 批量插入 SQL 帮助函数 | `_internal/db.py` |
| APIModel 动态加载 / 登录换 token | `_internal/api.py` |
| 带超时轮询 | `_internal/wait.py` |
| 跨 word 复用的业务模型 | `models.py`（项目填充） |
