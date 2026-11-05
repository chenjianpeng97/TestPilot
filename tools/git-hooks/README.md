# git-hooks

确定性 git 钩子：提交规范校验、暂存文件密钥扫描、DNA 漂移提醒。规范见 `docs/spec/commit-convention.md` 与 `AGENTS.md` §5。

## 启用（本地一次性，不改全局配置）

```bash
git config core.hooksPath tools/git-hooks
```

## 钩子

| 钩子 | 何时 | 做什么 | 阻断？ |
| --- | --- | --- | --- |
| `pre-commit` → `secret_scan.py` | `git commit` 前 | 扫描暂存文件里**像凭据的值**：Bearer/Basic 头、JWT、私钥块、Cookie 头、云 access key、`password = <8+ 字符非占位符>` 等赋值 | 是（exit 1） |
| `commit-msg` → `validate_commit_msg.py` | 写完提交信息 | 首行 Conventional Commits；声明 scope 覆盖实际改动层（`packages` 覆盖三个子资产层） | 是 |
| `pre-push` | `git push` 前 | `init_repo manifest --check`，DNA 漂移只警告 | 否 |

- 合并/回滚提交（`Merge`/`Revert`/`fixup!`/`squash!` 开头）跳过 commit-msg 校验。
- 找不到 python 时钩子 fail-open；找不到暂存文件列表时 commit-msg 只做格式检查。
- secret-scan 的占位符白名单：`{{password}}`、`***`、`<...>`、`$VAR`、`CHANGE_ME`、`replace-me` 等；文档里确需示例值的行末加 `# secret-scan: allow`。
- 测试 / 活文档可用环境变量 `TUNER_COMMIT_STAGED`（换行分隔路径）替代 `git diff --cached`。

## 文件

- `pre-commit` / `commit-msg` / `pre-push`：git 调用的 shell 入口（sh，跨平台，优先用仓库 `.venv`）。
- `secret_scan.py` / `validate_commit_msg.py`：确定性校验逻辑（stdlib，无第三方依赖）。

## CI 复用

- `python tools/git-hooks/secret_scan.py <paths…>` 扫指定文件；不传路径则扫暂存区。
- `python tools/git-hooks/validate_commit_msg.py <msg-file>` 校验一条提交信息。
