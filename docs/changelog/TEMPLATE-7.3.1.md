# tuner-testkit 7.3.1 — 工作台样式缓存破坏

PATCH，向后兼容。

## 变化

- **工作台 CSS 缓存**：`base.html` 里的样式表改为 `/static/app.css?v=<mtime>`。升级 kit 后浏览器不会继续用旧的 `app.css`，避免侧栏与看板卡片看起来像未加样式的蓝链（顶栏仍是绿的）。

## 下游怎么用

`uv add "tuner-testkit[<原来的 extras>]==7.3.1"` → `uv sync` → 重启 `tuner-workbench`，必要时对页面强制刷新一次（Ctrl+F5）。

## 需要迁移

不需要。
