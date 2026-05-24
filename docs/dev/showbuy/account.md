---
title: 账户体系概念扫描
permalink: /account-overview
---

## 一、现有概念全景扫描

当前 ShowBuy 中涉及“资产分类与归属”的概念已经有以下四个：

| 概念 | 存储位置 | 核心问题 | 创建者 | 生命周期 |
|:---|:---|:---|:---|:---|
| **Ledger**（交易账户） | `ledgers` 表 | 钱放在哪个券商/银行？ | 用户手动创建 | 随账户开立/注销 |
| **Allocation**（五笔钱） | `positions.allocation` | 钱属于哪种风险/期限类型？ | 系统预定义（活钱/稳健/长期/博弈/保障） | 固定，不可自定义 |
| **Watchlist Group**（自选分组） | `watchlist_groups` 表 | 我关注哪些资产？ | 用户手动创建 | 随关注/取消关注 |
| **Tag**（标签） | `tags` 表 | 资产有什么特征？ | 用户手动创建 | 随标签创建/删除 |

现在我们要新增的 **Objective（投资目标）**，它回答的是：

> **“这笔钱是为了什么人生目标而投的？”**

---

## 二、是否存在冗余？

| 对比维度 | Allocation（五笔钱） | Objective（投资目标） |
|:---|:---|:---|
| **划分依据** | 风险等级 + 投资期限 | 人生目标 + 资金用途 |
| **能否自定义** | ❌ 系统预定义 5 种 | ✅ 用户任意创建 |
| **粒度** | 粗（5 种） | 细（可无限扩展） |
| **与 Ledger 关系** | 一笔持仓一个 allocation | 同一持仓的不同批次可归属不同 objective |
| **典型案例** | “活钱”、“长期增值” | “养老金”、“子女教育”、“买房首付” |

**结论：两者不冗余，是互补关系。**

- **Allocation 是“客观属性”**：根据资产的风险和期限自动或半自动分类，用户不需要思考就能理解。
- **Objective 是“主观目标”**：完全由用户根据自己的人生规划来定义，是五笔钱的进一步细化。

与 **Watchlist Group** 对比：Group 用于管理“关注列表”中的资产，Organize 的是**自选股**，不涉及实际持仓。与 **Objective** 完全不同。

与 **Tag** 对比：Tag 是资产的**特征标签**（如“高股息”、“消费龙头”），Objective 是资产的**目的归属**（如“养老金”）。Tag 是辅助筛选，Objective 是决策依据。

**所以：Objective 不冗余，但需要明确它与 Allocation 的层级关系。**

---

## 三、概念层级关系图

```
Ledger (交易账户) ← 资金存放渠道
  │
  └── Position (持仓) ← 具体持有的某只股票/基金
        ├── Allocation (五笔钱) ← 客观风险/期限分类
        │     └── Objective (投资目标) ← 主观人生目标，可选关联 Allocation
        ├── Watchlist Group (自选分组) ← 仅用于自选列表，不涉及实际持仓
        └── Tag (标签) ← 辅助特征标记，可跨不同实体
```

---

## 四、为开发者和用户准备的区分文档

### 4.1 开发者版：概念边界与 API 职责

| 概念 | 表名 | API 前缀 | 核心字段 | 与其他概念的关系 |
|:---|:---|:---|:---|:---|
| Ledger | `ledgers` | `/api/ledgers/` | `name`, `ledger_type`, `default_allocation` | 一个 Ledger 包含多个 Position |
| Allocation | `positions.allocation` | 无独立 API，通过 Position 接口 | `liquid/stable/longterm/speculative/security` | 系统预定义枚举，不可扩展 |
| Objective | `objectives` | `/api/objectives/` | `name`, `description`, `target_amount`, `target_date`, `allocation` | 可选关联 Allocation |
| Position-Objective | `position_objectives` | 通过 Position 或 Objective 接口操作 | `position_id`, `transaction_id`, `objective_id` | 多对多关联 |

**API 设计原则**：
- `Ledger` 独立管理，不与 Objective 直接关联。
- `Objective` 独立管理，创建时可选关联某个 `Allocation`。
- `Position` 通过 `position_objectives` 关联到 `Objective`，同一 Position 的不同批次可关联不同 Objective。
- `Allocation` 不提供独立 CRUD，仅作为枚举值出现在 Position 和 Objective 中。

### 4.2 用户版：界面上的四个选择（各自含义）

| 界面场景 | 用户看到的选择 | 应该怎么选 | 影响什么 |
|:---|:---|:---|:---|
| **导入交易前** | “这笔交易发生在哪个账户？” | 选择资金存放渠道（华泰证券、支付宝） | 决定交易记录归属的 Ledger |
| **导入预览或持仓页面** | “配置目标（五笔钱）” | 选择活钱/稳健/长期/博弈/保障 | 决定资产在五笔钱视图中的分组 |
| **导入预览或持仓页面** | “投资目标（可选）” | 选择或创建目标（如“养老金”） | 进一步细化这笔钱的目的 |
| **自选管理页面** | “分组” | 选择或创建自选分组（如“消费股”） | 仅影响自选列表的展示，不影响实际持仓 |

**防混淆提示**：
- **账户** = 钱放在哪里（券商/银行）
- **五笔钱** = 钱的风险等级
- **投资目标** = 钱为了什么（养老金/教育/买房）
- **自选分组** = 我关注的资产怎么分类（和实际持仓无关）

### 4.3 典型案例：用户“为养老买入腾讯”

```
1. 用户选择 Ledger: "华泰证券"
2. 导入交易: 买入 100 股腾讯控股
3. 设置 Allocation: "长期增值"（因为腾讯是股票，风险高、期限长）
4. 设置 Objective: "养老金"（因为这笔钱是为了退休准备的）
```

最终数据关系：
```
Ledger: 华泰证券
  └── Position: 腾讯控股
        ├── Allocation: longterm
        └── Objective: 养老金（通过 position_objectives 关联）
```
