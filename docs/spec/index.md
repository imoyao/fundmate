---
title: 多多贝 项目规范体系（文档枢纽）
---

# 多多贝 项目规范体系（文档枢纽）

**版本**: v4.5.9
**最后更新**: 2026-08-01
**状态**: 原单一 `SPEC.md` 已于 2026-08-01 拆分为本多文件体系，`docs/spec/` 为项目唯一事实标准。

## 核心原则

本项目为**个人 / 家庭使用、云端权威 + 本地缓存、完全合规**的投资记账工具。

> **存储架构（2026-08-18 定稿）**：项目**架构必须上云**——核心账本（用户域）生产落 Supabase，市场数据（市场域）生产落 Turso；「永不上云」旧承诺已取消（D3，2026-08-07）。详见 `docs/dev/db-data-domain.md`。合规红线不变：严禁用户券商/平台持仓自动登录/爬取/同步、不荐股不跟单不预测。

## 文档定位

本目录（`docs/spec/`）取代原根目录 `SPEC.md`，作为项目**唯一事实标准**，所有开发必须严格遵守，禁止私自变更规则。

拆分目的：将「法律级硬约束」「随代码演进的中频内容」「易腐烂的进度 / 技术债 / 决策」分离，降低单文件维护负担、避免编辑事故（如曾出现的重复第 13 章编号错位）。

> 章节编号（如 §2.1、§5.7）沿用原 SPEC v4.5.x 体系，便于历史引用对齐。

## 文件导航

| 文件 | 职责 | 变更频率 | 约束级别 |
|------|------|---------|---------|
| [index.md](./index.md) | 本文档，导航与体系说明 | 低 | — |
| [conventions.md](./conventions.md) | 全局强制规范、UI 红线、编码守则、AI 约束 | 极低（冻结区） | 🔒 冻结 |
| [architecture.md](./architecture.md) | 项目概述、第三方数据适配层、高级能力、暗色模式、断点续传 | 中 | 硬约束 |
| [data-model.md](./data-model.md) | 核心数据模型完整规范 | 随代码演进 | 事实标准 |
| [api.md](./api.md) | 核心 API 端点清单 | 随代码演进 | 事实标准 |
| [frontend-ui.md](./frontend-ui.md) | 通用业务组件规范、前端区域布局与交互规范 | 随前端演进 | 硬约束 |
| [roadmap.md](./roadmap.md) | 四象限路线图与进度表 | 易腐烂（标核实日期） | 进度追踪 |
| [tech-debt.md](./tech-debt.md) | 技术债务与开口项明细 | 易腐烂（标核实日期） | 进度追踪 |
| [decisions.md](./decisions.md) | 重要决策完整记录表 | append-only | 永久回溯 |
| [pricing-tier.md](./pricing-tier.md) | 付费/免费分层规范（判定准则、功能归属、双层估值开关、前端直连约束） | 低频 | 事实标准 |
| [changelog.md](./changelog.md) | 版本更新记录与文档结束语 | 版本驱动 | 追溯 |

## 专题与子文档索引

上表列「体系级」核心文档；`docs/spec/` 下另有按主题成文的子文档，一并登记于本节。

> **维护规则（防孤儿文档）**：在 `docs/spec/` 下**新增或删除** `.md` 文件，必须同步更新本节——只落文件不登记，等同制造孤儿文档（2026-09-11 盘点发现 11 篇未登记，其中 1 篇全仓零引用）。登记时须注明**性质**（决定其约束力与是否会腐烂），不得只写文件名。

| 文档 | 职责 | 性质 |
|------|------|------|
| [importer-architecture.md](./importer-architecture.md) | 导入系统可扩展架构与社区贡献规范（导入类 issue 的「宪法」，解析器/持仓导入/去重/OCR 复用均须遵循） | 硬约束 |
| [frontend-naming.md](./frontend-naming.md) | 前端命名规范（`conventions.md` §2.7 的前端补充细则） | 事实标准 |
| [realtime-data-sources.md](./realtime-data-sources.md) | 自选/持仓**前端直连外部数据源**的权威归集（JSONP 源、字段约束）；与 `api.md`（后端自有端点）互补 | 事实标准 |
| [site-architecture-and-traffic-routing.md](./site-architecture-and-traffic-routing.md) | 站点架构与导流方案（域名/子站职责边界、身份互通、数据隔离） | 事实标准 |
| [frontend-naming-audit.md](./frontend-naming-audit.md) | 前端命名不规范点清单（执行层待办，只定位不即改） | 待办（易腐烂） |
| [integrations-plan.md](./integrations-plan.md) | 用户凭证与第三方集成规划（自持 API Key、加密存储、家庭共享、审计日志） | 规划基线（未实现） |
| [realtime-data-source-switching.md](./realtime-data-source-switching.md) | 多数据源切换与优选的设计参考（萃取自 jigu 复盘） | 参考（未实现） |
| [temperature-architecture-plan.md](./temperature-architecture-plan.md) | 温度模块 + 投资概览页的评估与排期（2026-08-02） | 排期（易腐烂） |
| [watchlist-column-defs.md](./watchlist-column-defs.md) | 自选表格 `columnDefs` 数据驱动设计（#995 前置，#990/#992/#993 的地基） | 设计依据 |
| [launch-priority-baseline.md](./launch-priority-baseline.md) | 基础可用版上线优先级基线（四象限对齐） | 基线（易腐烂，待核实） |
| [internal-index.md](./internal-index.md) | 内部资产 / 备忘索引（钩子清单） | 索引页（`srcExclude`，不参与构建） |

## 视觉设计语言（权威入口）

- 亮色模式：[`../../frontend/design.md`](../../frontend/design.md)（v2.3.2）
- 暗色模式：[`../../frontend/design.dark.md`](../../frontend/design.dark.md)（v1.4）

所有色彩、字阶、间距、token 以这两份为准；本体系仅记录与业务 / 技术架构有交集的强制决策。

## 冻结区说明

`conventions.md` 为 🔒 冻结区：其内的强制 / 红线 / 永久锁定类规则变更，须先在 `decisions.md` 记录决策，禁止随手修改。
