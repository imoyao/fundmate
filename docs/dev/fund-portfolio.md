---
title: 投顾组合（Advisor Portfolio）数据域设计与实现
---

> 本文是**组合域（投顾/基金组合参照数据）的权威文档**（2026-09-08 收束，替代散落的调研备忘与 2021 年组合回测研究稿）。
> 编码与引用决策的完整讨论过程见 [issue #1286](https://github.com/imoyao/fundmate/issues/1286) 评论留档。

## 1. 定位与边界

- `advisor_portfolios` 及其三张明细表是 **market 域公开参照数据**（且慢/蛋卷/天天基金等平台的投顾组合、实盘组合、基金组合），公开、读多写少。
- 与 **user 域的用户私有组合**（`portfolios` 表，`positions.portfolio_id` 归属）严格分离，二者无外键、无 join，跨域只走应用层两步法。
- 历史上的「资产配置型（回测）/ 投资记录型（实盘）」组合产品愿景（原 2021 研究稿）保留为远期方向：账本可视为实盘型组合，回测作为投资前计划、落地后跟踪误差。当前落地的是**投顾组合参照 + 自选引用**，回测功能未启动。

## 2. 数据模型（`backend/app/domains/funds/models.py`）

| 表 | 说明 |
|----|------|
| `advisor_portfolios` | 组合主表：`code`（平台组合码，**unique**）、`platform`（QIEMAN/DANJUAN/TIANTIAN/YINGMI）、name/host/org_name/risk_level/strategy_type、累计与年化收益、#1167 补充的 estab_date/strategy_desc |
| `advisor_holdings` | 当前持仓快照：同一 (portfolio, as_of_date) 整体覆盖；`fund_code` 存业务键不建外键（成分基金可能暂缺于 funds 表） |
| `advisor_industry_alloc` | 行业配置快照：快照日随当前持仓调仓日 |
| `advisor_adjust_history` | 历史调仓：同一 (portfolio, adjust_date) 整体覆盖，调仓理由随行冗余 |

四表均登记在 `app/core/db_factory.DATA_DOMAIN_REGISTRY` 的 market 域，由启动校验兜底。

## 3. 编码与自选引用约定（#1286，2026-09-08 定稿）

- **平台原生码即 symbol**：天天基金 tgcode（7 位平台随机码，如 `XCOVSEX`，来自 App 分享链接）与且慢策略码（`ZHxxxxxx` 自增）格式互不重叠、天然全局唯一，**不自造编码**。
- `advisor_portfolios.code` 带 unique 约束 → 自选侧**单键引用**：`watchlist.symbol = 平台码`、`asset_type='portfolio'`、`market=''`、`venue=''`（无市场实体存空串而非 NULL，SQLite UNIQUE 中 NULL 互不相等会使唯一性失效）。
- **platform 留在组合表**，不在自选侧冗余：自选回查 `advisor_portfolios` 后带出 platform 等属性。早期「自选存 platform+code 双键」的设计作废。
- 经理（`asset_type='manager'`）同理：`symbol = MGR_ + 权威外部经理 id`（派生码方案 sha256 已废），market/venue 同样存空串。
- 唯一键 `(symbol, market, venue)` 天然覆盖新品种，自选表不加任何外键（双库硬规则 §2 跨域零外键）。

## 4. 同步链路

- **天天基金**：`AdvisorPortfolioSyncJob`（`app/services/sync/jobs/advisor_portfolio_job.py`）+ `TiantianAdvisorAdapter`，公开接口零鉴权直抓四个数据面（概览/当前持仓/行业配置/历史调仓），覆盖式更新。已在 orchestrator 注册（`advisor_portfolio` job）。
- **且慢**：无免费公开持仓接口，走手动导入 `import_qieman_holdings()`（`scripts/import_qieman_holdings.py`），`source='qieman_manual'` 区分。
- 回填 SOP：`pdm run python scripts/seed_advisors.py` 建档（幂等 upsert）→ `pdm run invoke grab.advisor_portfolio`（或 `sync --job advisor_portfolio`）。
- tgcode 获取方式与接口调研留档：`docs/working-notes/advisor-ttfund-id-research-2026-09-08.md` 等 4 篇 advisor 系列备忘。

## 5. 待办

- [ ] 基金经理权威外部 id 调研与 `mgr_code` 换源（废 sha256 派生码，仿 advisor 调研留档）——#1286 实施项
- [ ] 组合/经理接入统一聚合搜索 `GET /api/search/assets/` ——#1286 实施项
- [ ] 自选详情/列表的品种差异化展示（组合：持仓/主理人；经理：任职基金）——#1285
- [ ] 远期：资产配置型（回测）组合、组合购买记账录入（经聚合搜索 `asset_type='portfolio'` 分流）
