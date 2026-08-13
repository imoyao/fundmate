---
title: 账户体系概念扫描
permalink: /account-overview
---

> ⚠️ **文档状态（2026-08-13 修订）**：本文是对"资产分类与归属"概念的**历史扫描**，其中 **Objective（投资目标）相关章节已过时、从未落地**。权威概念体系见 [`concepts.md`](./concepts.md) 与 GitHub Issue [#859](https://github.com/imoyao/fundmate/issues/859) / Discussion [#152](https://github.com/imoyao/fundmate/discussions/152)。
>
> 关键更正：**Objective 不是独立实体**。原计划中的 `objectives` 表、`/api/objectives/`、`position_objectives` 多对多关联均**未实现且已被否决**；"投资目标"语义已**降级并入 `Portfolio.purpose` 字段**（见 `docs/spec/data-model.md` §5.11）。本文中关于独立 Objective 实体、"Objective 是五笔钱的进一步细化"、"同一持仓不同批次可归属不同 Objective" 的描述，**以 `concepts.md` 为准，本文不再作为实现依据**。

## 一、现有概念全景扫描

当前 多多贝 中涉及"资产分类与归属"的**已实现**概念有以下五个（外加两类辅助标记）：

| 概念 | 存储位置 | 核心问题 | 创建者 | 生命周期 |
|:---|:---|:---|:---|:---|
| **Ledger**（交易账户） | `ledgers` 表 | 钱放在哪个券商/银行？ | 用户手动创建 | 随账户开立/注销 |
| **Allocation**（五笔钱） | `positions.allocation` | 钱属于哪种风险/期限类型？ | 系统预定义（活钱/稳健/长期/博弈/保障） | 固定，不可自定义 |
| **Portfolio**（投资组合） | `portfolios` 表 | 这笔钱按什么策略/目标投资？ | 用户手动创建 | 合并关联 Ledger 现金流算 XIRR；`purpose` 承载"投资目标" |
| **Watchlist Group**（自选分组） | `watchlist_groups` 表 | 我关注哪些资产？ | 用户手动创建 | 随关注/取消关注 |
| **Tag**（标签） | `tags` 表 | 资产有什么特征？ | 用户手动创建 | 随标签创建/删除 |

> 关于"投资目标"：历史上曾设想独立的 `objectives` 表与 `position_objectives` 多对多关联，但该方案已被否决、从未落地。"投资目标"这一**概念**仍然存在，只是语义并入 `Portfolio.purpose`，不再独立成表（详见 [`concepts.md` §三](./concepts.md)）。

---

## 二、是否存在冗余（已落地概念之间）

| 对比维度 | Allocation（五笔钱） | Portfolio（投资目标） |
|:---|:---|:---|
| **划分依据** | 风险等级 + 投资期限 | 人生目标 + 资金用途 |
| **能否自定义** | ❌ 系统预定义 5 种 | ✅ 用户任意创建 |
| **粒度** | 粗（5 种） | 细（可无限扩展） |
| **与 Ledger 关系** | 每笔持仓一个 allocation（系统自动） | 一个 Ledger 关联一个 Portfolio（多对一，不拆持仓） |
| **典型案例** | "活钱"、"长期增值" | "养老金"、"子女教育"、"买房首付" |

**结论：两者不冗余，是互补且平行的客观/主观关系。**

- **Allocation 是"客观属性"**：根据资产的风险和期限自动或半自动分类，用户不需要思考就能理解。
- **Portfolio（投资目标）是"主观目标"**：完全由用户根据自己的人生规划来定义。

> 〔已废弃旧表述〕原草案称"Objective 是五笔钱的进一步细化""Allocation └── Objective 嵌套"——**不成立**。Allocation 与 Portfolio 平行，无嵌套（见 `concepts.md` §三）。

与 **Watchlist Group** 对比：Group 用于管理"关注列表"中的资产，Organize 的是**自选股**，不涉及实际持仓。与 **Portfolio** 完全不同。

与 **Tag** 对比：Tag 是资产的**特征标签**（如"高股息"、"消费龙头"），Portfolio 是资产的**目的归属**（如"养老金"）。Tag 是辅助筛选，Portfolio 是决策依据。

**所以：Allocation 与 Portfolio 不冗余，但层级上平行互补，不存在嵌套。**

---

## 三、概念层级关系图（已落地）

```plain
Ledger (交易账户) ← 资金存放渠道
  │
  └── Position (持仓) ← 具体持有的某只股票/基金
        ├── Allocation (五笔钱) ← 客观风险/期限分类（系统预定义枚举）
        ├── Portfolio (投资组合) ← 主观人生目标（purpose 字段），与 Allocation 平行
        ├── Watchlist Group (自选分组) ← 仅用于自选列表，不涉及实际持仓
        └── Tag (标签) ← 辅助特征标记，可跨不同实体
```

> 〔已废弃旧图〕旧图曾将 Objective 画为 Allocation 的子节点（Allocation └── Objective）。Objective 已非独立实体，不再出现于此图。

---

## 四、为开发者和用户准备的区分文档

### 4.1 开发者版：概念边界与 API 职责

| 概念 | 表名 | API 前缀 | 核心字段 | 与其他概念的关系 |
|:---|:---|:---|:---|:---|
| Ledger | `ledgers` | `/api/ledgers/` | `name`, `ledger_type`, `default_allocation`, `portfolio_id` | 一个 Ledger 最多关联一个 Portfolio |
| Allocation | `positions.allocation` | 无独立 API，通过 Position 接口 | `liquid/stable/longterm/speculative/security` | 系统预定义枚举，不可扩展 |
| Portfolio | `portfolios` | `/api/portfolios/` | `name`, `purpose`, `target_amount`, `target_date`, `target_return`, `benchmark` | `purpose` 承载"投资目标"语义 |
| Watchlist Group | `watchlist_groups` | `/api/watchlist/` | `name` | 仅影响自选列表 |
| Tag | `tags` | `/api/tags/` | `name` | 辅助筛选 |

> 〔已废弃旧表〕原 §4.1 所列 `objectives` 表、`/api/objectives/` 前缀、`position_objectives` 关联表均**未实现**。请勿据此建表或写接口；"投资目标"经 `Portfolio.purpose` 实现。

**API 设计原则**：

- `Ledger` 独立管理；通过 `portfolio_id` 关联 `Portfolio`（多对一）。
- `Portfolio` 独立管理，`purpose` 表达投资目标；无独立 `objectives` 概念。
- `Allocation` 不提供独立 CRUD，仅作为枚举值出现在 Position 中。

### 4.2 用户版：界面上的几个选择（各自含义）

| 界面场景 | 用户看到的选择 | 应该怎么选 | 影响什么 |
|:---|:---|:---|:---|
| **导入交易前** | "这笔交易发生在哪个账户？" | 选择资金存放渠道（华泰证券、支付宝） | 决定交易记录归属的 Ledger |
| **导入预览或持仓页面** | "配置目标（五笔钱）" | 选择活钱/稳健/长期/博弈/保障 | 决定资产在五笔钱视图中的分组（系统多按产品属性预填） |
| **组合/投资目标页面** | "投资目标（如养老金）" | 创建或选择 Portfolio | 经 `Portfolio.purpose` 实现，用于目标进度追踪 |
| **自选管理页面** | "分组" | 选择或创建自选分组（如"消费股"） | 仅影响自选列表的展示，不影响实际持仓 |

**防混淆提示**：

- **账户** = 钱放在哪里（券商/银行）
- **五笔钱** = 钱的风险等级
- **投资目标** = 钱为了什么（养老金/教育/买房），经 Portfolio 实现
- **自选分组** = 我关注的资产怎么分类（和实际持仓无关）

### 4.3 典型案例：用户"为养老买入腾讯"

```plain
1. 用户选择 Ledger: "华泰证券"
2. 导入交易: 买入 100 股腾讯控股
3. 设置 Allocation: "长期增值"（因为腾讯是股票，风险高、期限长）
4. 设置 Portfolio: "养老金"（因为这笔钱是为了退休准备的；经 Portfolio.purpose 实现）
```

> 〔已废弃旧表述〕旧版称"设置 Objective: 养老金（通过 position_objectives 关联）"。实际为 **Portfolio.purpose**，**不存在 `position_objectives` 多对多、也不拆分同一持仓到多个目标**（一个 Ledger 只关联一个 Portfolio）。

最终数据关系：

```plain
Ledger: 华泰证券  ──portfolio_id──►  Portfolio: 养老金
  └── Position: 腾讯控股
        └── Allocation: longterm
```
