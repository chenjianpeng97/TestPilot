# dashboard

离线统计工作台看板要的数字，写两份结果；`tuner-workbench` 首页只读结果，不在请求里扫文件。

## 需求背景

早期看板在每次打开页面时汇总文件系统（`build_catalog` 全量扫描，再逐个文件 `git log`），
资产一多首页就要等好几秒。现在把统计挪到这个 app，由 skill `refresh-dashboard` 手动触发，
统计和看板展示之间异步解耦。

## 试用场景

- 想知道这个仓现在有多少用例、测试单、API / 页面对象、动作词、BDD 场景、pytest 用例、工具。
- 刷新工作台首页的看板（自检、环境配置概览、逐轮测试单进度）。
- **不做**：不改任何资产；不连数据库（doctor 段跳过 `db.*` 连通检查）；不导入 workspace 的
  `apps/` 或动作词（工具和动作词都用 AST 静态解析）；不跑 `git log`。

## 运行方式

无 extra。

```bash
uv run tuner-dashboard refresh                # 统计并写两份结果
uv run tuner-dashboard refresh --no-doctor    # 跳过 doctor 自检段
uv run tuner-dashboard refresh --out-dir /tmp/dash   # 实测用：两份结果都写到别处，不动仓库
uv run tuner-dashboard status                 # 只读已有结果，不统计
```

两份结果：

| 文件 | 入库 | 内容 |
| --- | --- | --- |
| `DASHBOARD.md` | 是 | front-matter 平铺计数加三张表（测试资产、自动化覆盖、工具）。计数和 kit 版本都没变就不重写，`updated` 是计数最后一次变化的时间 |
| `artifacts/catalogs/dashboard.json` | 否 | 全部段：assets、automation、tools、doctor、config，加 `checked_at` 与各段 `timings`（毫秒） |

统计口径：

- 测试用例：`assets/testcases/**/*.md`，除 `README.md`、`CHANGELOG.md`。
- 测试单：`assets/testsheet/<轮次>/testsheet.md`；`archived/`、`_archive/` 下的算已归档；进行中的轮次用 `tuner-testreport` 的统计逐轮算进度。
- API 对象、页面对象、BDD：同 `tuner_testkit.catalog.scan`。
- 动作词：`packages/action_words/<类别>/*.py` 里带 `@register` 的类；db_seed 是其中 `db_seed` 类别。
- pytest：`tests/pytest/**/test_*.py`（或 `*_test.py`）里的 `def test_` 个数。
- 工具：kit 的 `tuner-*` 命令（安装元数据）；workspace `apps/<名>/tool.py` 里的 `tool(...)`，以及没有 `tool.py` 的 app 目录。
- 环境配置：`tuner_testkit.config.describe_environments()`，按白名单只取 URL 与数据源的类型、host、端口、库名，其余段只给条目数；密码、令牌、账号一律不读。

任何一段失败只在该段写 `error`，其它段照常；失败段的计数沿用 `DASHBOARD.md` 里的旧值。

## 运行示例

```text
$ uv run tuner-dashboard refresh
{
  "changed": true,
  "markdown": ".../DASHBOARD.md",
  "json": ".../artifacts/catalogs/dashboard.json",
  "updated": "2026-11-08T14:35:13+08:00",
  "counts": {"testcases": 816, "testsheets_active": 2, "api_objects": 115, ...},
  "delta": {"testcases": "810 -> 816"},
  "errors": {},
  "timings": {"assets": 242, "automation": 140, "tools": 5, "doctor": 288, "config": 0, "total": 685},
  "doctor": {"ok": true, "not_ok": [{"id": "ports.log-source", "status": "missing", "fix": "..."}]}
}
```
