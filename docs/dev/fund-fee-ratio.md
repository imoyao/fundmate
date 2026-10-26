---
title: 基金费率信息获取
---

> **关联 Issue**：[#460](https://github.com/imoyao/fundmate/issues/460)（费率信息处理，已实现/已关闭）
> **币种缺口跟踪**：[#820](https://github.com/imoyao/fundmate/issues/820)
> 本文档于 2026-08-08 triage 复核中**由 V1 方案更新为 V2 现状**，V1 内容移至「历史方案（已退役）」归档，避免文档↔历史差异。

## 现状（V2，已实现）

数据源由 V1 的「韭圈儿/蛋卷爬虫」改为 **xalpha `fetch_fund_fee`**（`backend/app/services/sync/adapters/xalpha_adapter.py`）。

### 实现链路

- **模型拆表**（`backend/app/domains/funds/models.py:127-156`）：
  - `FeeRatio`（fund_code / fee_type / rate / fee_amount + PurchaseRule、RedeemRule 两个外键）
  - `PurchaseRule`（金额区间 `start_quota` / `end_quota`，单位：元）
  - `RedeemRule`（持有天数区间 `start_day` / `end_day`，单位：天）
- **落盘任务**：`backend/app/services/sync/jobs/fund_detail_enrich_job.py` 的 `_update_fund_fees()` / `_save_single_fee()` / `_get_or_create_purchase_rule()` / `_get_or_create_redeem_rule()`，已在 `DataSyncOrchestrator.execution_plan` 中自动执行并 `commit` 落盘。
- **消费层**：`backend/app/services/fund_service.py` 的 `get_fund_fee_rates()` / `estimate_redeem_fee()` / `sync_fund_fees()`；API 出口见 `backend/app/domains/funds/views.py`。

### 区间处理（V2）

不再使用 V1 的 `portion` 模块，改为**整数列**：申购费率区间用 `start_quota`/`end_quota`（元），赎回费率区间用 `start_day`/`end_day`（天）。计算赎回费时由 `estimate_redeem_fee()` 按持有天数匹配对应区间。

### 币种（已实现）

- **币种已落库**：`FeeRatio` 已含 `currency` 列（ISO 4217，默认 CNY，见 [#820](https://github.com/imoyao/fundmate/issues/820)）。东财/同花顺接口均无结构化币种字段（pingzhongdata / jjfl / f10 / `fund_info_ths` 实测均不含），故按基金份额名称特征推导：含「人民币」或全无外币字样 → CNY；含「美元/港币/港元/日元/欧元/英镑」→ 对应 ISO 码。推导逻辑见 `FundService.infer_fund_currency`（`backend/app/services/fund_service.py`），写入点为 `sync_fund_fees` 与 `FundDetailEnrichJob._update_fund_fees`。既有库回填用一次性脚本 `backend/scripts/migrate_fee_ratio_currency.py`。

### 消费侧展示口径（前端，#1015）

产品详情页「基金资料」区块的两格费率口径收口在纯函数
`frontend/src/views/product/components/fundFeeFormat.ts`，三条约定写在那里：

1. **`rate` 是小数**（`0.015` = 1.5%）。落库前 `_upsert_fee_ratio` 已除以 100，
   消费侧只许走 `formatPercent`，**不得再乘 100**——两处各写一份就是 100 倍错误的来路。
2. **区间是半开区间** `[start, end)`（`estimate_redeem_fee` 判据 `days >= start`
   且 `days < end`），故 `[0, 7)` 读作「不足 7 天」，写成「0~7 天」会让人以为第 7 天
   仍收 1.5%。
3. **取区间下界最小的一档**，不是 `rows[0]`：`get_fund_fee_rates` 的查询无
   `ORDER BY`，顺序不确定；旧实现取首行 + 用 `start_day` 当条件，首档下界为 0 时
   渲染出「1.50%（0 天内）」。

申购档还要看 `fee_amount`（固定金额档，元/笔）：大额档常是「1000 元/笔」且
`rate` 为 0，只读 `rate` 会显示成「0.00%」，等于说「免费申购」。

「费率怎么读」（申购/赎回费怎么算、首档是短期惩罚档且全额计入基金资产、管理费/
托管费等按日从净值计提）没有任何后端字段归属，属**知识**而非**数据**，由前端静态
文案承载（`components/FundFeeGuide.vue`，默认收起），不入库、不缓存。

---

## 历史方案（V1，已退役 · 仅作归档参考）

> 以下内容为早期方案，已被 V2 xalpha 方案取代，**当前代码中不存在** `portion` 模块、`IsClosedDurationError`、韭圈儿/蛋卷费率爬虫。

### 数据源（V1）

基金费率信息数据源主要来自：

1. ~~谁牛基金~~
2. ~~蛋卷基金~~
3. 韭圈儿

其中谁牛基金（基金决策宝）的数据需要先查询基金前面的对应码，然后拼接字符（SZxxx）才能请求接口，调用比较麻烦；蛋卷基金的命中率太低；所以最后使用韭圈儿结合蛋卷基金来处理基金的费率信息，目前只保存申购和赎回费率，对于运行费率信息，我们暂时不关心，后期可以视情况保存。

### 区间处理（V1）

一开始我们对前中后的费率区间分别进行处理，需要针对每一种进行判断并单独处理，导致代码复杂度较高；之后引入 `portion` 模块来处理区间信息，区间最小值为 0，最大值为 `portion.inf`，存入数据库时须将 `inf` 转为 `None`（MySQL 的 `NULL`）；赎回费率区间统一转为「天」，申购费率区间统一转为「元」，区间统一为前闭后开（`[0,inf)`）。对时间区间天数进行区间转换（参阅 `parse_portion()`）；金额区间直接强制转为前闭后开（金额最小精度 `0.01`）。

### 币种（V1）

部分基金费率并非以人民币结算，曾对币种做匹配，但**数据中的币种当时未存入数据库**。该诉求在 V2 下由 [#820](https://github.com/imoyao/fundmate/issues/820) 承接。

### V1 TODO（已不适用）

- 封闭期基金：V1 因赎回费率按天区分而无法处理，抛出 `IsClosedDurationError`；V2 下封闭期逻辑由 xalpha 内部处理，此异常已不存在。
- 爬虫效率：V1 多线程爬虫议题随数据源切换至 xalpha 已失效。

## 关联

- Issue [#460](https://github.com/imoyao/fundmate/issues/460)（费率信息处理，已关闭）
- Issue [#820](https://github.com/imoyao/fundmate/issues/820)（币种落库，待办 · 重要不紧急）
