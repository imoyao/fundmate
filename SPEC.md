## 📋 项目需求规格说明书 (ShowBuy)

> **版本**: v3.0
> **最后更新**: 2026-05-13
> **状态**: P1 核心模块推进中。
> **核心原则**: 本项目为**个人使用、本地优先、完全合规**的投资记账工具。

---

### 1. 项目愿景与技术栈

#### 1.1. 我们要解决什么问题？
为个人投资者提供一个**安全、私密、可长期维护**的全资产记账与投资分析工具，回答两个核心问题：“我的钱都放在哪儿？”，“我的钱是怎么理的？”。

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
- **数据源**: xalpha (基金净值与分析) + AKShare (补充备用)，通过 `DataProvider` 防腐层统一调用。

---

### 2. 全局设计原则

- **数据合规与安全 (不可妥协)**
    - 必须支持用户手动在 Web 表单中逐条录入交易。
    - 应当支持用户上传标准格式的 CSV/JSON 文件，系统解析并导入。
    - **严禁**任何形式的自动登录、爬取券商等非法获取数据的行为。
- **设计与开发**
    - **“交易资产与非交易资产分离”**：可买卖的金融资产归 `positions`，更广义的资产/负债归 `assets`。
    - **API-First**：前后端严格遵循 API 契约。
    - **渐进式交付**：永远优先交付最小可用功能（MVP），再逐步丰满。
- **用户体验**
    - **30秒效率**：首页仪表盘 30 秒内掌握全局。
    - **分层信息架构**：高频操作入口浅，复杂分析可以深。
- **重构安全 (不可妥协)**
    - 任何代码优化、重构、服务层抽取，**必须保证对外 API 的请求参数、响应结构、状态码、字段名完全不变**，新增字段须保持向后兼容。
    - 前端依赖的接口契约（如筛选参数 `type`、`time_range`、`asset_type` 等）属于不可变部分，修改需同步更新前端并记录 breaking change。
- **测试完整性 (不可妥协)**
    - 新接口或重构后的接口必须覆盖主要业务场景的自动化测试（创建、查询、更新、删除、边界错误），并覆盖核心逻辑分支（筛选、分页、操作类型、状态码）。
    - 修改接口行为必须同步更新对应的测试。
- **URL 与 RESTful 规范 (不可妥协)**
    - 所有 API 端点必须使用尾部斜杠（例：`/api/positions/`），前后端及测试保持一致，避免 308 重定向。
    - 资源 URL 使用复数名词（如 `/items/`、`/groups/`），嵌套资源体现层级关系（如 `/items/{item_id}/groups/{group_id}/`）。
    - 动作通过 HTTP 方法表达，URL 中不使用动词。
- **命名规范 (不可妥协)**
    - 模型类名必须包含领域前缀（如 `WatchlistItem`），避免跨模块名称冲突。
    - 视图函数参数禁止单字母缩写，必须见名知意（如 `item_id`、`group_id`）。
    - Schema 类名与领域模型严格对齐，输入输出后缀明确区分（`Create` / `Update` / `Out`）。
    - 蓝图变量名需体现所属领域（如 `watchlist_bp`、`funds_bp`）。
- **第三方库引入规范**
    - 引入新库时必须先阅读其官方文档或可靠案例，只调用库真正支持的接口，禁止编造不存在的函数或参数。
    - 若发现接口行为与预期不符，应立即回退到已知可用的版本或替代方案。
- **工具库与模型测试规范**
    - 新建的工具库、数据转换器等必须编写覆盖所有预设边界的测试用例（正常输入、异常输入、边界值、空值等），并在提交前全部通过。

### 开发教训与准则（持续更新）

> 本章节记录实际开发中因错误做法导致的重大返工，以及对应的正确实践，作为团队协作的强制规范。

#### 1. 测试失败时：系统诊断 > 盲目猜测
- **错误做法**：测试失败后，直接猜测问题原因（“可能是字段名没改”、“可能是旧函数残留”），反复修改代码却一直失败。
- **正确做法**：
  1. 在 fixture 中打印数据，确认数据确实已插入数据库。
  2. 在视图函数中打印查询结果，确认数据库是否为空。
  3. 检查 Flask 路由表，确认端点是否正确注册。
  4. 根据诊断输出精确定位问题，再修改代码。
- **准则**：**永远不要在没有看到实际数据的情况下猜测问题原因。必须通过日志、打印、路由检查等手段获取事实依据。**

#### 2. 测试数据库隔离：统一使用 `conftest.py` 的 `db` fixture
- **错误做法**：测试 fixture 直接导入 `SessionLocal`，导致使用了文件数据库；视图函数通过 `monkeypatch` 后的 `TestSessionLocal` 使用内存数据库，两者数据不互通。
- **正确做法**：
  - 所有涉及数据库操作的测试 fixture 和测试函数，必须接收并使用 `conftest.py` 提供的 `db` fixture。
  - `conftest.py` 中必须使用 `StaticPool` 确保 SQLite 内存数据库的单例模式，`monkeypatch` 替换全局引擎和会话工厂。
  - **禁止**在测试文件中直接导入 `SessionLocal` 进行数据库操作。
- **准则**：**测试数据与视图函数必须操作同一个数据库实例，否则所有测试都是无效的。**

#### 3. 模型字段变更必须同步更新 Schema
- **错误做法**：新增或重命名模型字段（如 `bookmarked` → `favorite`）后，忘记更新对应的 Pydantic Schema，导致 API 返回的 JSON 缺少该字段，前端或测试报错。
- **正确做法**：
  - 修改模型字段后，立即检查所有相关的 Pydantic 输出 Schema（`*Out`），确保字段列表完全一致。
  - 可考虑编写自动化对比测试，验证 Schema 字段与模型列的匹配度。
- **准则**：**模型字段变更 = Schema 字段同步变更，二者必须同时完成并立即验证。**

#### 4. 重构后必须全局清理残留代码
- **错误做法**：重命名函数或字段后，旧版本代码未彻底删除，导致路由冲突或数据不一致。
- **正确做法**：
  - 重构完成后，立即使用全局搜索（`bookmark`、`toggle_bookmark` 等）检查是否存在残留引用。
  - 删除所有旧函数、旧装饰器、旧导入语句。
- **准则**：**重构完成 ≠ 工作结束，必须确保“旧世界”彻底消失。**

#### 5. 前端 API 封装与组件调用统一
- **经验**：所有后端 API 调用必须封装在 `src/api/` 目录下的对应文件中，禁止在 Vue 组件中直接使用 `http.request`。组件只调用封装好的 API 函数，并使用其返回的类型定义。
- **准则**：**前端数据获取层与视图层严格分离，API 变更时只需修改一处。**

#### 6. 数据库变更必须重建表结构
- **经验**：SQLite 不支持直接重命名列，若修改字段名，必须删除旧数据库文件（或执行 ALTER TABLE）并重新初始化。测试环境中应自动使用内存数据库，确保无残留。
- **准则**：**模型字段变更后，立即删除开发数据库文件并重启应用，或执行等效迁移操作。**
---

### 3. 核心数据模型

#### 3.1. `positions` — 可买卖的金融资产
用于需要追踪成本与盈亏的交易性资产，如股票、ETF、可转债、基金、虚拟货币、银行存款等。

| 核心字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id`, `symbol`, `name`, `market`, `asset_type` | - | `type` 字段因 Python 关键字冲突已重命名为 `asset_type`，API 层映射为 `type` |
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
| `txn_type` | String | **操作类型**: buy, sell, dividend, deposit, withdraw（`type` 已重命名） |
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
| `minor_category` | String | **小类**: 自由定义 |
| `name`, `amount`, `currency` | - | 资产名，当前价值，币种 |
| `status` | String | active / closed |
| `start_date`, `end_date` | Date | 生效与到期/还清日 |
| `extra` | JSON | **扩展属性** (如房产面积、借款人、保单号等) |

#### 3.4. 证券与基金元数据

- **`securities`** — 交易性金融产品（股票、ETF、可转债等），存储标准化代码 `symbol`（如 `SH600519`、`HK00700`）。
- **`funds`** — 场外基金，含基金代码、名称、拼音缩写、类型、公司、风险等级等。
- **`fund_companies`** — 基金公司。
- **`fund_types` / `fund_varieties`** — 基金小类/大类。
- **`fund_sales_orgs`** — 销售机构。
- **`managers`** — 管理人（基金经理/组合主理人），通过 `mgr_type` 区分类型。
- **`fund_managers`** — 基金与经理多对多关联。
- **`daily_worth`** — 基金每日净值。

#### 3.5. 自选与关注体系 (P1)

- **`WatchlistItem`** — 自选资产条目，状态由 `positions` + `transactions` 动态推导。
- **`WatchlistGroup`** — 自选分组（系统分组动态渲染，自定义分组落库）。
- **`WatchlistItemGroup`** — 资产与分组关联。
- **`WatchlistTagDef`** — 标签定义。
- **`WatchlistItemTag`** — 资产与标签关联。
- **`WatchlistAlert`** — 异动提醒。
- **`ClearedPosition`** — 清仓仓位快照，支撑清仓分析。

#### 3.6. 数据存储与扩展 (P1-P2)

- **`price_history`** — 证券/基金历史价格（收盘价/单位净值），支撑收益日历和资产走势图。
- **`benchmark_indices`** — 基准指数日线数据（如沪深300），支撑复盘对比。
- **`user_preferences`** — 用户偏好设置（默认基准、主题等），核心字段独立列，扩展属性用 JSON。
- **`review_notes`** — 复盘笔记，按周期关联。

#### 3.7. 符号标准化

所有证券代码统一通过 `StockCodeNormalizer` 标准化为 `{MARKET}{CODE}` 格式（如 `HK00700`、`SH600519`、`US:AAPL`），支持多格式输入自动识别和补零。xalpha、AKShare 等外部数据源通过 `to_xalpha_code()` 等方法转换。

---

### 4. 旧项目资产继承
本系统是旧 `fundmate` 项目思想的重构与延伸。以下设计已完全继承或记录在案：

- **枚举体系**：100% 继承至 `app/core/enums.py`。
- **`Fund ↔ Manager` M2M 关系**：已在 `funds` / `managers` 表中实现。
- **`FeeRatio` 费率体系**：P2 规划，核心字段已记录。
- **`Collection` 自选体系**：重构为 `watchlist` 模块，设计理念完整继承。

---

### 5. API 设计 (核心端点)

| 方法 | 路径 | 描述 |
| :--- | :--- | :--- |
| `GET/POST` | `/api/positions/` | 持仓 CRUD，POST 为智能接口 |
| `PATCH,DELETE` | `/api/positions/{id}/` | 更新/删除持仓 |
| `GET` | `/api/transactions/` | 交易流水（多维筛选+分页） |
| `GET/POST` | `/api/assets/` | 通用资产 CRUD |
| `PATCH,DELETE` | `/api/assets/{id}/` | 更新/删除通用资产 |
| `GET` | `/api/summary/` | 仪表盘聚合数据 |
| `GET` | `/api/funds/search/` | 基金搜索 |
| `GET` | `/api/funds/managers/search/` | 经理搜索 |
| `GET` | `/api/securities/search/` | 证券搜索 |
| `GET/POST` | `/api/watchlist/items/` | 自选资产列表/添加 |
| `PATCH/DELETE` | `/api/watchlist/items/{item_id}/` | 更新/删除自选资产 |
| `GET/POST` | `/api/watchlist/groups/` | 分组列表/创建 |
| `PATCH/DELETE` | `/api/watchlist/groups/{group_id}/` | 更新/删除分组 |
| `POST/DELETE` | `/api/watchlist/items/{item_id}/groups/{group_id}/` | 资产与分组关联 |
| `GET/POST` | `/api/watchlist/tags/` | 标签列表/创建 |
| `DELETE` | `/api/watchlist/tags/{tag_id}/` | 删除标签 |
| `POST/DELETE` | `/api/watchlist/items/{item_id}/tags/{tag_id}/` | 资产与标签关联 |

---

### 6. 架构演进与 P1 路线图

#### 6.1. 架构演进目标

- **服务层抽取**：`app/services/position_service.py` 已完成，视图函数控制在 10 行左右。
- **通用工具封装**：`app/core/utils.py` 中的 `paginate()` 已用于全部列表接口。
- **防腐层**：`app/services/data_provider.py` 封装 xalpha + AKShare，支持重试与反爬策略。
- **符号标准化**：`app/core/symbol_utils.py` 统一处理多市场代码。

#### 6.2. P1 任务路线图 (更新于 2026-05-13)

| 编号    | 任务                          | 状态     | 备注                         |
|-------|-----------------------------|--------|----------------------------|
| P1-01 | 业务逻辑抽取到 position_service.py | ✅ 完成   | 测试通过                       |
| P1-02 | 分页函数通用封装                    | ✅ 完成   | paginate 已用于多模块            |
| P1-04 | 股票/基金元数据表 + 搜索 + 标准化        | ✅ 完成   | 模型、API、测试均已就绪              |
| P1-05 | xalpha 集成（净值、行情）            | ✅ 基本完成 | 数据同步可用，需完善定时任务             |
| P1-06 | 记账表单远程搜索                    | ✅ 完成   | 前端搜索下拉已接入                  |
| P1-07 | 自选功能（资产、分组、标签、特别关注）         | ✅ 完成   | 模型、API、前端页面、测试均已通过         |
| P1-03 | 全面盘点页面（CSV导入/去重）            | ⏸️ 未开始 |                            |
| P1-08 | 特别关注页面（诗句、卡片流）              | ✅ 完成   | 路由 /the-road-not-taken 已创建 |
| P1-09 | 清仓分析模块                      | ⏸️ 未开始 |                            |
| P1-10 | 年化收益率计算（依赖价格历史）             | ⏸️ 未开始 |                            |
| P1-11 | 基金经理跟踪                      | ⏸️ 未开始 |                            |
| P1-12 | 数据导入导出增强                    | ⏸️ 未开始 |                            |
| P1-13 | 移动端适配（PWA/响应式）              | ⏸️ 未开始 |                            |


**当前里程碑**：元数据体系与自选后端 API 完成，xalpha 数据通道畅通。下一步聚焦自选前端页面与数据层扩展（`price_history` 表），为复盘模块积累历史数据。

---

### 7. xalpha 集成策略

- **定位**：xalpha 是 ShowBuy 的数据获取与数学计算引擎，负责“感知市场”。
- **职责**：
    - 基金元数据、净值、持仓穿透的获取与缓存。
    - 提供日线、实时行情等数据，用于“一键刷新”等功能。
    - 作为 CSV 账单解析的辅助工具，生成标准交易记录。
    - 提供投资组合分析能力（年化、回撤、持仓穿透）。
- **边界**：
    - xalpha **不涉及**任何用户认证、数据库写入（除其自身缓存）、前端交互或 API 端点生成。
    - 所有写入 `positions`、`transactions` 的业务逻辑，完全由 `services/` 层控制。
- **缓存策略**：使用 CSV 后端缓存，路径 `data/xalpha_cache/`，与业务数据库物理隔离。
- **分析功能保留**：`CBCalculator`、`QDIIPredict`、`mul` 等特色分析模块通过 `app/services/xalpha_analysis.py` 封装调用。

---

### 8. 穿透持仓分析 (P1)
- **数据分层**：采用“热-温-冷”数据分层架构。
    - **热数据**：`positions`、`transactions`，本地库内保障事务与 CRUD。
    - **温数据**：穿透持仓明细，定期缓存，设置过期时间，存储于 `holding_details` 表。
    - **冷数据**：海量历史行情，仅作回测，不进入主库。
- **`holding_details` 表**：关联 `fund_id`，存储报告期、底层标的代码/名称、占比、较上期增减。
- **工作流**：用户触发分析 → 检查缓存 → 若过期则调 xalpha 获取 → 存入 `holding_details` → 前端可视化。

---

### 9. 断点续传协议

**当会话达到上限时**，新会话中只需提供：
1.  **本 `SPEC.md` 文件**
2.  **当前进度一句话**，如：“P1-07 自选 API 完成，正准备开发前端页面”
3.  **关键文件清单**：

| 文件 | 为什么需要 |
|------|------------|
| `backend/app/main.py` | 蓝图注册全貌 |
| `backend/app/core/database.py` | Base 定义、get_db |
| `backend/app/core/symbol_utils.py` | 代码标准化 |
| `backend/app/services/data_provider.py` | 数据获取防腐层 |
| `backend/app/domains/positions/views.py` | 核心交易接口 |
| `backend/app/domains/watchlist/models.py` | 自选模型 |
| `backend/app/domains/watchlist/views.py` | 自选 API |
| `src/api/positions.ts` | 前端持仓 API |
| `src/api/watchlist.ts` | 前端自选 API |
| `src/components/QuickEntry/TransactionModal.vue` | 记账弹窗 |
| `src/views/asset/AssetPanorama.vue` | 资产全景页 |

4.  **最新的报错截图或要解决的具体问题**

---

**本文档是 ShowBuy 项目的唯一事实标准。所有后续开发决策，必须参照此文档。**
