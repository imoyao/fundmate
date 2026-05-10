# 项目需求规格说明书 (SPEC.md)

> **版本**: v1.1
> **最后更新**: 2026-05-07
> **状态**: 草案，基于旧项目考古分析后更新
> **核心原则**: 本项目为**个人使用、本地优先、完全合规**的投资记账工具。

---

## 📋 项目需求规格说明书 (SPEC.md)

**版本**: v2.0
**最后更新**: 2026-05-10
**状态**: 核心闭环完成，正在扩展通用资产体系。
**核心原则**: 个人使用、本地优先、完全合规、数据主权绝对在我。

---

### 1. 项目愿景与技术栈

**我们要解决的核心问题**：为个人投资者提供一个安全、私密、可长期维护的全球资产记账工具，回答“我今天比昨天多了多少钱？我的钱都放在哪儿？”。

**后端**：
- **语言/环境**: Python 3.12+，PDM 管理依赖
- **框架**: APIFlask
- **数据库**: SQLite (开发) + SQLAlchemy 2.0 (原生，不耦合 flask-sqlalchemy)
- **原则**: 视图函数手动构建 `{ data, message }` 统一响应，不使用 `BASE_RESPONSE_SCHEMA`，以便未来平滑迁移到 FastAPI。

**前端**：
- **框架**: Vue 3 + Vite + TypeScript
- **基础工程**: pure-admin-thin
- **UI库**: Element Plus
- **状态管理**: Pinia
- **图表库**: ECharts

**代码质量**：
- 后端统一使用 `ruff` 进行 Lint 与格式化。
- 前端遵循 pure-admin 内置规范。

**旧项目资产处理**:
- 旧 `fundmate` 项目的枚举体系、多对多关系设计、交易记录思想等已全部提取、继承或记录。新旧代码不可直接混淆。

---

### 2. 核心数据模型

**通用原则**:
- **统一响应格式**: `{ "data": ..., "message": "ok" }`。所有"列表"和"分页"接口都遵循此格式。

#### 2.1 `positions` (可买卖的金融资产)
**用途**: 股票、ETF、可转债、基金、虚拟货币、银行存款等需要追踪成本与盈亏的资产。

| 核心字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id`, `symbol`, `name`, `market`, `type` | - | 基本标识 |
| `account_name` | String | **所属账户** |
| `quantity`, `avg_price` | Float | 持仓数量与成本价 |
| `currency`, `current_price` | String, Float | 本币种与当前市价 |
| `purchase_date`, `notes` | Date, Text | 首个买入日期与备注 |
| `allocation` | String | **配置目标** (五笔钱) |
| `is_liability` | Boolean | **是否为负债** (复用字段) |
| `liability_type` | String | 负债类别 (信用卡/房贷等) |

#### 2.2 `transactions` (交易流水)
**用途**: 记录所有买卖、分红、存取款的历史。是的“录像机”，用于复盘。

| 核心字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id`, `position_id` | - | 关联的持仓 |
| `type` | String | **操作类型**: buy, sell, dividend, deposit, withdraw |
| `trade_date` | Date | **交易发起日期 (T日)** |
| `quantity`, `price`, `fee`, `amount` | Float | 交易细节 |
| `status` | String | **交易状态**: success, failed, cancelled, pending |
| `position_name`, `account_name` | String | **快照字段**，确保上游删除后流水不丢失 |
| `notes`, `created_at` | Text, DateTime | 备注与创建时间 |

#### 2.3 `assets` (通用资产与负债)
**用途**: **核心扩展**。用于房产、汽车、应收款、负债、保险等非高频交易的广义资产/负债。

| 核心字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id`, `user_id` | - | 主键，`user_id` 为多用户预留 |
| `major_category` | String | **大类**: cash, fixed, receivable, liability, insurance |
| `minor_category` | String | **小类**: 自由定义 (如 mortgage, credit_card, car) |
| `name`, `amount`, `currency` | - | 资产名，当前价值，币种 |
| `account_name`, `allocation` | - | 归属与配置目标 |
| `status` | String | active / closed |
| `start_date`, `end_date` | Date | 生效与到期/还清日 |
| `extra` | JSON | **扩展属性** (如房面积、借款人、保单号等) |

---

### 3. API 设计 (核心端点)

**通用前缀**: `/api`

| 方法 | 路径 | 描述 | 关键特性 |
| :--- | :--- | :--- | :--- |
| `GET/POST` | `/positions` | 持仓CRUD | **`POST` 为智能接口**：买入时合并持仓，卖出/分红时修改持仓并写入流水。支持 `?group_by=account` |
| `PATCH,DELETE` | `/positions/{id}` | 更新/删除持仓 | `PATCH` 用于更新价格等字段 |
| `GET` | `/transactions` | 获取交易流水 | 支持多维筛选 (type, asset_type, status, time_range) 与分页 |
| `GET/POST` | `/assets` | 通用资产CRUD | 支持按 `major_category` 筛选 |
| `PATCH,DELETE` | `/assets/{id}` | 更新/删除通用资产 | |
| `GET` | `/summary` | **仪表盘聚合数据** | 合并 `positions` 与 `assets`，返回 总资产、总负债、净资产、总盈亏等 |

---

### 4. 前端核心功能与状态

| 页面/组件 | 状态 | 核心职责 |
| :--- | :--- | :--- |
| **仪表盘 (Dashboard)** | ✅ 已完成 | 展示总资产/盈亏/市场分布，基于真实数据。 |
| **快速记账模态框** | ✅ 已完成 | 核心交互。支持多资产类型的动态表单 (股票/基金/虚拟币/可转债/静态资产)、卖出/分红操作、五笔钱配置、15点前后申购。 |
| **账户总览 (AccountOverview)** | ✅ 已完成 | 持仓列表，支持筛选 (账户/市场/类型)、分页、行内编辑价格、删除。 |
| **交易流水 (TransactionList)** | ✅ 已完成 | 表格与时间线双视图，支持多维筛选 (操作类型/资产类型/状态/时间) 与分页。 |
| **资产全景 (AssetPanorama)** | ✅ 已完成 | 聚合视图。包含总览大卡片 (净资产/总资产/负债)、瀑布图、桑基图、饼图/柱状图维度切换、摘要卡片、明细表格。 |
| **通用资产录入** | ⚠️ 待完善 | 目前可在弹窗中选择"通用资产/负债"类型进行录入，已打通后端。 |
| **负债显示** | ⚠️ 待完善 | 全景页已能显示总负债，但明细表格未合并 `assets` 数据。 |

---

### 5. 开发路线图

#### ✅ 里程碑 1：核心闭环 (已完成)
- [x] 项目环境搭建、核心模型定义
- [x] `positions` 与 `transactions` CRUD API
- [x] 记账弹窗、账户总览、交易流水 (含卖出、分页)
- [x] 资产全景 (含瀑布图、桑基图、维度切换)

#### 🔜 里程碑 2：通用资产体系完善 (当前重点)
- [ ] **【前端】统一资产明细表**：在全景或总览页整合 `positions` + `assets` 数据，完善负债/通用资产的展示。
- [ ] **【前端】完善记账弹窗**：支持录入所有通用资产大类 (应收款、保险等)，并动态渲染 `extra` 字段。
- [ ] **【后端】`summary` 微调**：确保各项资产变化率准确，支持五笔钱分组统计。
- [ ] **【全栈】`positions` 清算**：移除临时的 `is_liability` 字段，让负债全面归入 `assets`。

#### 📅 里程碑 3：P1 功能池
- [ ] **Step 分步记账**：将弹窗重构为“填写 → 确认 → 结果”三步向导。
- [ ] **收益率计算**：基于 `transactions` 表，在仪表盘展示年化收益率。
- [ ] **数据导出**：支持一键导出 CSV/JSON 备份。
- [ ] **文档体系**：完成操作手册、设计哲学、开发者指南。
- [ ] **用户认证 (JWT)**：为多用户和设备同步做准备。
- [ ] **移动端适配**：PWA 或响应式优化。

---
**本文档将作为项目开发的唯一事实标准。任何需求或实现的变更，都应先更新此文档，再修改代码。**

```
