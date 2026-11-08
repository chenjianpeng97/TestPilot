# TestPilot（tuner-testkit）

**TestPilot** 是一个测试助手：用一个 Git 仓库加一套 rule / skill / agent / hook，约束读这个仓库的 AI 怎么工作，
同时让测试工程师把知识、用例、测试单、报告、自动化资产、工具都存进同一个仓库维护。

运行库与 CLI 以 PyPI 包发布：发行名 **`tuner-testkit`**，导入名 **`tuner_testkit`**，命令 `tuner-*`。它提供公共运行库
（db / API / Web UI / 录制 / mock）以及 Cursor/git **DNA**（rules、skills、hooks、specs）。

业务数据（`knowledge/` 被测系统知识、`assets/` + `packages/` 测试资产、`apps/` 自定义工具、`tests/`）留在**各项目仓**，不进本包。
平台发新版本后，下游用 `uv` 升级并 `tuner-dna sync --prune`，不必整树拷贝运行库。

打开新仓后让 AI 先跑 skill **`health-check`**（体检与开场配置）。对外入口分三组：
知识（`maintain-wiki`、`dump-ddl`、`maintain-defectlib`）、动作（`maintain-testcases`、`maintain-testsheet`、`execute-testsheet`、
`generate-test-report`、`maintain-bdd-assets`、`maintain-pytest`）、可用性（`health-check`、`upgrade-framework`、`maintain-config`、`create-app`）。

---

## 标准作业流程

### 1. 工具域：只装核心 kit（能 `tuner-init` 即可）

`uv tool install` 和业务仓 `.venv` 是两套环境。下游在 **tool 域只装默认 wheel**，用来拿 `tuner-init` / `tuner-dna`；**不要**在 tool 域打开 `[db]` / `[api]` 等 extra。

```bash
uv tool install tuner-testkit
```

入口命令是 `tuner-init`、`tuner-dna` 等（`tuner-*`），**没有** `tuner-testkit` 这个 script。`tuner-dump-ddl`、`tuner-recorder` 等依赖 extra 的 CLI，请在业务仓用 `uv run …` 跑，走该仓 `.venv`。

### 2. 初始化测试仓

```bash
tuner-init scaffold ../acme
cd ../acme
uv sync
```

`scaffold` 会铺分层目录（`knowledge/`、`assets/`、`packages/`、`apps/`、`data/`、`tests/`、`config/`、`work/tasks/`、`artifacts/`）、写入依赖 `tuner-testkit[db,api]>=<当前 kit 版本>` 的 `pyproject.toml`，并执行一次 `tuner-dna sync`（把 `.cursor/`、`docs/spec/`、`tools/git-hooks/`、`AGENTS.md` 放进**项目树**；平台专属内容不下发）。可在任意目录运行，不必先有测试仓。不要用 `tuner-testkit init repo`。

scaffold 之后让 AI 跑 `health-check`（底层是 `tuner-workspace doctor`），它会列出还缺的配置、账号、表结构、浏览器通道、日志端口等，并逐项补齐。

生成的文件夹名就是 `target` 路径的最后一段。`pyproject.toml` 里的项目名默认取这个文件夹名（`Acme` 会写成 `acme`）。需要另起项目名时加 `--name`：

```bash
tuner-init scaffold ../clients/acme --name acme-billing
```

`uv sync` 把 **db / api 装进业务仓 `.venv`**，不是 tool 域。已有项目仓则在该仓根目录：

```bash
uv add "tuner-testkit[db,api]>=4.0.0"
uv sync
```

Web UI / 合录等按需再加 extra：

```bash
uv add "tuner-testkit[web-ui]"
uv add "tuner-testkit[recorder]"
```

测 kit 全能力（平台狗食仓等）一次打开全部能力 extra：

```bash
uv add "tuner-testkit[all]"
uv sync
```

### 3. 开始写业务

在**项目仓**里写，不要改 site-packages 里的 kit：

| 你写什么 | 放哪里 |
| --- | --- |
| 被测系统知识（DDL、需求、业务讲解、探索、design、缺陷） | `knowledge/`（`ddl/`、`raw/`、`wiki/`、`requirements/`、`defects/`） |
| 测试设计、功能用例、测试单、报告 | `assets/`（`testdesign/`、`testcases/`、`testsheet/`、`testreport/`） |
| 页面 / 接口资产 | `packages/page_objects/`、`packages/api_objects/`（有 OpenAPI 时 `tuner-openapi-import`） |
| 业务动作 | `packages/action_words/` |
| BDD / pytest | `tests/features/`、`tests/pytest/` |
| 本仓私有工具、端口适配器（如后端日志） | `apps/`（`python -m apps.<name>`） |
| 测试数据、账号（角色、权限） | `data/` |
| 「在哪、用什么」：环境、运维通道、端口绑定、浏览器通道、知识位置 | `config/`（`tuner-config show --json` / `validate`） |

代码里 `from tuner_testkit.db import …` / `from tuner_testkit.page_test import …`。密钥只放本机 `config/env_local.py` 或环境变量（`TUNER_ENV`、`TUNER_DB_<ALIAS>_*`），**不要提交**。

后端日志这类取数方式各团队不同的能力，kit 只定**端口契约**（`docs/spec/ports.md`），实现是本仓 `apps/` 里的自定义工具。
缺陷和用例一样有固定目录与模板：`knowledge/defects/<DEF-ID>.md`（`docs/spec/defect-syntax.md`，skill `maintain-defectlib`）。
维护过的库（用例、需求、缺陷、wiki、接口与页面资产）各有一份入库的 `CHANGELOG.md`，`pre-commit` 会检查。

录制产物同样写到项目仓 `packages/`，不会写进 venv。

### 4. 获取 PyPI 上的更新

平台发新版本后，下游从 [PyPI：tuner-testkit](https://pypi.org/project/tuner-testkit/) 取 wheel，**不要**再拷本仓源码。tool 域和业务仓 `.venv` 是两份安装，**两边都要升**，再铺 DNA。

**先看当前装的是哪一版、PyPI 最新是哪一版：**

```bash
uv tool list                          # tool 域里的 tuner-testkit
cd ../my-sut-tests
uv pip show tuner-testkit             # 业务仓 .venv
```

发行说明见 [`docs/changelog/FRAMEWORK.md`](docs/changelog/FRAMEWORK.md) 与该版本的 `docs/changelog/TEMPLATE-*.md`。

**① tool 域（只升核心 CLI）**

```bash
uv tool upgrade tuner-testkit
```

升的是 `tuner-init` / `tuner-dna` 所在环境。这里仍然**不要**加 `[db]` / `[api]`。尚未 `uv tool install` 过则先执行第 1 节。

**② 业务仓 `.venv`（升运行库 + extras）**

在**项目仓根目录**改依赖并同步 lock。保留你原来打开的 extra（普通仓 `[db,api]`，狗食/全能力仓 `[all]`）：

```bash
# 钉到某一发行版（推荐，和团队 lock 一致）
uv add "tuner-testkit[db,api]==4.3.0"

# 或只抬下限，让解析器选允许范围内的最新
# uv add "tuner-testkit[db,api]>=4.3.0"

uv sync
```

已经写过 `>=4.0.0`、只想把 lock 里的 kit 升到 PyPI 最新：

```bash
uv lock --upgrade-package tuner-testkit
uv sync
```

只改 `pyproject.toml` 里的版本再 `uv lock` / `uv sync` 也可以。一个 wheel 不能「只升 web-ui、钉死旧 db」。

**③ 同步 DNA、按说明迁移、提交**

`uv add` / `uv sync` 只更新 site-packages 里的运行库。Cursor 读的是项目树里的 `.cursor/`、`docs/spec/`、`docs/changelog/TEMPLATE-*.md`、`tools/git-hooks/`、`AGENTS.md`，必须再铺一层：

```bash
tuner-dna sync --prune      # 没被本地改过的文件自动更新；上游删掉的文件一并删除
tuner-dna check             # 本地改过的文件会列为 edited
```

`tuner-dna sync` 在项目根写 `.tuner-dna.json`（每个文件的哈希，入库），据此区分「没动过、可以直接更新」和「本地改过」。
本地改过的 DNA 文件默认保留；把定制移到 `.cursor/rules/<名字>.local.mdc` 或 `AGENTS.local.md`（sync 永不触碰）后再加 `--overwrite`。
然后读 `docs/changelog/TEMPLATE-<版本>.md` 做布局或配置迁移（例如 7.0.0 的 `tuner-workspace migrate knowledge`），最后一次提交。
这一整套可以交给 skill **`upgrade-framework`**。

`tuner-dna check` 核对项目树 DNA 是否与**当前 PATH 上那份** kit 一致。建议先 `uv tool upgrade`，再 `sync`，避免 CLI 还是旧包、`.venv` 已是新包。

**其他 AI IDE**：DNA 以 Cursor 布局为源，`tuner-dna sync --ide claude,agents`（或 `all`）把 skills 渲染到
`.claude/skills/` / `.agents/skills/`、subagents 到 `.claude/agents/`，并生成 `CLAUDE.md`（`@AGENTS.md` + always-on 规则内联 + 路径规则清单）。
`tuner-dna targets` 列出各目标落点；hooks.json 不跨工具翻译。目录约定随各工具文档变动，用前核对。

新仓第一次仍用第 2 节的 `tuner-init scaffold`（会写依赖并做一次 `tuner-dna sync`），不是每次发版都重新 scaffold。

`[phone-ui]` 为预留空 extra，4.0 未实现。

---

## extras

| extra | 内容 |
| --- | --- |
| （默认 wheel） | `config` / `logging`、`tuner-init`、`tuner-dna`（tool 域只装这个） |
| `[db]` | MySQL / SQL Server / PostgreSQL（装在业务仓 `.venv`） |
| `[api]` | `api_test`（HTTP 客户端） |
| `[web-ui]` | `page_test` + Playwright |
| `[phone-ui]` | 预留，无实现 |
| `[recorder]` | 合录 / 仅 UI / mitmproxy 代理 |
| `[mock]` | 按冻结的 api_objects 回放 |
| `[excel]` / `[fake]` | 表格 / 假数据 |
| `[report]` | `tuner-testreport render`：测试单报告出 docx（docxtpl） |
| `[bdd]` / `[test]` | behave / pytest |
| `[all]` | 元 extra：上述能力 extra 的并集（不含 `[dev]`） |
| `[dev]` | `tuner-testkit[all]`，给本仓 editable 开发 |

CLI 与 `python -m tuner_testkit.…` 等价，例如 `tuner-recorder`、`tuner-page-recorder`、`tuner-api-recorder`、`tuner-mock-server`。依赖 extra 的命令在业务仓用 `uv run tuner-dump-ddl` / `uv run tuner-recorder`。

TestPilot 的确定性入口（默认 wheel 即可）：

| 命令 | 作用 |
| --- | --- |
| `tuner-workspace doctor` | 体检：还缺哪些配置、账号、表结构、通道、端口绑定，DNA 是否漂移 |
| `tuner-config show --json` / `validate` | 读配置（密钥打码）/ 校验配置 |
| `tuner-workspace changelog append` / `check` | 维护库的 changelog；提交前校验 |
| `tuner-workspace migrate knowledge` | 旧布局迁到 `knowledge/` |
| `tuner-openapi-import <spec>` | 从 OpenAPI / Swagger 冻结 api_objects |
| `tuner-dna sync --prune` / `check --json` | 升级 DNA，保留本地改动 |

---

## 安全

不得把 token、cookie、Authorization、密码、session 写入仓库（含 capture 与 api_objects）。凭证只允许运行时注入。

---

## 本仓库（平台源码）

克隆后在仓库根目录开发 kit 本身：

```powershell
uv venv
uv sync --extra all
```

`uv sync --extra dev` 与 `--extra all` 等价（`dev` 只是引用 `[all]`）。

Lint 与 CI 用同一个 ruff 版本，规则写在 `pyproject.toml` 的 `[tool.ruff.lint]`（E4 / E7 / E9 / F / B / BLE：语法与导入、pyflakes、bugbear、宽泛 except）：

```powershell
uvx ruff@0.17.3 check .
```

宽泛的 `except Exception` 要写理由：`# noqa: BLE001 -- <为什么>`。

本仓是**平台仓**，不是 workspace。路线图见 [`ROADMAP.md`](ROADMAP.md)；AI 组件（rule / skill / agent / hook）的分组与说明见 [`docs/spec/ai-components.md`](docs/spec/ai-components.md)。

7.4.0 发行说明（去掉工作台「知识」页）见 [`docs/changelog/TEMPLATE-7.4.0.md`](docs/changelog/TEMPLATE-7.4.0.md)；7.3.1 发行说明（工作台 CSS 缓存）见 [`docs/changelog/TEMPLATE-7.3.1.md`](docs/changelog/TEMPLATE-7.3.1.md)；7.3.0 发行说明（工作台看板）见 [`docs/changelog/TEMPLATE-7.3.0.md`](docs/changelog/TEMPLATE-7.3.0.md)；7.2.0 发行说明（任务文件夹与附件、任务与测试单归档）见 [`docs/changelog/TEMPLATE-7.2.0.md`](docs/changelog/TEMPLATE-7.2.0.md)；7.1.0 发行说明（账号单一来源、测试单四态结果）见 [`docs/changelog/TEMPLATE-7.1.0.md`](docs/changelog/TEMPLATE-7.1.0.md)；7.0.2 发行说明（平台主干改名 main）见 [`docs/changelog/TEMPLATE-7.0.2.md`](docs/changelog/TEMPLATE-7.0.2.md)；7.0.1 发行说明（DNA 比对不受换行符影响）见 [`docs/changelog/TEMPLATE-7.0.1.md`](docs/changelog/TEMPLATE-7.0.1.md)；7.0.0 发行说明（TestPilot：`knowledge/` 知识层、配置扩展、端口与自定义 apps、体检 / 升级 / 配置 skill）见 [`docs/changelog/TEMPLATE-7.0.0.md`](docs/changelog/TEMPLATE-7.0.0.md)；6.3.0 发行说明（测试单出 GJB438B 报告）见 [`docs/changelog/TEMPLATE-6.3.0.md`](docs/changelog/TEMPLATE-6.3.0.md)；6.2.0 发行说明（测试单）见 [`docs/changelog/TEMPLATE-6.2.0.md`](docs/changelog/TEMPLATE-6.2.0.md)；6.1.0 发行说明（scaffold 项目名）见 [`docs/changelog/TEMPLATE-6.1.0.md`](docs/changelog/TEMPLATE-6.1.0.md)；6.0.0 发行说明（一条用例一个文件）见 [`docs/changelog/TEMPLATE-6.0.0.md`](docs/changelog/TEMPLATE-6.0.0.md)；5.3.1 发行说明（已回答提问归档）见 [`docs/changelog/TEMPLATE-5.3.1.md`](docs/changelog/TEMPLATE-5.3.1.md)；5.3.0 发行说明（功能用例集 `assets/testcases/`）见 [`docs/changelog/TEMPLATE-5.3.0.md`](docs/changelog/TEMPLATE-5.3.0.md)；5.2.0 发行说明（work task / 测试设计 / 证据附件）见 [`docs/changelog/TEMPLATE-5.2.0.md`](docs/changelog/TEMPLATE-5.2.0.md)；5.1.0 发行说明（工作台 / meta stamp / `--json`）见 [`docs/changelog/TEMPLATE-5.1.0.md`](docs/changelog/TEMPLATE-5.1.0.md)；5.0.0（Plane Job 协议退场、`tuner-workspace`）见 [`TEMPLATE-5.0.0.md`](docs/changelog/TEMPLATE-5.0.0.md)；4.3.0 见 [`TEMPLATE-4.3.0.md`](docs/changelog/TEMPLATE-4.3.0.md)；3.x → 4.x 迁移见 [`TEMPLATE-4.0.0.md`](docs/changelog/TEMPLATE-4.0.0.md)。平台能力地图见 [`INDEX.md`](INDEX.md)。
