## 📋 项目需求规格说明书

> **版本**: v2.0
> **最后更新**: 2026-05-10
> **状态**: MVP 核心闭环完成，P1 规划已确认。
> **核心原则**: 本项目为**个人使用、本地优先、完全合规**的投资记账工具。

---

### 1. 项目愿景与技术栈

#### 1.1. 我们要解决什么问题？
为个人投资者提供一个**安全、私密、可长期维护**的全资产记账与投资分析工具，回答两个核心问题：“我的钱都放在哪儿？”，“我的钱是怎么理得？”。

#### 1.2. 核心价值主张
- **绝对的数据主权**：所有数据存储在本地，不上传云端，用户完全掌控。
- **完全的合规性**：通过坚决的手动/文件导入方式录入数据，**永不**自动登录或爬取券商。
- **从记账到分析**：不仅记录交易，更能穿透底层、分析集中度、复盘年化，为行为提供优化建议。
- **全资产统一视图**：用一个简洁而灵活的数据模型，管理从股票基金到房产、负债甚至应收款的广义资产。

#### 1.3. 技术栈
- **后端**: Python 3.12+, APIFlask, SQLAlchemy 2.0 (原生), SQLite (开发)。
    - **原则**: 视图函数手动返回 `{ data, message }` 格式，不使用 `BASE_RESPONSE_SCHEMA`，确保未来平滑迁移 FastAPI。
- **前端**: Vue 3 + Vite + TypeScript, pure-admin-thin (骨架), Element Plus, ECharts。
- **代码质量**: 后端 `ruff`，前端遵循 pure-admin 内置规范。

---

### 2. 全局设计原则
- **数据合规与安全 (不可妥协)**
    - **[P0]** 支持用户手动在 Web 表单中逐条录入交易。
    - **[P1]** 支持用户上传标准格式的 CSV/JSON 文件，系统解析并导入。
    - **严禁**任何形式的自动登录、爬取券商等非法获取数据的行为。
- **设计与开发**
    - **“交易资产与非交易资产分离”**：可买卖的金融资产归 `positions`，更广义的资产/负债归 `assets`。
    - **API-First**：前后端严格遵循 API 契约。
    - **渐进式交付**：永远优先交付最小可用功能（MVP），再逐步丰满。
- **用户体验**
    - **30秒效率**：首页仪表盘 30 秒内掌握全局。
    - **分层信息架构**：高频操作入口浅，复杂分析可以深。
- **重构安全（不可妥协）**
    - 任何代码优化、重构、服务层抽取，**必须保证对外 API 的请求参数、响应结构、状态码、字段名完全不变**。
    - 前端依赖的接口契约（如筛选参数 `type`、`time_range`、`asset_type` 等）属于不可变部分，修改需同步更新前端并记录 breaking change。
---

### 3. 核心数据模型

#### 3.1. `positions` — 可买卖的金融资产
用于需要追踪成本与盈亏的交易性资产，如股票、ETF、可转债、基金、虚拟货币、银行存款等。

| 核心字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id`, `symbol`, `name`, `market`, `type` | - | 基本标识与分类 |
| `account_name` | String | **所属账户** |
| `quantity`, `avg_price` | Float | 持仓数量与成本价 |
| `currency`, `current_price` | String, Float | 本币种，当前市价（用户手动更新） |
| `purchase_date`, `notes` | Date, Text | 首个买入日期，备注 |
| `allocation` | String | **配置目标**（五笔钱） |
| `created_at`, `updated_at` | DateTime | 审计字段 |

> **设计原则**：所有金额字段均为原始币种。在应用层通过查询汇率表统一换算为人民币。

#### 3.2. `transactions` — 交易流水
记录所有买卖、分红、存取款等操作，用于复盘。

| 核心字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id`, `position_id` | - | 关联的持仓 |
| `type` | String | **操作类型**: buy, sell, dividend, deposit, withdraw |
| `trade_date` | Date | **交易发起日期 (T日)** |
| `quantity`, `price`, `fee`, `amount` | Float | 交易细节 |
| `status` | String | **交易状态**: success, failed, cancelled, pending |
| `position_name`, `account_name` | String | **快照字段**，上游删除后流水不丢失 |

#### 3.3. `assets` — 通用资产与负债
**核心扩展**。用于房产、汽车、应收款、负债、保险等非高频交易的资产/负债。

| 核心字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id`, `user_id` | - | 主键，`user_id` 为多用户预留 |
| `major_category` | String | **大类**: cash, fixed, receivable, liability, insurance |
| `minor_category` | String | **小类**: 自由定义 (如 mortgage, credit_card, car) |
| `name`, `amount`, `currency` | - | 资产名，当前价值，币种 |
| `status` | String | active / closed |
| `start_date`, `end_date` | Date | 生效与到期/还清日 |
| `extra` | JSON | **扩展属性** (如房产面积、借款人、保单号等) |

#### 3.4. 未来扩展 (P1)
- **`securities` / `funds` / `managers`**：股票/基金元数据表，用于前端远程搜索与基本信息展示。
- **`holding_details`**：基金穿透持仓明细（温数据），用于集中度分析与行业穿透。

---

### 4. 旧项目资产继承
本系统是旧 `fundmate` 项目思想的重构与延伸。以下设计已完全继承或记录在案：
- **`settings.py` 枚举体系**：所有 `BaseTypeEnum` 及其业务枚举已在新系统 `app/core/enums.py` 中 100% 继承。
- **`Fund ↔ Manager` M2M 关系**：已体现为 P1 规划的 `funds` 与 `managers` 表设计。
- **`FeeRatio` 费率体系**：作为 P2 规划，其核心字段已记录在 SPEC，待实现时直接复用。
- **`Collection` 自选体系**：完全的模型结构继承在 P1 规划中。

---

### 5. API 设计 (核心端点)

| 方法 | 路径 | 描述 | 关键特性 |
| :--- | :--- | :--- | :--- |
| `GET/POST` | `/api/positions` | 持仓 CRUD | **`POST` 为智能接口**：自动处理买入合并、卖出校验、流水生成。支持 `?group_by=account` |
| `PATCH,DELETE` | `/api/positions/{id}` | 更新/删除持仓 | `PATCH` 用于更新价格等字段 |
| `GET` | `/api/transactions` | 获取交易流水 | 支持多维筛选与分页 |
| `GET/POST` | `/api/assets` | 通用资产 CRUD | 支持按 `major_category` 筛选 |
| `PATCH,DELETE` | `/api/assets/{id}` | 更新/删除通用资产 | |
| `GET` | `/api/summary` | **仪表盘聚合数据** | 合并 `positions` 与 `assets`，返回总资产、总负债、净资产、总盈亏等 |

---

### 6. 架构演进 (P1 规划)

#### 6.1. 服务层抽取
- **目标**：将 `views.py` 中臃肿的业务逻辑抽取到服务层。
- **产出**：`app/services/position_service.py`
- **预期**：视图函数缩减到 10 行以内，只负责参数校验和服务调用。

#### 6.2. 通用工具封装
- **目标**：消除所有视图函数中重复的分页和数据处理代码。
- **产出**：`app/core/utils.py` 中的通用 `paginate()` 函数。

#### 6.3. 防腐层（数据提供者）
- **目标**：封装 xalpha 等外部数据源，避免业务逻辑与外部库直接耦合。
- **产出**：`app/services/data_provider.py` (统一对外提供基金、股票日线等数据)

---

### 7. xalpha 集成策略 (P1)
- **定位**：xalpha 是 ShowBuy 的数据获取与数学计算引擎，负责“感知市场”。
- **职责**：
    - 基金元数据、净值、持仓穿透的获取与缓存。
    - 提供日线、实时行情等数据，用于“一键刷新”等功能。
    - 作为 CSV 账单解析的辅助工具，生成标准交易记录。
    - 提供投资组合分析能力（年化、回撤、持仓穿透）。
- **边界**：
    - xalpha **不涉及**任何用户认证、数据库写入（除其自身缓存）、前端交互或 API 端点生成。
    - 所有写入我们 `positions`、`transactions` 的业务逻辑，完全由我们自己的 `services/` 层控制。

---

### 8. 穿透持仓分析 (P1)
- **数据分层**：采用“热-温-冷”数据分层架构。
    - **热数据**：`positions`、`transactions`，本地库内保障事务与 CRUD。
    - **温数据**：穿透持仓明细，定期缓存，设置过期时间。存储于 `holding_details` 表。
    - **冷数据**：海量历史行情，仅作回测，不进入主库。
- **`holding_details` 表**：关联 `fund_id`，存储报告期、底层标的代码/名称、占比、较上期增减。
- **工作流**：用户触发分析 → 检查缓存 → 若过期则调 xalpha 获取 → 存入 `holding_details` → 前端可视化。

---

### 9. P1 任务路线图

| 编号 | 任务 | 复杂度 | 依赖 |
| :--- | :--- | :--- | :--- |
| P1-01 | 业务逻辑抽取到 `position_service.py` | 中 | 无 |
| P1-02 | 分页函数通用封装 | 低 | 无 |
| P1-03 | CSV/JSON 文件导入（含 xalpha 辅助解析） | 中 | P1-01 |
| P1-04 | **建立股票/基金元数据表 (`securities` + `funds` + `managers`)** | 高 | 无 |
| P1-05 | **集成 xalpha 实现基金信息搜索、净值获取** | 高 | P1-04 |
| P1-06 | **记账表单“代码”输入框改为远程搜索** | 中 | P1-05 |
| P1-07 | 自选（关注）功能 | 高 | P1-04 |
| P1-08 | 记账弹窗重构为 Step 向导 | 中 | 无 |
| P1-09 | 数据导出（CSV/JSON 备份） | 低 | 无 |
| P1-10 | **仪表盘年化收益率计算（基于 xalpha 组合分析）** | 中 | 无 |
| P1-11 | **穿透持仓分析与存储 (`holding_details` 表)** | 高 | P1-05 |
| P1-12 | JWT 用户认证 | 中 | 无 |
| P1-13 | 移动端适配（PWA/响应式） | 高 | 无 |

---

### 10. 断点续传协议

**当会话达到上限时**，新会话中只需提供：
1.  **本 `SPEC.md` 文件**
2.  **当前进度一句话**，如：“MVP 完成，准备从 P1-01（业务逻辑抽取）开始”
3. 文件列表

| 文件                                       | 为什么需要                                 |
|------------------------------------------|---------------------------------------|
| backend/app/main.py                      | 蓝图注册全貌，知道有哪些模块                        |
| backend/app/core/database.py             | get_db 用法、Base 定义                     |
| backend/app/domains/positions/views.py   | 当前需要重构的核心文件                           |
| src/api/positions.ts + src/api/assets.ts | API 封装层，前端调用的函数名和参数                   |
| src/views/asset/AssetPanorama.vue        | 最重的页面，我需要知道 fetchData、sankeyData 等函数名 |

- 前端
| 文件                                             | 为什么需要                                                      |
|------------------------------------------------|------------------------------------------------------------|
| src/views/asset/AssetPanorama.vue              | 最重的页面，包含 fetchData、sankeyData、dimensionGroups、图表初始化等所有核心逻辑 |
| src/components/QuickEntry/TransactionModal.vue | 记账弹窗，包含动态表单、五笔钱、卖出级联选择等                                    |
| src/api/positions.ts                           | 持仓 API 封装，函数签名和参数结构                                        |
| src/api/assets.ts                              | 通用资产 API 封装                                                |
| src/api/transactions.ts                        | 交易流水 API 封装                                                |
| src/api/summary.ts                             | 仪表盘聚合 API 封装                                               |
| src/api/types.d.ts                             | TypeScript 类型定义，Position、SummaryData 等接口                   |
| src/views/account/AccountOverview.vue          | 账户总览页，含分页、行内编辑                                             |
| src/views/account/TransactionList.vue          | 交易流水页，含双视图和筛选                                              |
| src/router/modules/asset.ts                    | 资产相关路由配置，页面结构和导航映射                                         |

3.  **最新的报错截图或要解决的具体问题**
4. **重构时，必须先对照当前 views.py 的所有分支，确保新代码覆盖所有已有筛选/逻辑。**
---

**本文档是 ShowBuy 项目的唯一事实标准。所有后续开发决策，必须参照此文档。**
