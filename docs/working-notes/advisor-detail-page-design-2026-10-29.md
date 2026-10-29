# 投顾组合详情页 Web 端增强设计 · 2026-10-29

> 承接 issue [#1205](https://github.com/imoyao/fundmate/issues/1205)（投顾「双层记账」模型）。
> 上游同族：`./product-detail-page-design-2026-10-08.md`（详情页体系，§0 已把「投顾组合」列为三期品类）。
> 参考素材：用户提供的两张手机端截图（且慢「远足」、天天基金「中泰开阳价值优选」）。
> 状态：**v2 已拍板**（2026-10-29 owner 六项全部确认，见 §12）；实现待排期，未动代码。

---

## 0. 一句话结论

**投顾组合仍留在「产品详情页」内做成一组区块，不新开独立页面；把「持仓明细」从快照升级为「持仓 + 业绩 + 调仓」三件套，数据缺口集中在净值序列与档案字段填充率，靠「Port 加可选方法 + 新表 + 走势卡零改动点亮」的最小路径补齐，双层记账本期只做读取侧（组合层流水 → 底层基金拆解），不做写入侧。**

- **页面形态不变**：`/portfolio/<symbol>` 内区块栈扩展，现有入口、路由、身份解析、锚点机制全部复用，**不新建路由**；
- **补齐原则**：先补「已有数据但没暴露」的（行业配置 3 行、持仓 40322 行、调仓 1363 行），再补「能取但没请求」的（天天 10 个字段），最后才是「确实没有」的（净值序列，分期）；
- **双层记账的边界**：本期只做**只读聚合**（组合层交易 → 底层基金层拆解的展示），**不做** FOF 会计法的写入与对账；
- **可降级**：所有新增字段缺数据一律 `—`，不得因缺数据显示空区块或报错。

---

## 1. 现状盘点（全部经代码实证）

### 1.1 页面与路由

| # | 事实 | 证据 |
|---|------|------|
| 1 | 「投顾详情」**不是独立页**，是产品详情页里一个区块 | `frontend/src/router/modules/product.ts:24-34`（`/:assetType/:symbol`）；`frontend/src/utils/productIdentity.ts:61-68`（品类白名单含 `portfolio`） |
| 2 | 现有区块栈：身份卡 → 持仓 → 走势 → 交易 → 投顾 → 相关 → 外链 | `frontend/src/views/product/components/ProductDetailSections.vue:24-187` |
| 3 | 锚点标签表已把投顾登记为「投顾组合」 | `frontend/src/views/product/composables/useProductPageNav.ts:16-35`（`nav-advisor`） |
| 4 | 投顾区块**明确声明「本次刻意不做调仓记录」** | `frontend/src/views/product/components/ProductAdvisorSection.vue:29-34` |
| 5 | 走势卡在拿不到序列时**整卡不渲染**（`kind === ''`） | `frontend/src/views/product/composables/useProductTrend.ts:78-82` |
| 6 | 后端把 `portfolio` **显式列入「无序列品类」**，`fetch_product_trend` 直接 `return None`；视图随即降级成 `empty_product_trend`（`kind: ''`），前端据此隐藏整卡 | `backend/app/services/product_trend.py:72`（`_NO_SERIES_TYPES = frozenset({'manager', 'portfolio'})`）、`:242-243`（命中即 `return None`）；`backend/app/domains/products/views.py:457-461`（降级）；`empty_product_trend:308-327` |

### 1.2 数据与接口

| # | 事实 | 证据 |
|---|------|------|
| 7 | 投顾公开档案 4 张表，均在 market 域且已登记 | `backend/app/domains/funds/models.py`：`AdvisorPortfolio:487-552`、`AdvisorHolding:555-580`、`AdvisorIndustryAlloc:583-598`、`AdvisorAdjustHistory:601-623` |
| 8 | Port 契约 23 列 canonical，**无净值序列位** | `backend/app/services/adapters/advisor_source.py:45-69`（`CANONICAL_OVERVIEW_COLUMNS`）、`:77`（`CURATED_OVERVIEW_KEYS`）、`:90-170`（Port） |
| 9 | 现有 4 个投顾相关端点（**无行业配置端点**） | `GET /api/products/advisor-profile/`（`products/views.py:380`）、`GET /api/funds/advisors/<code>/holdings/`（`funds/views.py:239`）、`GET /api/funds/advisors/<code>/adjusts/`（`funds/views.py:254`）、`GET /api/positions/<id>/advisor-context/`（`positions/views.py:74`） |
| 10 | 行业配置**无任何端点暴露** | `funds/views.py` 内 grep `industr` 零命中 |
| 11 | 聚合出口 `build_advisor_profile` 恒返回全部字段（缺则 `null`） | `backend/app/services/advisor_profile.py:87-140`、`_NUMERIC_FIELDS:58-72` |
| 12 | 持仓 / 调仓读取由 `fund_service` 组装 | `backend/app/services/fund_service.py:791-840`（`build_advisor_holdings`）、`:842-913`（`build_advisor_adjusts`） |

### 1.3 三个平台适配器的能力差异（这是「数据看着有、其实没取」的根因）

| 平台 | 官方调仓 | 行业配置 | 净值序列 | 证据 |
|---|---|---|---|---|
| 且慢 QIEMAN | ❌ 靠快照推导 | ❌ 返回 `[]` | ⚠️ MCP 有工具名未接入 | `qieman_advisor_adapter.py:39-40`（`has_official_rebalances=False` / `derive_rebalances_from_snapshots=True`）、`:139-141`、`:143-149`；`services/mcp/providers/qieman.py:34-38`（`_CAPABILITY_TOOLS` 仅 3 项） |
| 天天 TIANTIAN | ✅ `getAdjustWarehouse?tag=1` | ✅ | ❓ 无已知接口（待 spike） | `tiantian_advisor_adapter.py:132-138`（`SYL_TO_INTERVAL` 仅 5 项）、**`:150`（`FIELDS` 字符串，漏列 2N/3N/3Y/6Y/RUN_DATE/MAXRETRA/SHARPE/ANNSYL/BENCHSYL）**、`:131,144`（注释「API 仅提供区间收益，不含回撤/超额」——**已过时**）、`:168`（未映射键落 `extra`，不显式映射就没人消费） |
| 好买 HOWBUY | — | — | ✅ **已实测可用但未接入** | `howbuy_advisor_adapter.py` docstring（`v717z/clcplshb.json` 净值序列实测可取；`RANGE_TO_INTERVAL`，近 3/5 年走 extra） |

### 1.4 本地库实测填充率（`backend/invest.db` 只读，114 只组合，2026-10-29）

`advisor_portfolios` 共 37 列（`pragma table_info` 实测），按列逐个统计 `is not null`：

| 字段（**列名照 `models.py:500-552` 实录**） | 填充率 | 备注 |
|---|---:|---|
| `nav` / `nav_date` | 88.6%（101/114） | `nav_date` 区间 2026-01-05 ~ 2026-10-28 |
| `max_drawdown` | 88.6%（101） | 全部来自且慢 |
| `sharpe_ratio` | 86.0%（98） | 同上 |
| `annual_return` | 86.0%（98） | 同上 |
| `volatility`（年化波动率） | 86.0%（98） | **列已存在且有数据**，无需新建 |
| `return_1d` / `1w` / `1m` / `1q` / `6m` / `1y` | 84.2% ~ 90.4% | 且慢贡献；`return_1y` 94、`return_1m` 100 |
| `return_since_incep` | 90.4%（103） | |
| `return_ytd` | 2.6%（3） | 恰为天天那 3 只 |
| `estab_date` | 90.4%（103） | 成立日可直接用 |
| `strategy_desc` / `strategy_summary` | 91.2% / 88.6% | **简介类字段并不缺** |
| `org_name` / `risk_level` / `allocation` / `source_url` | 93.9% / 93.0% / 89.5% / 88.6% | |
| `product_type` | 71.9%（82） | |
| `host`（主理人） | **1.8%（2）** | 几乎全空，是真实缺口 |
| `strategy_type` / `cum_return` / `running_days` / `benchmark` / `excess_return` | **0%** | 列在表里、值全空 |
| **表里没有的列** | — | `return_2y` / `return_3y`（无此列）、基准收益（`benchmark` 是 `String(50)` 文本基准描述，非数值） |

按平台拆开看，差异是**适配器是否请求**造成的，不是「数据源没有」：

| 平台 | 组合数 | nav | max_drawdown | sharpe_ratio | annual_return | volatility | return_1y | return_ytd |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 且慢 | 111 | 101 | 101 | 98 | 98 | 98 | 94 | 0 |
| 天天 | 3 | **0** | **0** | **0** | **0** | **0** | 3 | 3 |
| 好买 | 0 | — | — | — | — | — | — | — |

> 天天那 3 只：`return_1m` / `return_1y` / `return_ytd` / `strategy_desc` 有值（3/3），而返回同一接口的
> `nav` / `max_drawdown` / `sharpe_ratio` / `annual_return` / `volatility` / `estab_date` **全为 0**。
> 同一份概览里一半有值一半没有 ⇒ **只能是适配器只请求了部分字段**（§4.2 已证实接口能返回这些值）。

### 1.5 历史持仓可还原性

| 平台 | 机制 | 本地存量（实测） |
|---|---|---:|
| 天天 | `getAdjustWarehouse?tag=1` 官方调仓，含 pre/after 权重 + reason ⇒ 可还原任意调仓日持仓 | `advisor_adjust_histories` 1206 行 / **3 只**组合 |
| 且慢 | 无官方调仓，靠持仓快照序列 + 0.5pp 阈值推导 | 157 行 / **仅 20 只**组合（111 只里） |
| 天天 | 行业配置 | `advisor_industry_allocs` 全库 **3 行**，`source` 全为 `tiantian`，无端点暴露 |

历史持仓的两条通道（`advisor_holdings` 40322 行 / 105 只组合 / 全库仅 32 个不同 `as_of_date`，单组合最多 26 个）：

- **快照通道**：`advisor_holdings.as_of_date` 逐时点还原（覆盖 105 只）；
- **调仓通道**：`advisor_adjust_histories` 的 pre/after 权重（覆盖 23 只，其中且慢那 20 只是推导出来的）。

> **粒度必须说清楚**：且慢的「历史持仓」粒度 = **调仓时点**，不是逐日；且 **111 只里只有 20 只有推导记录**
> （其余 91 只没有产生过超过 0.5pp 的变化，或从未抓到第二个快照）。任何「历史仓位走势图」的横轴只能是
> 这些 `as_of_date`，不得画成连续日线；UI 应显式写「数据点 = N 个调仓时点」。
>
> **表名与列名以 `pragma` 实况为准**：行业表叫 `advisor_industry_allocs`（不是 `advisor_industries`），
> `advisor_holdings` 用 `portfolio_id` 关联（**没有** `platform` / `code` 列）。

---

## 2. 两张截图的信息块与移植判定

> ⚠️ **本节为「按页面形态归纳」，非逐像素转写**。截图来自移动端，且慢「远足」与天天「中泰开阳价值优选」的区块顺序、项目名可能与我下列归纳有出入；**若与截图逐块不符，以截图为准**，请 owner 指认差异后我再修订本节。

### 2.1 信息块清单与 Web 端判定

| 信息块 | 移动端作用 | Web 端判定 | 落位 |
|---|---|---|---|
| 组合名称 / 主理人 / 平台 logo | 识别 | ✅ 移植（**主理人 `host` 仅 1.8%**，缺则整行 `—`；`org_name` 93.9% 可兜底显示机构） | 已有 `IdentityCard` |
| 组合简介 / 策略说明 | 建立信任 | ✅ 移植（`strategy_desc` 91.2% 已有，折叠展示） | `AdvisorSection` |
| 最新净值 + 净值日 | 每日盯盘 | ✅ 移植（88.6% 有值，其余 `—`） | `AdvisorSection` 指标行 |
| 近 1 月 / 3 月 / 6 月 / 1 年 / 今年 / 成立以来 收益 | 业绩主视图 | ✅ 移植（1d~1y 与成立以来已有 84~90%；**缺 2 年 / 3 年，表里无列**） | 收益表（`.detail-table`） |
| 最大回撤 / 夏普 / 年化波动 / 年化收益 / 运行天数 | 风险画像 | ✅ 前 4 项已有 86%（`volatility` 列存在）；**运行天数 0%，需补写者** | `MetricCard` 网格 |
| 净值走势图 + 区间切换 | 趋势 | ✅ 移植（**需新数据链路，§4.3**） | `TrendSection`（现有卡自动点亮） |
| 业绩基准对比 | 判断是否跑赢 | ⚠️ 有条件移植（仅天天 `BENCHSYL_*` 能取，且**无数值列**，须新增） | 收益表附「基准 / 超额」列，缺则 `—` |
| 当前持仓（基金 / 权重） | 看清买了什么 | ✅ 移植 | 现有持仓表增强 |
| 历史持仓（按调仓日切换） | 追溯仓位变化 | ✅ 移植（**新交互，§3.1 第 6 项**） | 持仓表 + 时点选择器 |
| 调仓记录（时间 / 加减仓 / 原因） | 解释变化 | ✅ 移植（天天有 reason，且慢无） | 现有 `PositionAdvisorAdjusts` 提取为共用件 |
| 资产大类分布（环形） | 一眼看结构 | ⚠️ **暂不纳入**（`allocation` 只是单值标签、非占比分布，见 §12-Q5） | —（待数据源） |
| 行业分布 | 穿透风险 | ⚠️ 仅天天有数据（`advisor_industry_allocs` 全库 3 行），Web 端只对这几只渲染 | 表内嵌条（`ProductIndustrySection` 范式） |
| 交易 / 买入按钮 | 转化 | ❌ **不移植**（本产品是记账软件，不做交易导流） | — |
| 关注 / 收藏 | 留存 | ⚠️ 已有自选机制，复用现有 `watchlist` 状态按钮，不新增 | 页头操作槽 |
| 策略说明长文 / 主理人履历 | 尽调 | ⚠️ 折叠（`el-collapse`），不占首屏；**主理人履历无数据源**（无此表/此字段），本期只展示 `org_name` | `AdvisorSection` 底部 |

### 2.2 移动端 → Web 端的**形态改写**（不照搬）

| 移动端形态 | Web 改写理由 | Web 形态 |
|---|---|---|
| 全屏纵向单列滚动 | 桌面有横向空间，单列会产生大面积空白 | 两列栅格：左 2/3 主数据、右 1/3 风险画像 + 结构 |
| 底部固定「买入」条 | 无交易功能 | 删除，页头操作槽给「加入自选」 |
| 收益指标横滑卡片 | 横滑在桌面不可发现 | `MetricGrid` 网格（4 列） |
| 净值图全宽 + 手势缩放 | 桌面用 `dataZoom` | 保留图内区间档（现有 `useProductTrend`） |
| 图表点击弹层看明细 | 桌面用 hover tooltip | ECharts `tooltip.trigger='axis'` |
| 持仓列表点开展开 | 桌面用表内嵌条 + 表头排序 | `.detail-table` |

---

## 3. Web 信息架构（区块与锚点）

### 3.1 区块栈（在现有栈上**插入**，不重排既有顺序）

```text
IdentityCard                      (现有，不动)
PositionSection                   (现有，仅持有我的持仓时渲染)
TrendSection                      (现有，本期由「恒隐藏」变「有序列才亮」)
TransactionSection                (现有，仅持有)
AdvisorSection                    (现有 → 本期扩容为多子卡，见下)
RelatedSection                    (现有)
ExternalLinks                     (现有)
```

`AdvisorSection` 内部子卡顺序（自上而下）：

1. **组合概览**：名称 / 平台 / 主理人 / 成立日 / 运行天数 / 最新净值 + 净值日 / 简介（折叠）；
2. **业绩表现**：区间收益表（近 1 月 / 3 月 / 6 月 / 今年 / 1 年 / 2 年 / 3 年 / 成立以来，列含「本组合 / 业绩基准 / 超额」，缺则 `—`）；
3. **风险画像**：`MetricGrid`（最大回撤 / 夏普 / 年化收益 / 年化波动，均取 `max_drawdown` / `sharpe_ratio` / `annual_return` / `volatility`——**这四列已存在且填充率 86%**）；运行天数单列，现 0% 填充（§4.1 B/C 级）；
4. **净值走势**：由 `TrendSection` 承载，**不在此重复**（避免同页两图）；
5. **当前持仓**：基金名称 / 代码 / 权重 / （可选）穿透行业；
6. **历史持仓**：时点选择器（`SegmentedControl` 不合适——单组合最多 26 个 `as_of_date`，用 `el-select`）+ 该时点持仓表；
7. **调仓记录**：时间 / 方向 / 前后权重 / 原因（且慢无 reason 时显示推导标记「据持仓变化推导」）；
8. **行业分布**：当前仅 3 行数据（1 只组合），用表内嵌条（`ProductIndustrySection` 范式，按本区最大值归一），不占独立卡位；「资产大类」环形图**本期不做**（§12-Q5）。

### 3.2 锚点变更

现有 `nav-advisor`（「投顾组合」）保留，指向 `AdvisorSection` 顶部。若子卡需要独立锚点（如「调仓记录」），**必须同步登记** `useProductPageNav.ts:16-35`，否则标签点了不动——该文件是锚点的唯一真源。

**建议本期只保留 `nav-advisor` 一个锚点**，不拆子锚点：投顾子卡在页面中位置连续，拆锚点会让导航条膨胀到 9 项以上，违反「一层页头」的克制原则。

### 3.3 交互与状态

| 场景 | 行为 |
|---|---|
| 组合未建档 / 接口 404 | `AdvisorSection` 整体不渲染（与 `TrendSection` 同策略），不显示空壳 |
| 某字段缺 | 行内 `—`，不隐藏整行（保持表结构稳定） |
| 历史持仓无数据 | 时点选择器置灰 + 提示「该组合暂无调仓记录」 |
| 走势序列缺 | `TrendSection` 自动不渲染（现有机制，零改动） |
| 加载中 | 区块级 skeleton，不做全页 loading |

---

## 4. 数据方案

### 4.1 缺口分级与处置

| 级别 | 缺口 | 处置 | 成本 |
|---|---|---|---|
| **A. 已有数据未暴露** | 行业配置（`advisor_industry_allocs` 3 行）、历史持仓（`advisor_holdings` 40322 行 / 105 只；`advisor_adjust_histories` 1363 行） | 新增 2 个只读端点 | 低 |
| **B. 能取但没请求** | 天天：`SYL_2N` / `SYL_3N` / `SYL_3Y` / `SYL_6Y` / `MAXRETRA_LN` / `SHARPE_LN` / `ANNSYL_LN` / `BENCHSYL_LN` / `BENCHSYL_1N` / `RUN_DATE`（运行天数） | 扩 `FIELDS` + 扩 canonical 列 | 低 |
| **C1. 有列但 0% 填充** | `strategy_type` / `cum_return` / `running_days` / `benchmark` / `excess_return` | B 级落地后 `running_days` 有写者；其余三个明确「谁写」或**从表中移除**（数据策略硬约束 1：新列必须当场指定读者） | 低 |
| **C2. 连列都没有** | `return_2y` / `return_3y` / 基准收益数值 / 超额收益数值（`excess_return` 列在但 `benchmark` 只是文本描述） | 新增列（走 `migrate_advisor_tables.py` 范式） | 中 |
| **D. 确实没有** | 净值序列（且慢可经 MCP 工具取、好买实测可取、天天未知） | 分期：先接且慢 + 好买，天天单独 spike | 中 |

### 4.2 B 级实证（2026-10-29 实网探测，均返回成功）

`POST https://uni-fundts.1234567.com.cn/combine/investAdviserInfo/getTGQuoteByFavor`
（form：`product=EFund, mobileKey=123, version=6.5.9, plat=Android, tgCodeWithDateStr=XCOVSEX_2026-10-29`）

返回（节选）：`SYL_D 1.10 / SYL_Z -1.28 / SYL_Y -5.79 / SYL_3Y -5.85 / SYL_6Y -9.46 / SYL_JN -3.83 / SYL_1N -3.02 / SYL_2N 25.39 / SYL_3N 35.12 / SYL_LN 18.46 / MAXRETRA_LN 24.33 / SHARPE_LN 0.16 / ANNSYL_LN 4.19 / RUN_DATE 1556 / ESTABDATE 2022-07-26 / JZRQ=SYRQ=2026-10-28`。

`GET https://dataapi.1234567.com.cn/dataapi/IAAGGR/FundIATGInfoAggr`（扩 `FIELDS` 后）额外给 `BENCHSYL_LN 1.17`、`BENCHSYL_1N -10.4`；**不含** `MAXRETRA_LN` / `SHARPE_LN`。

**结论**：天天侧 2~3 年收益、最大回撤、夏普、年化、基准收益、运行天数**全都拿得到**，属「适配器没请求」，不是数据源缺失。这解释了 §1.4 里天天 3 只全 0% 的现象。

> ⚠️ **`models.py:527` 的注释已经过时**，原文写「回撤/超额 API 不直接提供（实测结论），暂留空、待补算」。
> 那句话的实测范围只是 `FundIATGInfoAggr` 一个接口；**回撤与夏普在 `getTGQuoteByFavor` 里现成有**
> （`MAXRETRA_LN 24.33` / `SHARPE_LN 0.16`）。改代码时一并修正该注释，否则下一个人会沿用这条
> 「不提供」的结论，把已经能取的字段继续留空。
>
> **两个接口分工**：`getTGQuoteByFavor` 给指标（回撤 / 夏普 / 年化 / 2-3 年区间 / 运行天数 / 成立日），
> `FundIATGInfoAggr` 给基线数据与基准（`BENCHSYL_*`）。而当前 `fetch_overview` **只调后者**
> （`tiantian_advisor_adapter.py:153` 的 `API_AGGR`），`FIELDS` 也只列了 5 个 `SYL_*`（`:150`）——
> 所以「只扩 `FIELDS`」拿不到回撤与夏普，**必须新增对 `getTGQuoteByFavor` 的调用**。
> 另外 `:168` 把未映射的键塞进 `extra`、业务侧不读 ⇒ 光加 `FIELDS` 而不加映射，数据会
> 落进一个没人看的地方，属于「看起来取了、实际没用」。

### 4.3 D 级：净值序列的最小改动路径

```text
Port(advisor_source) 加可选方法 fetch_nav_history(code, days) -> list[(date, nav)]
  ├─ qieman:   接入 MCP 工具 GetPortfolioNavHistory（需改 _CAPABILITY_TOOLS:34-38）
  ├─ howbuy:   接 v717z/clcplshb.json（docstring 已实测可用）
  └─ tiantian: 暂无（spike 后再定）
        ↓
新表 advisor_nav_history（market 域，须登记 DATA_DOMAIN_REGISTRY）
        ↓
product_trend.py: 从 _NO_SERIES_TYPES(L72) 移除 'portfolio' + 加 elif portfolio 分支
        ↓
前端 TrendSection 零改动自动点亮
```

**为什么走这条**：前端走势卡已有完整的「区间档 + nav/return 双口径 + 空则隐藏」逻辑（`useProductTrend.ts:50-59,78-82,107-117`），后端缺的只是「移除 `_NO_SERIES_TYPES` 里的 `portfolio` + 加一个分支」。任何「前端另写一套投顾走势图」的方案都会造出第二份图表实现，是明确的反面模式。

> ⚠️ **只加分支、不移除 `_NO_SERIES_TYPES` 等于没做**：`product_trend.py:242-243` 在分派**之前**就 `return None`，
> 新加的 `elif` 永远不会被执行。这是典型的「写了代码但不会跑」，验收时要按 §8-3 实测两种情况（有序列 / 无序列）。
> 顺带：`products/views.py:440` 的 docstring 把「指数」也算进无序列品类，但 `index` 已有独立分支（`:270-278`），
> 该注释同样过时，一并修正。

**降级备选已否决（Q2 裁定 A，2026-10-29）**：原备选是「快照 × 成分基金日净值」加权合成组合净值。**不采用**——它会造出「看起来有曲线、实际是推算」的静默偏差，比显示 `—` 危险得多。若 P2 某平台确实取不到序列，则**该平台不画曲线**，而不是换一种算法硬凑。

### 4.4 数据策略四问自查（每项新增都要答）

| 新增项 | 谁在用 | 什么场景 | 缺了会怎样 | 成本 |
|---|---|---|---|---|
| `advisor_nav_history` 表 | 走势图 | 打开投顾详情页 | 走势卡不渲染（与现状一致，可接受） | 每组合 ~250 行/年 |
| 行业配置端点 | 行业分布卡 | 打开详情页看穿透 | 卡不渲染 | 0 新增存储（已存） |
| 历史持仓时点端点 | 历史持仓表 | 追溯仓位变化 | 只显示当前持仓 | 0 新增存储（已存） |
| 天天 10 个字段 | 业绩表 / 风险卡 | 首屏 | 一堆 `—` | 0 新增存储（10 个里有 6 个列已存在；2y/3y/基准收益需新增列） |
| `return_2y` / `return_3y` / 基准收益数值列 | 业绩表「本组合 / 基准 / 超额」 | 首屏 | 该 3 行显示 `—` | 3 列 × 114 行，可忽略 |

> C1 的 5 个 0% 字段已按 §12.1 逐条处置：3 条本期闭环（`running_days` 写入、`cum_return` 复用 `SYL_LN`、`excess_return` 现算不落库），2 条（`benchmark` / `strategy_type`）登记 `docs/spec/tech-debt.md`「无写者」并**保留列**——不允许继续沉默存在。「列在表里但永远为空」会让下一个人以为「只是还没同步」。

---

## 5. #1205 双层记账：本期边界

### 5.1 #1205 的模型（回顾）

- **组合层交易流水**：用户对这个投顾组合的申购 / 赎回 / 调仓成交（金额、份额、净值、费用）；
- **底层基金交易流水**：由平台调仓推导出的、组合内部对各只基金的买卖；
- **持仓快照**：某时点组合的成分与权重；
- **成本法**：平均成本法为建议默认，FOF 会计法为备选。

### 5.2 本期做 / 不做

| 项 | 本期 | 理由 |
|---|---|---|
| 组合层「我的持仓」展示 | ✅ 已有（`positions.asset_type='portfolio'`，`valuation_mode` 必须 `balance`，D70/#2740） | 已落地 |
| **读取侧**：当前持仓 → 底层基金拆解展示 | ✅ **本期做** | 数据已在 `advisor_holdings`，只缺端点与前端 |
| **读取侧**：调仓事件 → 前后权重变化展示 | ✅ **本期做** | 天天有 reason，且慢可推导 |
| **写入侧**：用户调仓时自动生成组合层 + 底层基金两层流水 | ❌ **本期不做** | 需要先定成本法（平均成本 vs FOF），属会计口径决策，不在设计文档单方面拍板 |
| FOF 会计法 | ❌ 不做 | #1205 定为「备选」，未定默认 |
| 双层流水的对账（组合层总额 = 底层拆解总额之和） | ❌ 不做 | 依赖写入侧 |

### 5.3 为什么写入侧必须先定成本法

平均成本法与 FOF 会计法对**同一笔调仓**给出的成本与已实现盈亏不同：

- 平均成本法：组合视为一个整体，调仓只在组合层记账，底层基金层不产生独立成本；
- FOF 会计法：底层每只基金各自持有成本，调仓产生底层层的已实现盈亏。

两者在「用户看到的收益率」上会给出**不同数字**。这不是展示层能调和的差异，必须先由 owner 拍板（§12-Q3）。

---

## 6. 接口契约（本期新增 / 变更）

### 6.1 新增端点（均为只读、均尾斜杠、均走统一错误信封）

| 方法 | 路径 | 说明 | 降级 |
|---|---|---|---|
| `GET` | `/api/funds/advisors/<code>/industries/` | 行业配置 | 无数据返回 `data: []` |
| `GET` | `/api/funds/advisors/<code>/holdings-history/` | 历史持仓时点列表 + 指定时点明细 | 无数据返回 `data: {dates: [], holdings: []}` |
| `GET` | `/api/funds/advisors/<code>/nav-history/?range=` | 净值序列（D 级完成后） | 无序列返回 `data: []` |

约束：

- 一律 `APIBlueprint` + `{data, message, error_code}` 三字段信封（`scripts/guard_error_envelope.py`）；
- 改路由后必须重跑 `python scripts/check_api_conventions.py --write` 刷新 `docs/spec/api.md` 自动段；
- `holdings-history` 的时点来源**必须显式标注推导/官方**（`source: 'official' | 'derived'`），不得混成一个字段。

### 6.2 变更端点

| 端点 | 变更 | 兼容性 |
|---|---|---|
| `GET /api/products/advisor-profile/` | 返回值**新增**字段（业绩区间、基准、运行天数） | 加法兼容，前端缺字段走 `—` |
| `GET /api/funds/advisors/<code>/holdings/` | 增加可选 `as_of` 参数 | 不传 = 当前持仓，行为不变 |

> **不得**把 `advisor_profile` 改成「缺字段就不返回 key」——现有契约是恒返回、缺给 `null`，前端据此降级。改成动态 key 会让前端 `undefined` 与 `null` 两套判断并存。

---

## 7. 前端组件拆分与复用

### 7.1 拆分清单

| 组件 | 性质 | 来源 | 行数预估 |
|---|---|---|---|
| `ProductAdvisorSection.vue` | 宿主（现有，扩容） | `views/product/components/` | 现 133 行 → 扩容后须 **< 400 行**（`check_vue_size.mjs`），超阈值先抽子件 |
| `AdvisorOverviewCard.vue` | 新建 | — | ~120 |
| `AdvisorPerformanceTable.vue` | 新建 | `.detail-table` 范式 | ~140 |
| `AdvisorRiskMetrics.vue` | 新建 | `MetricGrid` | ~80 |
| `AdvisorHoldingsTable.vue` | 新建 | 现有持仓表逻辑迁移 | ~180 |
| `AdvisorHoldingsHistory.vue` | 新建 | 时点选择 + 复用上表 | ~90 |
| `AdvisorAdjustsTimeline.vue` | **提取** | `positionSection/PositionAdvisorAdjusts.vue:242 行` 改为 data-driven | ~200 |
| ~~`AdvisorAllocationChart.vue`~~ | 本期**不做**（§12-Q5） | — | — |

### 7.2 强制复用（不得重写）

- 区块：`CardBlock` + `SectionHeader`；
- 指标：`MetricCard` / `MetricGrid`；
- 分段：只有 `SegmentedControl` 一个实现（禁止 `el-segmented`，`scripts/guard_segmented.py` 拦截）；
- 表格：`.detail-table` 约定，`scripts/guard_detail_tables.py` 拦截；
- 环形图：`AssetAllocationDonut`（`frontend/src/components/Charts/`），**禁止**第二份饼图（`scripts/guard_no_duplicate_pie.py`）；
- 涨跌色：只用 `--color-rise` / `--color-fall`，禁止硬编码 hex；
- 净值位数：`pricePrecision(assetType)` / `formatPrice`，禁止 `.toFixed()`。

### 7.3 风险：调仓组件提取

`PositionAdvisorAdjusts.vue` 当前按 `positionId` 取 `positions/advisor-context`。提取为共用件时**不得**把父组件耦合进去——改为 props 接收 `adjusts` 数组，数据获取留在两个宿主各自处理。否则会造出「组件知道两种取数路径」的分支判断，是后续 bug 的温床。

---

## 8. 验收标准

1. `/portfolio/<symbol>` 打开后，`AdvisorSection` 按 §3.1 渲染 7 项（其中第 4 项「净值走势」由 `TrendSection` 承载，不在本区块内重复），**其中至少 4 项有实质数据**；其余因无数据不渲染而非空壳；
2. 任一新增字段缺失时显示 `—`，页面无报错、无 console error；
3. 走势卡：有序列时渲染（且区间档可切换），无序列时整卡不渲染——**两种情况都不得出现空图**；
4. 历史持仓：时点选择器列出的每个日期点开，持仓权重合计 = 100%（±0.5pp），且标注 `official` / `derived`；
5. 调仓记录：天天组合显示 reason，且慢组合显示「据持仓变化推导」；两者不得混用同一措辞；
6. 新端点均返回三字段信封；`docs/spec/api.md` 自动段已刷新；
7. `pnpm typecheck` / `pnpm lint` 零错误；`ProductAdvisorSection.vue` 及新组件均 < 400 行（`scripts/check_vue_size.mjs`）；
8. 后端新增测试覆盖：`backend/tests/domains/test_advisor_views.py`（新端点）、`backend/tests/services/test_advisor_profile.py`（新字段）、`backend/tests/services/adapters/test_howbuy_advisor_adapter.py`（净值序列接入）；
9. 前端新增测试：`advisorModel.spec.ts` 扩展字段降级用例。

---

## 9. 分期拆卡

| 期 | 内容 | 依赖 | 可独立验收 |
|---|---|---|---|
| **P0（低成本补齐）** | ① 天天两个接口同时扩 `FIELDS`（`getTGQuoteByFavor` + `FundIATGInfoAggr`）+ 扩 canonical；② 新增 `return_2y` / `return_3y` / 基准收益列（`migrate_advisor_tables.py` 范式）；③ 行业配置端点；④ 历史持仓端点；⑤ 按 §12.1 处置 5 个 0% 字段（3 条闭环 + 2 条登记 tech-debt）；⑥ 修正 `models.py:527` 与适配器 `:131,144` 的过时注释 | 无 | ✅ |
| **P1（页面扩容）** | `AdvisorSection` 子卡（概览 / 业绩 / 风险 / 持仓 / 历史持仓 / 调仓 / 行业），`AdvisorAdjustsTimeline` 提取 | P0 端点 | ✅ |
| **P2（净值序列）** | Port 加 `fetch_nav_history` + 且慢 MCP 接入 + 好买接入 + `advisor_nav_history` 表 + `product_trend` 分支 | P1 可并行 | ✅ |
| **P3（天天序列 spike）** | 探测天天是否有净值序列接口；有则接入，无则明确记录「不支持」 | P2 完成主链路 | ✅ |
| **P4（双层记账写入侧）** | 依赖 §12-Q3 拍板 | owner 决策 | ❌ 本期不排期 |

> P0 与 P1 可拆成两张卡并行（P1 用 mock 数据先跑通组件）；P2 必须等 `advisor_source.py` Port 变更评审，因为它是跨平台契约，改一次影响 3 个适配器。

---

## 10. 风险与回滚

| 风险 | 影响 | 处置 | 回滚 |
|---|---|---|---|
| 天天接口字段变更（无文档、逆向得来） | 业绩表整列 `—` | 单测钉住字段名；解析失败降级 `—` 不抛错 | 保持旧 `FIELDS`，字段缺失自动降级 |
| 且慢 MCP 工具名/参数变化 | 净值序列取不到 | spike 阶段先手工验证再接入 | 关掉 `fetch_nav_history` 即可，它在 Port 里是**可选**方法 |
| 新表未登记 `DATA_DOMAIN_REGISTRY` | 启动校验直接失败（拦得住） | 建表同时登记 | 回滚迁移脚本 |
| 组件提取引入回归 | 我的持仓页调仓区块坏 | 提取前后跑同一组前端测试 | git revert 单 commit |
| 且慢「历史持仓」被误读为逐日 | 用户以为能看到日线仓位 | UI 明示「数据点 = 调仓时点」，共 N 个 | 文案修正 |
| `ProductAdvisorSection.vue` 涨破 400 行 | CI 红（`check_vue_size.mjs`） | 先拆子件再扩容 | 拆件本身无回滚风险 |

**迁移范式**（新增列必须走这条，`backend/` 下没有 alembic）：

`backend/scripts/migrate_advisor_tables.py`（`estab_date` / `strategy_desc` 历史先例）+ `backend/app/core/migrations.py` + `backend/app/core/schema_drift.py`。

---

## 11. 与现有设计的边界

| 问题 | 结论 |
|---|---|
| 要不要新开 `/advisor/<code>` 路由？ | **不要**。`product-detail-page-design-2026-10-08.md` §0 已把投顾定为详情页体系内的品类，另开路由会让同一数据两套页面（#1133 的反面先例） |
| 移动端截图里的「买入」要不要做？ | **不要**。记账软件不做交易导流，也不许抓用户券商账户（AGENTS.md「抓取合规」） |
| 是否要照搬天天基金的 13 个 tab？ | **不要**。同 `product-detail-page-design-2026-10-08.md` §2 第 1 条：持仓视角优先，不做全市场研究页 |
| 历史持仓能不能画成仓位面积图？ | 可以，但横轴是**调仓时点**不是日期，须在图上标注。本期先做表，图放 P1 之后 |

---

## 12. 决策记录（2026-10-29 owner 拍板，6 条全部确认）

| # | 问题 | 选项 | **裁定** | 落地含义 |
|---|---|---|---|---|
| **Q1** | 投顾组合是否仍留在产品详情页内做区块，不新开独立页？ | A 区块 / B 独立页 | **A 区块** | 不新建路由；`$route.params.assetType='portfolio'` 就地扩展，锚点沿用 `nav-advisor` |
| **Q2** | 净值序列缺口怎么处置？ | A 先接且慢 + 好买 / B 快照合成 / C 不做 | **A 先接且慢 + 好买** | P2 按 §4.3 路径做；**不采用**合成降级，`composed_from_snapshots` 口径作废 |
| **Q3** | 双层记账写入侧是否本期实现？成本法选哪个？ | A 不做 / B 平均成本 / C FOF | **A 不做** | 本期只做读取侧；写入侧与成本法**另开卡**，等免费层稳定后单独拍 |
| **Q4** | 天天净值序列是否要先做 spike 再排期？ | A 先 spike / B 假定没有 | **A 先 spike** | P3 必须先有实测结论（有/无都要落一条记录），不得凭空断言「不支持」 |
| **Q5** | 且慢「资产大类」环形图是否纳入 P1？ | A 纳入 / B 延后 | **B 延后** | 本期只做行业分布（表内嵌条）；`allocation` 是单值标签，画不出分布，需先有占比明细数据源 |
| **Q6** | 5 个 0% 填充字段：指定写者还是清理？ | A 指定写者 / B 清理 / C 现状 | **能取到的闭环掉** | 3 条本期闭环（`running_days` / `cum_return` / `excess_return`），2 条无数据源登记 tech-debt（见下） |

### 12.1 Q6 细则：逐字段处置

| 字段 | 数据来源 | 处置 |
|---|---|---|
| `running_days` | `RUN_DATE`（`getTGQuoteByFavor`，实测 1556） | ✅ P0 写入 |
| `cum_return` | `SYL_LN`（成立以来收益，与 `return_since_incep` 同源；已实测 18.46） | ✅ P0 写入（同一原始值双列，须在注释里写明「同一 SYL_LN 的两个读者」，避免被当成两个独立口径） |
| `excess_return` | 现算：组合区间收益 − 基准区间收益（`BENCHSYL_*`） | ✅ P1 现算，**不落库**（数据策略硬约束：能算出就不存） |
| `benchmark`（文本基准名） | 两次实网探测均未见对应字段 | ⚠️ 登记 `docs/spec/tech-debt.md`「无写者」，**不删列**（列留着不占存储，删了要迁移） |
| `strategy_type` | 两平台接口均无明确字段名 | ⚠️ 同上 |

> **为什么不一刀切删列**：删列要走迁移且不可逆，而 `benchmark` 很可能在换用别的平台接口后就有值；登记「无写者」比删除更能表达真实状态。反过来，**继续沉默才是真问题**——登记后下一个人看到 tech-debt 条目就知道「不是没同步，是没数据源」。

---

## 13. 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v1 | 2026-10-29 | 首版。基于 #1205 + 两张移动端截图 + 代码测绘 + 本地库填充率实测 + 天平接口实网探测 |
| v2 | 2026-10-29 | owner 拍板 6 项（§12 改为决策记录）：Q1 区块 / Q2 先接且慢+好买 / Q3 写入侧不做 / Q4 先 spike / Q5 环形图延后 / Q6 能取到的闭环。据此新增 §12.1 逐字段处置（3 条闭环 + 2 条登记 tech-debt）、否决合成降级（§4.3）、P0 范围加「修正过时注释」 |
