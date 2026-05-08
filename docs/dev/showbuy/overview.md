你提出的这个问题，不仅有意义，而且是专业项目管理的核心——**即使 MVP 可以最小化交付，但技术债务和资产需要被“可视化管理”**，否则团队的“心里没底”就是真实的风险。

我依据我们共同确认的 **SPEC.md v1.1** 和旧项目考古分析，为你整理了一份完整的全景式清单。它分为三个视图，让你既能把握宏观，也能审视微观。

---

## 📊 全景式资产清单

### 1️⃣ 核心继承清单（旧项目模型 → 新项目）

| 旧项目资产 (文件/模块) | 核心设计思想 | 继承状态 | 新项目位置 / 说明 |
| :--- | :--- | :--- | :--- |
| `settings.py` / `enums.py` | 所有业务枚举体系 | ✅ **已继承** | `backend/app/core/enums.py` |
| `database.py` (旧) | `CRUDMixin` 混入类 | ✅ **思想继承** | `backend/app/database.py` 中待实现，当前简化 |
| `fund/models.py` | `Fund ↔ Manager` M2M 关系 | ✅ **设计完全继承** | `backend/app/models/fund.py` (待搭建) |
| `fund/models.py` | `FeeRatio` 费率体系 | 🕒 **P2 暂缓** | SPEC 已完整记录其字段，MVP 后移植 |
| `fund/models.py` | `FundPortfolio` 组合体系 | 🕒 **P2 暂缓** | P2 功能，模型结构保留在 SPEC |
| `fund/models.py` | `Fund.search_key()` 搜索逻辑 | ✅ **设计继承** | `backend/app/services/fund_search.py` (待实现) |
| `account/models.py` | “四笔钱”风险维度 | ✅ **理念继承** | `backend/app/models/account.py` (待搭建) |
| `account/models.py` | `AccountTransactionRecord` | ✅ **字段设计继承** | `backend/app/models/transaction.py` (待搭建) |
| `collection/models.py` | `Collection/Categories/Labels` 体系 | 🕒 **P1 完整继承** | P1 功能，MVP 后实现 |
| `user/models.py` | `User` 密码处理、`lookup()` | 🕒 **P1 继承+重写** | MVP 实现鉴权时处理 |

### 2️⃣ 数据模型与字段清单

| 表/模型 | 核心字段 | 状态 | 后续规划 |
| :--- | :--- | :--- | :--- |
| `positions` (持仓表) | `id`, `symbol`, `name`, `market`, `type`, `account_name`, `quantity`, `avg_price`, `currency`, `current_price`, `purchase_date`, `notes`, `created_at`, `updated_at` | ✅ **已创建** | MVP 正常运行中。`family_id` 字段看情况，需要时再加。 |
| `securities` (证券元数据表) | `id`, `symbol`, `name`, `market`, `type`, `exchange`, `sector`, `industry`, `is_active` | 🕒 **P1 搭建** | 首批基金或股票导入时即建表 |
| `funds` (基金元数据表) | `id`, `fund_code`, `name`, `full_name`, `fund_type`, `company`, `risk_level`, `inception_date`, `management_fee` | 🕒 **P1 搭建** | 同上 |
| `managers` (基金经理表) | `id`, `name`, `company`, `appointment_date`, `sum_scale` | 🕒 **P1 搭建** | 同上 |
| `fund_manager_links` (关联表) | `id`, `fund_id`, `manager_id`, `start_date`, `end_date` | 🕒 **P1 搭建** | 同上 |
| `transactions` (交易记录表) | 旧 `AccountTransactionRecord` 字段精简版 | 🕒 **P1 搭建** | 记录每笔买入/卖出/分红等操作 |
| `accounts` (账户表) | `id`, `name`, `account_type`, `desc` | 🕒 **P1 搭建** | 简单的账户管理 |
| `currencies` (汇率表) | `code`, `rate_to_cny`, `updated_at` | 🕒 **P1 完善** | MVP 当前硬编码，后期改为可动态维护 |

### 3️⃣ 业务逻辑与功能清单

| 功能模块 | 细项 | 状态 | 后续规划 |
| :--- | :--- | :--- | :--- |
| **API 接口** | `positions` CRUD | ✅ **完成** | |
| | `summary` 聚合 | ✅ **完成 (v0.1)** | 后期增加收益率、账户分类等 |
| | 基金搜索 `/funds/search` | 🕒 **P1** | 继承旧 `Fund.search_key()` |
| | 文件上传 `/upload` | 🕒 **P1** | |
| | 汇率管理 `/currencies` | 🕒 **P1** | |
| **前端页面** | 资产总览仪表盘 | 🔜 **下一步** | |
| | 持仓列表 + 新增表单 | 🔜 **下一步** | |
| | 自选管理（轻量版） | 🕒 **P1** | |
| | 设置页（汇率/账户） | 🕒 **P1** | |
| | 数据可视化（饼图/折线图） | 🕒 **P1** | |
| **测试** | `pytest` + `httpx` 接口自动化测试 | 🕒 **P1 启动** | MVP 闭环后立即启动 |
| **数据处理** | 数据导入（CSV/JSON） | 🕒 **P1** | |
| | 数据导出（CSV 备份） | 🕒 **P1** | |
| **部署** | Docker 化 | 🕒 **P2** | |

> 优先级标记：**P0** (MVP 闭环) → **P1** (完善核心) → **P2** (长期优化)

---

## 💡 关于“是否偏离 MVP 实践”的建议

你并不需要因为这些清单而暂停 MVP 开发。清单的作用是给你一个**全局的“信心基础”**——让你知道哪些资产已经安全归还，哪些正在路上，哪些决定暂时封存。

建议你把这份清单作为 **`docs/CHECKLIST.md`** 文件提交到仓库中。每次会话开始或结束时，花 2 分钟更新一下状态。这符合 MVP 的“渐进式交付”理念，而且能有效防止未来技术债务失控：**丢弃或推迟，都是经过明确决策的，而不是被遗忘的。** 这也是对我们最初考古工作价值的最终兑现。

---

## 📌 当前进度总结与下一步

| 维度 | 当前状态 |
| :--- | :--- |
| **后端 API (P0)** | ✅ 完成，`/docs` 可交互 |
| **数据模型 (P0)** | ✅ `positions` 表完成 |
| **代码质量** | ✅ Lint 问题基本修复，前置检查配置完成 |
| **前端** | 🔜 下一步启动 |
