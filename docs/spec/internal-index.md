# 内部资产 / 备忘索引（钩子清单）

> ⚠️ 本页为**内部可见**文档（收录于侧边栏，但不在顶栏导航）。普通用户不会通过导航点进来，
> 即使猜到 URL 也能访问（这些内部文档不含敏感信息）。
>
> 本页列出的文件**在 `docs/.vitepress/config.mjs` 的 `srcExclude` 中被排除出构建**，
> 不进入部署产物（`docs/.vitepress/dist`），远端用户访问即 404。它们仅存在于仓库源码中，需直接阅读 `.md` 原文。

## 被屏蔽的资产 / 备忘（不在任何站点中渲染）

这些文件含项目资产、排障过程、研究草稿等备忘性质内容，按约定不对外发布。
如需查看，请在仓库中打开对应路径的源文件。

| 文件（仓库相对路径） | 性质 | 说明 |
|---|---|---|
| `docs/working-notes/`（整个目录） | 工作笔记 | 开发过程中的排障、临时结论、调研草稿，易腐烂，不对外 |
| `docs/backend-restructure-edgeone-dualengine.md` | 架构备忘 | 后端重构 + EdgeOne 双引擎方案草稿 |
| `docs/bias-datasource-troubleshooting.md` | 排障记录 | bias 数据源问题排查过程 |
| `docs/erniao-ingest-research-2026-08-02.md` | 调研草稿 | 二鸟（erniao）数据接入可行性研究 |
| `docs/overview-bias-stale-2026-08-02.md` | 状态备忘 | bias 数据陈旧问题概览（日期标记） |

## 访问管控约定

- **对外公开**（顶栏导航 + 侧边栏）：`guide/`、`features/`、`site/`、`api/`
- **内部可见**（仅侧边栏，不在顶栏）：`dev/`、`pytest/`、`ops/`、`spec/`、`design/`
- **彻底屏蔽**（不进产物）：见上表，由 `config.mjs` 的 `srcExclude` 排除出构建

新增需屏蔽的备忘文件时，同步在 `config.mjs` 的 `srcExclude` 列表与本页登记，保持两处一致。
