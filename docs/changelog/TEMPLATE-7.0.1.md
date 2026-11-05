# tuner-testkit 7.0.1 — DNA 比对不再受换行符影响

PATCH：`tuner-dna sync`、`tuner-dna check` 和发版清单按内容比较，不再区分 CRLF 和 LF。

Windows 上 `core.autocrlf=true` 时，git 把 DNA 文件检出成 CRLF。7.0.0 及更早的版本按原始字节比较，所以同事克隆下游仓后，
每个 DNA 文件都会被当成「本地改过」：`sync` 不更新它们，`check` 报漂移。7.0.1 起只看内容，7.0.0 写下的 `.tuner-dna.json` 继续有效。

## 下游怎么用

`uv tool upgrade tuner-testkit` → `uv add "tuner-testkit[<原来的 extras>]==7.0.1"` → `uv sync` → `tuner-dna sync --prune`

不需要迁移。之前只因换行符不同而被列为 `kept_local` 的文件，这次会正常更新。
