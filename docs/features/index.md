---
title: 功能设计
---

## 功能设计文档

本目录收录多多贝各功能模块的产品设计与技术决策记录，供开发者、产品设计者与贡献者参考。

- [全景式资产清单](./overview.md)：旧项目模型向新项目继承时的字段对照与数据模型清单。
- [概念体系总览（SSOT）](./concepts.md)：Position / Ledger / Portfolio(purpose=投资目标) / Allocation(五笔钱) / Strategy / Watchlist / Tag 的权威定义、两页面视角与防混淆速查。**概念以本文为准。**
- [账户体系概念扫描](./account.md)：Ledger / Allocation / Watchlist / Tag 的概念边界（Objective 章节已废弃，见 concepts.md）。
- [资产简记与盘点](./holding-record.md)：简记弹窗与全面盘点页面的需求、字段与去重对账设计。
- [资产复盘页面](./asset-review.md)：周 / 月 / 年报绩效分析视图的组件与交互设计。
- [自选股功能设计](./watchlist.md)：自选、分组、标签与基金经理追踪的数据模型与交互设计。
- [年化收益率（XIRR）决策](./xirr.md)：组合年化收益率计算引擎的技术选型与架构决策。
- [会话窗口恢复指南](./recover-from-ai.md)：会话达到上限时如何向新会话续传项目上下文。
- [市场温度（Explore）重设计](./temperature-redesign.md)：探索页市场温度功能的视觉与交互重设计方案。
- [探市（大类资产观察）设计](./market-explorer.md)：20 个大类资产的源映射（含真接口实测的通道健康度）、跨市场口径规则、数据分层，以及探市页 / 温度计页的界面设计。
