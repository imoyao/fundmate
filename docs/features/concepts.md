---
title: 概念体系总览（SSOT）
---

## 一、为什么要有这份文档

多多贝的"资产分类与归属"概念曾在多份文档中零散出现（账户体系扫描、数据模型、Issue #859、Discussion #152），且一度出现"Objective 是否独立成实体"的分歧。本文为**唯一事实标准（SSOT）**，汇总并裁定所有概念边界。**凡与本文冲突，以本文为准。**

权威来源：GitHub Issue [#859](https://github.com/imoyao/fundmate/issues/859) 与 Discussion [#152](https://github.com/imoyao/fundmate/discussions/152)（2021 年开、2026-06 定稿的核心概念体系），以及 `docs/spec/data-model.md` §5.11。

## 二、实体模型（均已实现）

| 概念 | 存储位置 | 核心问题 | 创建者 | 生命周期 / 约束 |
|:---|:---|:---|:---|:---|
| **Position**（持仓） | `positions` 表 | 具体持有了哪只股票/基金？ | 导入产生 | 收益计算、配置分析核心数据源 |
| **Ledger**（交易账户） | `ledgers` 表 | 钱放在哪个券商/银行？ | 用户手动 | 一个 Ledger 最多关联一个 Portfolio（多对一），不拆分持仓 |
| **Portfolio**（投资组合） | `portfolios` 表 | 这笔钱按什么策略/目标投资？ | 用户手动 | 合并关联 Ledger 现金流算 XIRR；`purpose` 字段承载"投资目标" |
| **Allocation**（五笔钱） | `positions.allocation` | 钱属于哪种风险/期限类型？ | 系统预定义（活钱/稳健/长期/博弈/保障） | 固定枚举，不可自定义 |
| **Strategy**（策略标签） | `strategy_tags` + `position_strategy_tags` | 持仓是什么风格（成长/价值/大盘）？ | 用户手动 | 纯展示层，不参与 XIRR |
| **Watchlist Group**（自选分组） | `watchlist_groups` 表 | 我关注哪些资产？ | 用户手动 | 仅影响自选列表，不涉及实际持仓 |
| **Tag**（标签） | `tags` 表 | 资产有什么特征（高股息/消费龙头）？ | 用户手动 | 辅助筛选 |

## 三、关键裁定：Objective 不是独立实体

历史上曾设想独立的 `objectives` 表、`/api/objectives/` 接口与 `position_objectives` 多对多关联（见历史文档 `account.md` 的 Objective 章节）。**该方案已被否决且从未落地**：

- "投资目标"语义已**降级并入 `Portfolio.purpose` 字段**（`data-model.md` §5.11.1 注："原 Objective 概念降级并入"；§5.11.2 注："原计划添加的 `objective` 字段已移除，语义与 `Portfolio.purpose` 重叠"）。
- 粒度原则：一个 Ledger 只归属一个 Portfolio，**同一持仓不拆分到多个目标**（与 #859 的"资金流防火墙、同账户不拆"一致）。
- 因此：**Allocation（五笔钱）与 Portfolio（投资目标）是平行概念，不存在"Objective 是五笔钱的细化/子类"的嵌套关系。**

## 四、两个页面的视角（用户怎么理解）

| 页面 | 一句话定位 | 承载的概念 | 性质 |
|:---|:---|:---|:---|
| **投资概览（welcome / 家庭资产看板）** | 我想过什么样的人生？设了什么目标？离目标多远？ | 心理账户 / Portfolio（投资目标）+ 收益·XIRR·市场温度·财务健康 | **理想 / 目标 + 表现进度** |
| **资产总览（panorama / 资产配置）** | 为了目标，我怎么规划钱、走哪条路径？ | 五笔钱（配置目标）、产品类型、账户、资产端/负债端 | **生活 / 方法（composition 拆解）** |

核心区分：**五笔钱是"方法/路径"（按风险分层去支撑目标），心理账户/Portfolio 是"理想"（目标本身）**。两者都沾"意图"，但一个是现状的切分、一个是未来的承诺，分到两页不打架。详见工作记录 `page-split-welcome-vs-panorama-2026-08-13.md`。

## 五、防混淆速查（给用户看）

- **账户** = 钱放在哪里（华泰证券、支付宝）。
- **五笔钱（配置目标）** = 钱的风险等级与期限（活钱/稳健底仓/长期增值/高风险博弈/保险保障），系统按产品属性自动归类，不可自定义。
- **投资目标（心理账户）** = 钱为了什么人生目标（养老金/教育/买房），由你自建，经 Portfolio 实现。
- **自选分组** = 我关注的资产怎么分类，与实际持仓无关。
- **标签** = 资产的特征标记（高股息、消费龙头），辅助筛选。

## 六、参考

- Issue [#859](https://github.com/imoyao/fundmate/issues/859)、Discussion [#152](https://github.com/imoyao/fundmate/discussions/152)
- `docs/spec/data-model.md` §5.11 投资组合
- `docs/features/account.md`（历史扫描，Objective 章节已废弃）
- 工作记录 `page-split-welcome-vs-panorama-2026-08-13.md`
