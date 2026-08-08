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

### 已知缺口
- **币种未落库**：`FeeRatio` 无 `currency` 列，币种信息尚未持久化 → 跟踪 **[#820](https://github.com/imoyao/fundmate/issues/820)**（重要不紧急）。

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
