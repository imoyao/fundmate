---
title: 更新日志
# 构建期从 FeedLog 拉取（见 docs/.vitepress/theme/index.ts 的 changelogData）。
# 数据源不可达时该 loader 返回 { degraded: true }，组件显示降级提示。
use: changelogData
---

<ChangelogTimeline v-bind="$data" />

## 这是什么

多多贝的版本更新记录，面向用户——每次发布做了什么、修了什么。

## 与其他页面的区别

| 页面 | 面向谁 | 记什么 |
|------|--------|--------|
| **本页（`/changelog`）** | **用户** | 每次**发布**的产品变化 |
| [版本更新记录（changelog）](../spec/changelog.md) | 开发 | SPEC **文档**自身的修订记录（v4.8.6 那套编号） |

两者**版本编号体系不同**（本页用软件版本 `v0.1.0`；spec/changelog 用文档修订号 `v4.8.6`），
请勿混淆。历史上 `spec/changelog.md` 停留在 2026-09-09，软件版本则已重新对齐为 `v0.1.0`。

## 数据来源

本页内容**不在本仓维护**，而是构建时从 [feedback.duoduobei.com](https://feedback.duoduobei.com/changelog)
拉取—— **唯一真值源**是那边的 changelog。这样「发布 → 更新日志」只需走一条链路，
不存在两份文档互相漂移的问题。

每条更完整的页面（含表情反馈）见 [FeedLog 更新日志](https://feedback.duoduobei.com/changelog)。

::: warning 怎么加一条更新日志

**不要在本仓建 markdown 文件。** 完整链路是：

```text
在 fundmate 提 Release → release:published 事件
  → bridge-feedback.yml 自动同步→ FeedLog changelog 表
  → 公开 /changelog 与本页（构建期拉取）同时可见
```

即**只需发一个 GitHub Release**，两处都会更新。
相关脚本：`scripts/bridge/feedlog_bridge.py`（桥接）、
`scripts/docs/load-changelog.mjs`（本页数据源）。

:::