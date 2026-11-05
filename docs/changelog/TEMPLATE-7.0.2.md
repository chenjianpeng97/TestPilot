# tuner-testkit 7.0.2 — 平台主干改名为 main

PATCH：平台仓的主干分支从 `public-main` 改名为 `main`，`dump-ddl` skill 里的分支说法同步更新（1.3.1）。没有运行库或布局变化。

## 下游怎么用

`uv tool upgrade tuner-testkit` → `uv add "tuner-testkit[<原来的 extras>]==7.0.2"` → `uv sync` → `tuner-dna sync --prune`

不需要迁移。
