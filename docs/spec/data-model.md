---
title: 核心数据模型完整规范（data-model）
---

# 核心数据模型完整规范（data-model）

本文件收录核心数据模型完整规范（原 SPEC 第 5 章），属于**随代码演进**的事实标准。模型字段以 `backend/app/domains/*/models.py` 为准；本节描述关键字段与设计意图。

## 1. 核心数据模型完整规范（原 SPEC 第 5 章）

### 5.1 positions 可交易持仓资产

核心存储用户股票、基金、ETF 持仓，记录成本、数量、配置目标、归属账户，是收益计算、配置分析的核心数据源。关键字段：symbol、name、market、asset_type、account_name、quantity、avg_price、current_price、confirm_date、allocation、snapshot 相关审计字段。

**精度规范**（v4.4）：`quantity` 为 Integer，存储最小份额单位（份×10000）；`avg_price` 和 `current_price` 为 Integer，存储分（元×100）。所有读写通过 `Money` 工具类转换。

### 5.2 transactions 交易流水

存储每一笔买入、卖出、分红、定投记录，保留 position_name、account_name 快照。新增 `symbol` 字段作为资产代码快照（不可更改），新增 `asset_type` 字段作为资产类型快照，用于过滤和统计。目的：持仓删除后，历史流水不丢失，保证复盘数据永久可追溯。

| 字段 | 类型 | 说明 |
|------|------|------|
| symbol | String(30) | 资产代码快照，不可更改，用于关联查询和盈亏曲线 |
| asset_type | String(20) | 资产类型快照，用于过滤和统计 |
| position_name | String(100) | 持仓名称快照 |
| account_name | String(100) | 账户名称快照 |

**精度规范**（v4.4）：`price`、`amount`、`fee` 为 Integer，存储分；`quantity` 为 Integer，存储最小份额单位。

### 5.3 assets 通用资产负债表

承载全量非交易资产与负债，是资产全景视图的底层支撑。核心区分：amount（用户原始录入正数）、signed_amount（系统计算唯一统计字段）。负债统一归入此类，不进入持仓体系。

**精度规范**（v4.4）：`amount` 为 Integer，存储分。

### 5.4 金融元数据体系

securities、funds、fund_companies、managers、fund_managers、daily_worth 全套基础金融数据，支撑搜索、行情刷新、净值获取、持仓穿透。

**精度规范**（v4.4）：`daily_worth.unit_nav` 和 `acc_nav` 改为 `DECIMAL(18,6)`，避免浮点误差。

#### 5.4.1 基金公司主数据（fund_companies）语义与不变式

**表定位**（market 域）：`FundCompany` 承载基金公司主数据，东财链路提供基础身份、AMAC 链路提供权威全称。

| 字段 | 语义 |
|------|------|
| `code` | 东财 `jjjz_gs` 8 位代码 |
| `name` | **简称**（界面默认展示） |
| `full_name` | **AMAC 权威全称** |
| `register_addr` / `office_addr` / `website` / `phone` / `is_active` | 来自 AMAC |

> 死表 `fund_management_companies` 已并入本表并 DROP，禁止再登记或引用。

**写入权归属（硬约束）**

- **唯一写入口**：`services/sync/company_resolver.get_or_create_fund_company()`，由 4 个同步 job 共用。禁止各 job 自行构造 `FundCompany(name=...)`。
- 配套函数：`normalize_company_name` / `company_business_family` / `match_fund_company`。
- **不变式**：全仓**只有 1 处**写 `fund_companies.name`（建行时，无 UPDATE）→ 同步只建行、绝不改存量行；形态修复必须走显式脚本。
- 字段写权分离：`name` / `code` / `scale` 归东财链路；`full_name` 与 AMAC 字段**仅 AMAC job 写**。

**身份解析（`resolve_company_identity()`）**

返回「（东财 code, 东财简称）」，匹配顺序：手动映射 → 东财原文名精确 → **归一化名 + 业务族**。

> **归一化键必须带业务族**：东财名录含券商资管，若只按名称归一，会让「招商基金」与「招商证券资管」（同为键 `招商`）互相取错 code。

**归并规则**

- 简称行与全称行的**名称键永远收敛不了**（中邮 / 东方红 / 中银 / 浦银），典型形态是「简称行持经理、全称行持基金」。
- 因此归并**必须用 code 兜底**；合并时须把冗余行的 AMAC 字段提升到规范行，否则会随冗余行 DROP 一起丢失。

**与持仓链路的衔接**

- E 账户导入**以 6 位基金代码定身份**；导入文件中的「基金名称」只落 `positions.name`（纯展示），「销售机构」经 `source_broker` 路由到 `sales_institution_id`。
- **持仓 → 公司**链路：`positions.symbol → funds.fund_code → funds.company_id → fund_companies`，**不经过 fund_manager**。

**已知设计态与遗留**

- `position_import_meta.fund_manager` **全为 NULL 属设计使然**（影子记录的唯一匹配键 + 部分索引；归因到渠道后按设计置 NULL）。原值不可回溯（已扫遍 16 个库与备份）→ **「补 fund_manager FK」一项应取消**。
- `fund_list_job` 对 `company_id` 的贡献**恒为 0**：`ak.fund_name_em()` 不返回公司名，其公司处理分支为死代码，且该 job 只增不改（docstring 谎报，见 #1402）。这是公司覆盖率仅 11% 的成因。
- #1386 遗留：`中科沃土基金管理有限公司` 占位行**已拍板保留**；`国联证券资产管理` / `众盈基金` 无 AMAC 全称可用。
- **直销 vs 代销**：基金管理人直销自家产品无需另行取得销售牌照（证监会令第175号第八条）→ **直销 = 基金公司本体**；独立成行的是基金公司设立的销售子公司（9 家）。当前**不建**「销售机构 ↔ 基金公司」关联表。

**相关符号命名空间**：基金经理 `MGR_<mgr_code>`，投顾组合为平台原生码（`ZHxxxx` / `CSIxxxx`）。回查须**大小写不敏感**——实测 `managers.mgr_code` 存小写，等值匹配必漏查。

### 5.5 自选关注体系

分组、标签、资产关联、异动提醒、清仓持仓快照，支撑用户自定义资产监控体系。

### 5.6 数据分析扩展模型

price_history 历史行情、benchmark_indices 基准数据、user_preferences 用户偏好、review_notes 复盘笔记，为年化、回撤、对比回测提供数据底座。

### 5.7 代码标准化工具

所有市场代码统一归一化，自动识别沪/深/港/美基金代码，统一格式后再请求数据源，避免多格式导致的数据丢失。**注意：基金代码（6 位纯数字且 asset_type=fund）不进行标准化，直接保留原代码。**

### 5.8 费率与规则模型

#### 5.8.1 purchase_rules（申购费率规则）

存储按金额区间的申购/认购费率阶梯。关键字段：start_quota（起始金额，包含）、end_quota（结束金额，不包含，NULL 表示正无穷）。**精度规范**（v4.4）：`start_quota`、`end_quota` 为 Integer，存储分。

#### 5.8.2 redeem_rules（赎回费率规则）

存储按持有天数区间的赎回费率阶梯。关键字段：start_day（起始天数，包含）、end_day（结束天数，不包含，NULL 表示正无穷）。

#### 5.8.3 fee_ratios（基金费率关联表）

关联基金与费率规则，存储具体费率值。关键字段：fund_code、fee_type（purchase/redeem/management）、rate（费率百分比）、fee_amount（固定金额，与 rate 互斥）、purchase_rule_id、redeem_rule_id。**精度规范**（v4.4）：`rate` 改为 `DECIMAL(10,6)`，`fee_amount` 改为 Integer 存储分。

**设计要点**：

- 相同区间的规则被多只基金复用，减少冗余。
- 创建规则前先查询是否已存在完全相同的规则，存在则复用，不存在则新增。
- 修改规则时检查引用计数：引用数 > 1 时创建新规则，引用数 = 1 时可原地修改。

### 5.9 基金表新增字段

- `is_active`：是否参与净值同步，默认 True。连续失败 3 次后自动标记为 False。
- `last_nav_check`：最后一次净值检查时间。
- `nav_fail_count`：连续获取净值失败次数。
- `pinyin_abbr`：拼音首字母简拼（仿天天基金规则），用于搜索。

### 5.10 货币基金独立净值模型

#### 5.10.1 money_fund_daily_worth（货币基金每日万份收益）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| fund_code | String(6) | 基金代码 |
| date | Date | 日期 |
| nav_per_10k | **Integer** | 万份收益（分） |
| annual_return_7d | Float | 七日年化收益率（暂不计算），精度校验 round(value, 4) |

**万份收益计算**：从 `xalpha.mfundinfo().price` 的累计净值反向计算 `(今日累计净值 - 昨日累计净值) × 10000`，四舍五入保留 4 位小数。

**设计原因**：

- 货币基金无单位净值概念，与普通场外基金的数据结构完全不同。
- 混合存储会导致字段语义混乱，影响后续收益率计算和统计。
- 独立建表可复用普通基金的去重、分批写入等基础设施。

**精度规范**（v4.4）：`nav_per_10k` 改为 Integer 存储分。`annual_return_7d` 保留 Float，但写入前强制 `round(value, 4)` 控制精度。

### 5.11 投资组合 (Portfolio)（目标态设计定稿 2026-08-24，D20；分期实施中）

**设计定位**：回答"我的钱按什么策略投资"。组合是**持仓级**概念：用户按投资目的（稳健/进取/养老等）将持仓划入不同组合，与渠道解耦——同一账户（如支付宝）内的持仓可分属不同组合。与 Ledger（账户：钱放哪里）和 Allocation（五笔钱：风险等级）互补。

**核心约束（D20 修订，废除旧「不拆分持仓」约束）**：

- 组合成员 = 持仓：一个持仓最多归属一个组合（多对一）；同一账户内的持仓可分属不同组合。
- 账户绑定降级为「默认组合」：`ledgers.portfolio_id` 语义 = 新建持仓未显式指派时的继承默认值，不再是组合成员资格的判定依据。
- 渐进暴露，默认隐藏入口，不侵入记账主流程（不变）。

**三层 XIRR 口径**：

| 层 | 口径 | 状态 |
|----|------|------|
| 持仓 XIRR | 单持仓现金流归因 | ✅ 已实现（`calculate_position_xirr`） |
| 账户/Ledger XIRR | 账户现金流合并 | ✅ 已实现（performance 域） |
| 组合 XIRR | 组合内持仓的现金流归因（分红/费用/内部划转规则见实施计划） | 📦 二期；过渡期组合详情页 XIRR 区块隐藏，避免展示旧口径数字 |

#### 5.11.1 portfolios 表（已实现，字段不变）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| name | String(100) | 组合名称（必填） |
| description | String(500) | 组合描述 |
| purpose | String(200) | 投资目的，如"养老金"（原 Objective 概念降级并入） |
| target_return | Numeric(5,2) | 年化目标收益率（%） |
| target_amount | Numeric(15,2) | 目标金额 |
| target_date | Date | 目标日期 |
| benchmark | String(50) | 基准指数（如 CSI300） |
| is_deleted | Boolean | 软删除标记（默认 False） |
| created_at / updated_at | DateTime | 时间戳 |

> 注：原计划中的 `risk_level` 字段已移除，`purpose` 已能表达风险偏好，避免概念重叠。

#### 5.11.2 持仓与账户的组合绑定（🚧 一期实施中）

| 表.字段 | 类型 | 说明 |
|--------|------|------|
| `positions.portfolio_id` | Integer (FK)，nullable | 持仓所属组合；NULL = 继承账户默认组合（🚧 一期新增，存量回填 = 所属账户的组合） |
| `ledgers.portfolio_id` | Integer (FK) | 语义调整为「默认组合」：新建持仓未显式指派时继承；`ON DELETE SET NULL`（已实现） |
| `ledgers.linked_cash_ledger_id` | Integer (FK) | 关联的现金账户（仅 stock/fund 类型可用），`ON DELETE SET NULL`（已实现，不变） |

**注**：原计划添加的 `objective` 字段已移除，语义与 `Portfolio.purpose` 重叠，精简模型。

**聚合口径变更（一期）**：组合持仓聚合从「按关联账户取全部持仓（历史实现按 `account_name` 字符串匹配，存在改名断链/重名串仓隐患）」切换为「按 `positions.portfolio_id` 直接归属」，账户名匹配隐患随一期修复。

#### 5.11.3 策略标签（持仓风格分析）（已实现，定位微调 D20）

**设计定位**：纯展示层分析工具，用于按投资**风格**（如"成长""价值""大盘"）分类查看持仓——与组合的「目的」维度（稳健/进取/养老）正交：风格回答"持仓是什么类型"，组合回答"这笔钱为什么而投"。不参与 XIRR 计算。是否将风格标签并入组合体系 → 三期评估（D20）。

**数据模型**：

- `strategy_tags` 表：`id / name（UNIQUE）/ created_at`
- `position_strategy_tags` 关联表：`position_id (FK → positions.id, ON DELETE CASCADE) / strategy_tag_id (FK → strategy_tags.id, ON DELETE CASCADE)`，联合唯一约束
- 与自选标签物理隔离，互不干扰

**API 端点**：

- `GET/POST /api/strategy/` — 标签列表、创建
- `DELETE /api/strategy/{id}/` — 删除标签（级联解绑）
- `POST/DELETE /api/strategy/{tag_id}/positions/{position_id}/` — 绑定/解绑
- `GET /api/strategy/relations/` — 获取全部持仓-标签关联映射
- `GET /api/strategy/overview/` — 策略视图全局数据（持仓、资产、标签、关联一次返回）

**消费场景**：策略视图页 `/asset/strategies`，按标签分组展示持仓，含汇总卡片和分组内分页。负债已在后端自动过滤。

### 5.12 账户类型与资产归属规范（v4.3.1 基线；账本模型以权威文档为准）

> **账本数据模型唯一权威说明**：账户结构、`ledger_type`/`channel_category` 正交、`sales_institution_id`、
> `external_account_code`、`frontend_app`、`is_aggregation` 等字段语义，一律以
> `docs/working-notes/ledger-channel-category-redesign-2026-08-28.md` 为准。本节仅保留"资产归属规则"这一通用约定。

#### 5.12.1 账户类型定义（基线，语义以权威文档对齐）

系统账户类型标识（`ledger_type`，内部资产类键，用户不可见）沿用以下集合；其**用户可见分组**由
`channel_category` 承载（如微众银行 `ledger_type=fund` 但 `channel_category=bank`）。详见权威文档 §2。

| 类型 | ledger_type 标识 | 含义 | 示例 |
|------|------|------|------|
| 银行账户 | `bank` | 银行机构下的资金账户，承载活期、货基、理财、该行购买基金等 | "微众银行" |
| 证券账户 | `stock` | 券商账户，承载股票、ETF、可转债等交易所资产 | "华泰证券""银河证券" |
| 场外基金平台 | `fund` | 独立基金销售平台，承载场外公募基金 | "支付宝基金""天天基金" |
| 实物资产 | `property` | 房产、车辆、黄金、收藏品等非金融资产 | "家庭房产" |

> 同一机构可因"外部资金账户"（`external_account_code`）不同拆为多个物理账本（如银河证券普通账户 vs 两融账户）；
> 同一账本可持有多种 `asset_type` 持仓。详见权威文档 §1 / §2.5 / §6。

#### 5.12.2 核心规则（硬规则，无智能判断）

1. **同账户内操作**：用户在同一个 `bank` 账户内记"买入理财"，系统视为**资产形态转换**（活期→理财），不生成出入金流水。
2. **跨账户操作**：资金离开当前账户时，用户必须使用"转账"操作关联两个账户，系统生成标准转账流水。
3. **用户自主决策**：系统不判断"银行体系内外"。用户通过选择账户和操作类型，自然决定资金流向规则。

#### 5.12.3 银行渠道买基金的归属

用户通过银行 App 直接购买的基金（钱未离开银行卡），持仓直接记录在该银行卡账户下，不单独创建 `fund` 账户。交易记录的 `source` 字段标记购买渠道（如"招商银行"）。

#### 5.12.4 交易类型（固定，不膨胀）

`bank` 账户仅支持 5 个通用操作：`存入活期` / `取出资金` / `买入理财` / `赎回理财` / `转账`。

用户选择"买入理财"后，自由输入：资产名称（如"朝朝宝"）、资产类型（从 6 个通用标签中选择）、金额。

#### 5.12.5 资产类型标签

预设 6 个通用标签：`活期存款` / `货币基金` / `定期理财` / `债券基金` / `股票基金` / `混合资产`。用户可在设置中手动新增自定义标签（如"黄金积存"），系统不自动新增。

#### 5.12.6 防错提示原则

仅对不可逆操作（删除账户、删除持仓、大额转账）进行二次确认。日常记账操作不弹出"你是不是想选另一个操作"类提示——用户选什么就执行什么。

### 5.13 乖离率（BIAS）数据模型（新增，v4.5.9）

乖离率模块为独立技术指标，支持申万一级行业、宽基指数、ETF、场外基金、股票等多种品种类型，采用刘晨明减法版乖离率算法：`BIAS = (ln(close) - EMA20(ln(close))) × 100`。

乖离率计算结果统一存入 `market_multi_items` 表（与温度模块共享），不独立建表：

| 字段 | 类型 | 说明 |
|------|------|------|
| `source` | String(30) | 固定值 `'bias'` |
| `item_type` | String(30) | 品种类型：`industry` / `index` / `etf` / `fund` / `stock` |
| `item_code` | String(20) | 品种代码（如 `801120.SI` 为申万一级行业代码） |
| `item_name` | String(50) | 品种名称 |
| `data` | JSON | 乖离率数据：`{bias, label, position, position_label, close, ema20, data_date}` |
| `collected_at` | Date | 数据日期 |

**品种列表**：

- 31 个申万一级行业（代码格式 `801XXX.SI`）
- 6 个宽基指数（沪深 300、中证 500、创业板指、科创 50、上证 50、中证 1000）
- 用户持仓/自选品种（动态获取，不写入静态配置）

**计算频率**：午间（12:00）一次 + 盘后（15:30）一次

**数据保留**：30 天（乖离度为短期技术指标，超过 30 天的数据对当前判断无参考价值）

**信号阈值**（刘晨明/广发策略）：

| 乖离率值 | 信号标签 |
|----------|----------|
| ≥ 15% | 极度高位(止盈) |
| ≥ 5% | 高位区(绿卖) |
| ≥ -5% | 中性区 |
| < -5% | 低位区(红买) |

### 5.14 温度模块三表设计（新增，v4.5.9）

温度模块采用三表设计，已全量落地：

| 表名 | 用途 | 数据保留 |
|------|------|----------|
| `market_single_values` | 单值指标（综合温度、恐贪指数、股债性价比、成交额等） | **永久** |
| `market_composites` | 复合指标（集思录估值指标、自算估值分位、二鸟说手抄报） | **1 年** |
| `market_multi_items` | 多维列表数据（乖离率、行业拥挤度、板块资金流） | **1 年** |
