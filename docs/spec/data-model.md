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

### 5.11 投资组合 (Portfolio)（已实现）

**设计定位**：回答"我的钱按什么策略投资"。与 Ledger（账户：钱放哪里）和 Allocation（五笔钱：风险等级）互补，为可选的高级分析工具。

**核心约束**：

- 一个 Ledger 最多关联一个 Portfolio（多对一），不拆分持仓。
- 组合收益率 = 合并关联 Ledger 的现金流后计算 XIRR，自动过滤内部划转。
- 渐进暴露，默认隐藏入口，不侵入记账主流程。

#### 5.11.1 portfolios 表（已实现）

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

#### 5.11.2 ledgers 表新增字段（已实现）

| 字段 | 类型 | 说明 |
|------|------|------|
| portfolio_id | Integer (FK) | 关联 portfolios 表，`ON DELETE SET NULL`，删除组合时自动解绑 |
| linked_cash_ledger_id | Integer (FK) | 关联的现金账户（仅 stock/fund 类型可用），`ON DELETE SET NULL` |

**注**：原计划添加的 `objective` 字段已移除，语义与 `Portfolio.purpose` 重叠，精简模型。

#### 5.11.3 策略标签（持仓风格分析）（已实现）

**设计定位**：纯展示层分析工具，用于按投资风格（如"成长""价值""大盘"）分类查看持仓。不参与 XIRR 计算，不影响 Portfolio 资金流隔离逻辑。

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

### 5.12 账户类型与资产归属规范（v4.3.1 最终确定）

#### 5.12.1 账户类型定义

系统仅支持四种账户类型，不再增减：

| 类型 | 标识 | 含义 | 示例 |
|------|------|------|------|
| 银行账户 | `bank` | 一张具体的银行卡，承载该卡内所有资产（活期、货币基金、银行理财、通过该行购买的基金等） | "招商银行卡(6214)" |
| 证券账户 | `stock` | 券商账户，承载股票、ETF、可转债等交易所资产 | "华泰证券" |
| 场外基金平台 | `fund` | 独立基金销售平台，承载场外公募基金 | "支付宝基金""天天基金" |
| 实物资产 | `property` | 房产、车辆、黄金、收藏品等非金融资产 | "家庭房产" |

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
