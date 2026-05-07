# 项目需求规格说明书 (SPEC.md)

> **版本**: v1.1
> **最后更新**: 2026-05-07
> **状态**: 草案，基于旧项目考古分析后更新
> **核心原则**: 本项目为**个人使用、本地优先、完全合规**的投资记账工具。

---

## 1. 项目愿景与价值

### 1.1. 我们要解决什么问题？

为个人投资者提供一个**安全、私密、可长期维护**的全球资产记账工具，以回答一个核心问题：“我今天比昨天多了多少钱？我的钱都放在哪儿？”。

### 1.2. 核心价值主张

- **绝对的数据主权**：所有数据存储在本地，不上传任何云端。用户完全掌控自己的财务数据。
- **完全的合规性**：通过手动/文件导入/截图导入的方式录入数据。
- **全球资产统一视图**：用最简洁的统一数据模型管理股票、ETF、可转债、基金等各类资产，统一换算为人民币进行总览。
- **为家庭财富管理而生**：设计上预留了未来向家庭共享和协作扩展的空间，但MVP阶段专注于单人使用。

---

## 2. 全局设计原则

### 2.1. 数据合规与安全 (不可妥协)

- **数据录入方式**：
  - **[P0]** 支持用户手动在Web表单中逐条录入交易。
  - **[P1]** 支持用户上传标准格式的CSV/JSON文件（从券商/工具合法导出），系统进行解析和导入。
  - **严禁**：任何形式的模拟登录、自动抓取网页、或调用非官方API获取用户财务数据的行为。
- **数据存储**：
  - 数据库文件及相关配置仅存储在本地。
  - 未来的“云部署”指将整个应用Docker化后部署在用户自己控制的云服务器上，而非服务化（SaaS）模式。

### 2.2. 设计与开发 (极简与务实)

- **“一张表”原则**：所有金融资产（股票、基金、债券等）的持仓统一存储在一个核心 `positions` 表中，通过字段区分类型。资产的元数据（股票/基金的基本信息）分表存储。
- **API-First**：前后端开发严格遵循API文档契约，先定义接口，再各自实现。
- **渐进式交付**：永远优先交付最小可用功能（MVP），跑通核心闭环后再逐步增加复杂度。
- **技术栈务实**：MVP阶段坚定使用`APIFlask`快速推进，但不耦合`flask-sqlalchemy`，使用原生SQLAlchemy 2.0，确保未来向`FastAPI`的迁移是轻松和无痛的。

### 2.3. 用户体验 (高效与专注)

- **30秒效率**：首页仪表盘设计的目标是让用户在30秒内掌握资产全局概况。
- **分层信息架构**：采用“首页轻量摘要 + 独立功能页”的模式，避免单一页面信息过载。高频操作入口必须浅，复杂操作可以深。

---

## 3. 技术栈与环境

### 3.1. 仓库管理

- **仓库**: 沿用旧仓库，在新分支 `main-v2` 上进行开发。
- **代码资产复用**: 旧项目的业务逻辑、组件设计等作为参考，代码全部重写，以消除历史债务。

- **仓库**: 沿用旧仓库，创建孤儿分支 `main-v2` 作为全新技术起点。旧代码保留在原分支作为参考。
- **代码资产复用**: 旧项目的业务逻辑、数据模型设计、枚举体系作为“设计参考”，代码全部重写，消除历史技术债务。

### 3.2. 后端

- **语言与环境**: Python 3.12，使用`PDM` 进行依赖管理。
- **框架**: `APIFlask`，**不**耦合`flask-sqlalchemy`，使用原生 SQLAlchemy 2.0。
- **数据库**: `SQLite` (开发环境)。
- **数据模型**: 使用 SQLAlchemy 2.0 声明式模型，定义为 Pydantic v2 `BaseModel`。
- **数据库操作**: 通过依赖注入 `get_db()` 获取会话，模型继承自 `Base`，不依赖 Flask 上下文。
- **迁移准备**: 代码风格和模型定义完全兼容未来向 `FastAPI` + `async SQLAlchemy` 的无痛迁移。
- **代码质量**:
  - 使用 `ruff` 替代 `isort` + `yapf`，统一进行 lint 和格式化。
  - 行宽：120
  - 目标 Python 版本：3.12

### 3.3. 前端

- **框架**:  `Vue 3` (使用`create vue`脚手架 + `Vite`)。
- **语言**:  `TypeScript`。
- **包管理**: `pnpm`。
- **UI库**:  `Element Plus`。
- **状态管理**: `Pinia`。

---

## 4. 核心数据模型设计

### 4.1. 统一持仓模型 (`positions`)

这是整个系统的核心。所有资产类型共用一个表，不再为不同类型资产单独建表。

**本模型继承自旧项目 `AccountTransactionRecord` 的设计思想，并做了适应“一张表”的调整。**

| 字段名 | 类型 | 约束 | 说明与示例 |
| :--- | :--- | :--- | :--- |
| `id` | Integer | PK, Auto | 系统内部唯一ID |
| `symbol` | String(50) | Not Null | **证券代码**，如 `AAPL`， `00700.HK` |
| `name` | String(100) | Optional | **证券名称**，如 `Apple Inc.`， `腾讯控股` |
| `market` | String(10) | Not Null | **所属市场**，枚举值继承自旧 `settings.py` 的 `SymbolTypeEnum`: `SH`, `SZ`, `HK`, `US` 等 |
| `type` | String(20) | Not Null | **资产类型**，枚举值继承旧 `SupportInvestCategoriesEnum`: `STOCK`, `ETF`, `BOND`, `FUND` |
| `account_name` | String(50) | Not Null | **所在账户名**，如 `华泰证券`， `富途牛牛` |
| `quantity` | Float | Not Null | 持仓数量 |
| `avg_price` | Float | Not Null | 平均成本价（以本币计） |
| `currency` | String(3) | Not Null | **本币种**，枚举值继承旧 `SupportCurrencyEnum`: `CNY`, `USD`, `HKD` 等 |
| `current_price` | Float | Default:0 | **当前市价**（用户手动更新） |
| `purchase_date` | Date | Not Null | 首次买入日期 |
| `notes` | Text | Optional | 用户备注，如“定投”，“转股中” |
| `created_at` | DateTime | Default: now | 创建时间 |
| `updated_at` | DateTime | OnUpdate: now | 最后更新时间 |

> **设计原则**：所有金额字段均为该资产原始币种。在应用层通过查询汇率表统一换算为人民币进行展示和计算。未来可预留`family_id`(Integer, Nullable)字段，用于家庭共享扩展。

### 4.2. 资产元数据模型 (分表存储)

#### 4.2.1. 通用证券信息 `securities`

适用于股票、ETF、可转债等标准化品种。
**继承自旧项目 `Fund` 模型的结构化思维，提取通用字段。**

| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | Integer, PK | 内部ID |
| `symbol` | String(50), Unique | 代码 (如 `AAPL`, `110047.SZ`) |
| `name` | String(200) | 名称 |
| `market` | String(10) | 市场 (`SH`, `SZ`, `HK`, `US`) |
| `type` | String(20) | 类型 (`STOCK`, `ETF`, `BOND`) |
| `exchange` | String(50) | 交易所 (如 `SSE`, `NASDAQ`) |
| `sector` | String(100) | 行业 (可选) |
| `industry` | String(100) | 子行业 (可选) |
| `is_active` | Boolean | 是否仍在交易 |

#### 4.2.2. 基金专属信息 `funds`

包含场外基金的独特属性。
**继承自旧项目 `Fund` 模型。**

| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | Integer, PK | 内部ID |
| `fund_code` | String(6), Unique | 基金代码 (如 `110022`) |
| `name` | String(30) | 基金简称 |
| `full_name` | String(40) | 基金全称 |
| `fund_type` | String(50) | 基金类型 (继承旧`FundType`设计) |
| `company` | String(200) | 基金公司 |
| `risk_level` | Integer | 风险等级 (继承旧 `RiskTypeEnum`) |
| `inception_date` | Date | 成立日期 |
| `management_fee` | Float | 管理费率 (P2) |
| `benchmark` | String(200) | 业绩基准 |

#### 4.2.3. 基金经理 `managers`

**完全继承自旧项目 `Manager` 模型。**

| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | Integer, PK | 内部ID |
| `name` | String(30) | 姓名 |
| `company` | String(200) | 所属公司 |
| `appointment_date` | Date | 任职日期 |
| `sum_scale` | Numeric | 管理规模 (亿元) |

#### 4.2.4. 基金-经理关联 `fund_manager_links`

**完全继承自旧项目 `FundManager` 中间表设计，实现多对多关系。**

| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | Integer, PK | 内部ID |
| `fund_id` | FK -> funds.id | 基金 |
| `manager_id` | FK -> managers.id | 经理 |
| `start_date` | DateTime | 开始管理日期 |
| `end_date` | DateTime | 结束管理日期 (Null表示现任) |
| `is_classic` | Boolean | 是否代表作 |

### 4.3. 交易记录模型 `transactions`

**完全继承自旧项目 `AccountTransactionRecord` 的设计思想，用于记录每一笔买卖、分红、存取款等操作。**
MVP阶段暂时不建表，但需预留此设计。

| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | Integer, PK | 内部ID |
| `position_id` | FK -> positions.id | 关联的持仓 |
| `op_type` | Integer | 操作类型 (继承旧 `FundOpTypeEnum`) |
| `amount` | Numeric | 交易金额 |
| `charge_fee` | Numeric | 手续费 |
| `launch_date` | DateTime | 发起日期 |
| `confirm_date` | Date | 确认日期 |
| `record_code` | String | 平台流水号 (用于对账) |
| `comment` | String | 复盘备注 |

---

## 5. 旧项目资产继承清单

此清单明确了旧项目中的优秀设计在新项目中的继承方式与位置。

### 5.1. 核心继承

| 旧项目模块 | 具体内容 | 继承方式 | 新项目位置 |
| :--- | :--- | :--- | :--- |
| `settings.py` | 所有业务枚举 (`RiskTypeEnum`, `FundOpTypeEnum`, `FeeTypeEnum`, `SupportCollectionsEnum` 等) | **100% 继承**，语法微调为 Pydantic 兼容 | `app/core/enums.py` |
| `settings.py` | `BaseTypeEnum` 和 `ChoiceTypeDk` 枚举基类体系 | **100% 继承** | `app/core/base_enum.py` |
| `fund/models.py` | `Fund` ↔ `Manager` 多对多关系 (中间表 `FundManager`) | **完全继承**数据关系设计，用 SQLAlchemy 2.0 重写 | `app/models/fund.py` |
| `fund/models.py` | `Fund.search_key()` 多字段模糊搜索逻辑 | **逻辑移植** | `app/services/fund_search.py` |
| `fund/models.py` | `FeeRatio` 费率体系 (`PurchaseRule`, `RedeemRule`) | 模型结构保留在 SPEC，MVP 暂不实现 | P2 功能 `app/models/fee.py` |
| `fund/models.py` | `FundPortfolio` 组合追踪体系 | 模型结构保留在 SPEC，MVP 暂不实现 | P2 功能 `app/models/portfolio.py` |
| `account/models.py` | `Account` 的“四笔钱”风险维度设计 | **理念继承**，简化模型 | `app/models/account.py` |
| `account/models.py` | `AccountTransactionRecord` 的完整交易字段 | **字段设计继承**，稍作调整 | `app/models/transaction.py` |
| `collection/models.py` | `Collection` + `Categories` + `Labels` 灵活自选体系 | **模型结构完全继承**，MVP 暂不建表 | P1 功能 `app/models/collection.py` |
| `user/models.py` | `User` 密码处理、`lookup()` 用户名/邮箱登录、Gravatar 头像 | **逻辑继承**，库替换为 `werkzeug.security` | `app/models/user.py` |
| `database.py` | `CRUDMixin` 通用数据库操作 | **思想继承**，升级为 `BaseRepository` | `app/database.py` |

### 5.2. 暂不继承 (但思想保留)

- `HandPick` 早期自选模型：已被 `Collection` 体系取代，不再使用。
- `Flask-Praetorian` 鉴权：因框架耦合和功能冗余，替换为手动 JWT。

---

## 6. API 设计 (契约)

### 6.1. 通用约定

- **Base URL**: `http://localhost:8000/api/v1`
- **鉴权**: MVP阶段暂无。未来通过JWT实现。
- **标准响应格式**:

  ```json
  // 成功
  { "data": { ... }, "message": "ok" }
  // 失败
  { "error": { "code": "...", "message": "..." } }
  ```

### 6.2. 核心接口 (MVP 必须)

| 方法 | 路径 | 描述 | 优先级 |
| :--- | :--- | :--- | :--- |
| `GET` | `/positions` | 获取用户所有持仓列表 | **P0** |
| `POST` | `/positions` | 创建一条新的持仓记录 | **P0** |
| `PUT` | `/positions/{id}` | 更新一条持仓记录（如更新`current_price`） | **P0** |
| `DELETE` | `/positions/{id}` | 删除一条持仓记录 | **P0** |
| `GET` | `/summary` | 获取首页仪表盘聚合数据（总资产、盈亏等）| **P0** |
| `POST` | `/upload` | 上传CSV/JSON文件并解析导入 | **P1** |

### 6.3. 核心业务逻辑

- **盈亏计算**: `unrealized_pnl` = (`current_price` - `avg_price`) * `quantity`。这个计算在数据查询或序列化时动态完成，不存储在数据库里。
- **币种换算**: 系统需维护一个汇率表。在展示总资产、总盈亏等聚合数据时，由后端统一换算为人民币（CNY）。

---

## 7. 前端核心功能与设计

### 7.1. 布局与导航 (MVP)

一个经典的“左侧导航 + 右侧内容”的响应式布局。

- **导航菜单**: `资产总览` (首页), `持仓明细`, `我的关注` (自选), `设置`。
- **移动端适配**: 后期通过响应式设计或底栏导航适配。

### 7.2. 页面功能说明 (MVP)

#### `资产总览` (Dashboard, P0)

- **顶部核心卡片**: `总资产(CNY)`, `当日/累计盈亏(CNY & %)`。
- **资产分布**: 饼图展示按市场(`market`)或类型(`type`)的资产分布。
- **持仓概览**: 展示前5-10条持仓记录，重点是盈亏。
- **我的关注 (轻量版)**: 紧随持仓，展示用户最关心的前5个自选标的。
  - **基金类自选必须显示基金经理姓名**。

#### `持仓明细` (Portfolio, P0)

- **完整列表**: 以表格形式展示所有持仓字段。
- **关键操作**:
  - **新增持仓**: 显眼的“+”按钮，弹出表单。
  - **更新市价**: 表格内快速编辑`current_price`字段，回车确认。
  - **数据导入**: 集成文件上传组件，支持CSV/JSON。
- **交互**: 支持按账户(`account`)、市场(`market`)、类型(`type`)、盈亏等维度进行**筛选和排序**。

#### `我的关注` (Watchlist, P1)

独立页面，承载完整自选功能。

- 以“标签页”形式对自选标的分类：`全部`, `股票`, `ETF`, `基金` 等。
- 提供更强的基金和基金经理追踪能力（MVP阶段后端先不做，仅做前端UI占位）。

#### `设置` (Settings, P1)

- 编辑汇率映射表（USD/CNY, HKD/CNY等）。
- 管理账户列表 (`accounts`)。

---

## 8. MVP 范围定义

### 8.1. MVP 必须完成 (四周目标，跑通核心闭环)

1. **后端**: 数据库表创建。`positions` 和 `currencies` 的 CRUD API 稳定运行。`summary` API 跑通。
2. **前端**: `资产总览`页和`持仓明细`页可用。
3. **闭环**: 用户能够在UI上新增一条持仓 -> 在列表中看到它 -> 更新它的当前价 -> 在首页看到总资产变化。
4. **部署**: 前后端能够分别在本地通过简单命令启动并通信。

### 8.2. MVP 暂不包含

- 用户鉴权与多用户。
- 复杂的数据导入（文件上传）只能手动调用后端接口，不做前端页面。
- `我的关注`的完整独立页面。
- 移动端完美适配。
- 复杂的图表交互。
- 家庭共享相关功能。

---
**本文档将作为项目开发的唯一事实标准。任何需求或实现的变更，都应先更新此文档，再修改代码。**

```
