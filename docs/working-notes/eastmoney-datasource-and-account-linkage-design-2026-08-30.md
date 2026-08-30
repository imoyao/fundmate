# 天天基金/东财数据源适配器 与 基金账户归一化设计（2026-08-30）

> 状态：设计草案（待评审，未写代码）。对应对话结论：① 数据源先出设计、确认结构后再动手；② 基金账户归一化到 `sales_institutions`，个人昵称保留自由文本。
> 关联：#1155 基金元数据架构回填（已确认）、`e-account-reconciliation-design-2026-08-16.md`、`sales-institution-common-group-2026-08-24.md`。

## 1. 背景与现状（代码实证）

用户提到的「头部数据」「MCP 抓取」「天天基金代码」经核查如下，均为已存在事实：

- **MCP 抓取**：项目已有 MCP **客户端**能力，但仅服务「且慢市场温度计」（`app/services/thermometer/fetchers.py:217` 走 `stargate.yingmi.com/mcp/v2`，`_mcp_post`/`_call_mcp` 完成 initialize→tools/call 握手）。无自建 MCP server，也未用于基金元数据。
- **天天基金代码**：分两条线。① `app/services/importer/parsers/tiantian_fund.py:25` 的 `TiantianFundParser` 解析用户粘贴的**交易明细 CSV**，纯本地、不抓外部数据；② 天天基金净值/基础资料实际来自东财，`akshare_adapter.py:200-229` 用 `ak.fund_name_em()` 拉全市场基金列表，xalpha 适配器直连东财公开接口（`xalpha_adapter.py:10-20`）。
- **「头部数据」= `fetch_fund_list()`**：全市场公募基金基础资料（代码/简称/类型），由 `ak.fund_name_em` 提供，是 enrich/类型/经理/净值的种子。代码库无「头部」字眼，对应即此 list。
- **数据源注册硬编码**：`DataSourceAdapter` 抽象基类（`adapters/base.py:13`，方法 `get_name/get_version/fetch_fund_list/fetch_fund_nav/fetch_fund_manager/fetch_stock_list/fetch_stock_price`）＋ orchestrator 硬编码注册表（`orchestrator.py:102-122` 注册 `xalpha`/`akshare`/`null`）。新增源无运行时选源开关。
- **基金账户现状**：`fund_account` 字段位于 `PositionImportMeta`（`positions/models.py:129`，注释「基金账户(平台侧账号)」），是自由文本；`positions` 主表只有 `source_broker`（`positions/models.py:52`）展示用字符串。`ledgers` 已通过 `sales_institution_id`（`ledgers/models.py:130-135`）关联销售机构；导入时 `_get_or_create_channel_ledger` 已做 `source_broker → SalesInstitution` 匹配（`importer/orchestrator.py:1226-1272`）。
- **基金公司 code bug**：`fund_list_job.py:60-64` 写 `FundCompany(name=name, code=name)`——用公司名顶替权威编码。`fund_companies` 表其实已有 `code` 唯一列（`funds/models.py:28`），权威来源是天天基金 `fund_company` 表（code 如 `80560408`、含 `full_name`/缩写 `TTJJ`）。

## 2. 设计 A：天天基金/东财数据源适配器

### 2.1 目标
把「天天基金/东财」提升为**一等数据源**（而非散落在 akshare/xalpha 适配器内部），提供干净的扩展点，并顺手回填基金公司权威 code。复用现有 proven 网络代码，不重写抓取。

### 2.2 落点与新模块
- 新增 `app/services/sync/adapters/eastmoney_adapter.py`：`class EastmoneyAdapter(DataSourceAdapter)`，复用 `ak.fund_name_em`（列表）与 xalpha 直连东财的模式（净值 `api.fund.eastmoney.com/f10/lsjz`、费率 `fund.eastmoney.com/f10/jjfl_{code}.html`）。
- 新增方法 `fetch_fund_company`（或并入 `fetch_fund_detail`）拉天天基金 `fund_company` 表：公司 code / `full_name` / 管理规模 `scale`，用于回填 `fund_companies`。

### 2.3 注册与「去硬编码」选源
当前 orchestrator 把 Job 写死绑定到具体适配器，这是扩展痛点。设计：
- `_register_data_sources()` 增加 `self.data_sources['eastmoney'] = EastmoneyAdapter()`（`orchestrator.py:104` 附近）。
- 引入**数据源偏好配置**（如 `app/core/config.py` 加 `SYNC__FUND_LIST_SOURCE` / `SYNC__FUND_DETAIL_SOURCE` 等，默认 `'eastmoney'`，回退 `'akshare'`），`_register_jobs()` 按配置取源而非写死。逐步把 `fund_list`/`fund_detail_enrich`/`fund_type`/`fund_manager` 切到 `eastmoney`；净值/行情暂保留 xalpha 直连（或一并迁）。
- 迁移策略：先双源并存（配置可切），回归测试通过后再把默认改为 `eastmoney`，最后择机下线 akshare 中重复的东财逻辑（保留 akshare 作为兜底 Tier）。

### 2.4 基金公司权威 code 回填（修 bug）
- `fund_list_job` 建 `FundCompany` 时，按公司名查天天基金 `fund_company` 表得到权威 `code`/`full_name`/`scale`；命中则写真值，未命中保留 `code=name` 占位（现状行为）并打告警，避免破坏既有唯一约束。
- `fund_companies` 已是市场域（`db_factory` 注册），适配器写市场域数据，无跨域问题。

### 2.5 分期
- P0：建 `EastmoneyAdapter`，实现 `fetch_fund_list`（委托 `ak.fund_name_em`）+ `fetch_fund_nav`/`fetch_fund_fee`（复用 xalpha 东财直连），注册并接入配置选源；`fund_list_job` 切到 `eastmoney`。
- P1：补 `fetch_fund_company`，回填 `fund_companies.code/full_name/scale`（修 `code=name` bug），含幂等回填脚本。
- P2：把 `fund_detail_enrich`/`fund_type`/`fund_manager` 迁到 `eastmoney`，akshare 降级为兜底。
- P3（远期）：若某源只暴露 MCP，复用 `thermometer/fetchers.py` 客户端模板加 MCP-backed fetcher，不建 server。

## 3. 设计 B：基金账户归一化到销售机构

### 3.1 目标与语义
把 `PositionImportMeta.fund_account`（平台侧账号自由文本）与权威销售机构关联，消除「硬编码字符串无外键」。结论（已与用户确认）：加 `sales_institution_id` 外键指向 `sales_institutions`，**个人昵称 `fund_account` 保留为自由文本**（如「我的基金账户」本就不命中任何机构名，不能作为外键）。

### 3.2 表结构变更
- `PositionImportMeta` 新增：
  `sales_institution_id = Column(Integer, ForeignKey('sales_institutions.id', ondelete='SET NULL'), nullable=True, comment='关联销售机构(AMAC 权威名录)')`。
- 域校验：`PositionImportMeta` 为 `FamilyScopedMixin`（user 域），`sales_institutions` 为 `DOMAIN_USER`（`db_factory.py:86`）——**同域外键，合规**（双引擎硬规则禁止跨域 FK，此处不触发）。
- `positions` 主表不新增该列：平台已可经 `positions.ledger_id → ledgers.sales_institution_id` 到达，避免冗余；如后续确需直查再议。

### 3.3 回填与写入路径
- 回填：对存量 `PositionImportMeta`，优先用已有 `source_broker` 走 `_get_or_create_channel_ledger` 的同款匹配（`org_name`→`display_name`）得 `SalesInstitution.id`；`source_broker` 为空时改从 `position.ledger_id → ledgers.sales_institution_id` 派生。`fund_account` 文本原样保留。
- 写入：导入建 `PositionImportMeta` 时（`importer/orchestrator.py:1538` 附近）顺带算 `sales_institution_id` 一并落库，复用现有匹配 helper，不重复造匹配逻辑。
- 迁移：SQLite `ALTER TABLE ADD COLUMN` 加可空列安全；回填脚本幂等（已非 NULL 跳过），放在 `backend/scripts/` 或作为一次性 job。

### 3.4 分期
- P0：加列 + 迁移 + 幂等回填脚本；`PositionImportMeta` 模型与对应 schema 同步更新（遵循 `conventions.md` §4.3 模型/字段变更须同步 Schema）。
- P1：导入路径写 `sales_institution_id`；`position_aggregation.py` 等聚合逻辑可改用外键替代字符串匹配。

## 4. 风险与未决
- 东财 WAF/限流：`core/requests_patch.py` 已全局 `impersonate chrome`，新增适配器无需重复加 UA/Referer；`akshare` 已设 `request_interval=3`，全量 list 偏慢。
- akshare 是否稳定提供 `fund_company` 权威 code：需实跑验证（P1 前先小批量核对 `db_data/fund_company.sql` 既有真实编码是否可由 akshare 复现）。
- 选源配置粒度：先做 list/detail 两级偏好，避免过度抽象。
- `fund_account` 与 `source_broker` 语义重叠：本设计明确 `source_broker`=平台展示名（可匹配机构），`fund_account`=个人账号昵称（不匹配），二者正交，不合并。

## 5. 验收标准
- A：存在 `eastmoney_adapter.py` 并注册；`fund_list_job` 经配置切到 `eastmoney` 后，`funds` 表数据与现 akshare 路径一致；`fund_companies.code` 不再等于 `name`（命中机构者写真值）。
- B：`PositionImportMeta` 有 `sales_institution_id` 列且存量回填完成；新导入的 `PositionImportMeta` 自动带 `sales_institution_id`；`fund_account` 自由文本保留。

## 6. 代码锚点索引
| 主题 | 位置 |
|---|---|
| MCP 客户端（仅温度计） | `app/services/thermometer/fetchers.py:217,225,238`；`constants.py:37-40` |
| 天天基金交易 CSV 解析器 | `app/services/importer/parsers/tiantian_fund.py:25` |
| 东财基金列表（akshare） | `app/services/sync/adapters/akshare_adapter.py:200-229` |
| 东财直连（xalpha） | `app/services/sync/adapters/xalpha_adapter.py:10-20` |
| 适配器抽象基类 | `app/services/sync/adapters/base.py:13` |
| 数据源注册表 | `app/services/sync/orchestrator.py:102-122` |
| 基金公司 code bug | `app/services/sync/jobs/fund_list_job.py:60-64` |
| 基金公司模型 | `app/domains/funds/models.py:25-32` |
| 销售机构模型 | `app/domains/positions/models.py:166-191`；AMAC 同步 `jobs/amac_institution_job.py` |
| 账本销售机构外键 | `app/domains/ledgers/models.py:130-135` |
| 持仓来源平台字段 | `app/domains/positions/models.py:52` |
| 导入溯源 meta 基金账户 | `app/domains/positions/models.py:129` |
| 导入匹配销售机构 | `app/services/importer/orchestrator.py:1226-1272` |
