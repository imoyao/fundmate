# 货币基金本金口径与每日收益计算方案（2026-08-09）

> 性质：内部备忘。目的：方案 B「本金口径修复 + 每日收益链路」的详细设计，含改动点、数据迁移、回滚、验证标准。实施前须用户确认本方案。

## 1. 现状实证（2026-08-09 实测）

### 1.1 用户货币基金数据实况

| 数据 | 数值 | 说明 |
|:---|:---|:---|
| money_fund 孤儿流水 | 434 条 / 净额 **52.2 万元** | 微众银行(ledger 3) 51.8 万、天天基金 0.42 万；415 条来自微众银行 |
| money_fund 建仓流水 | 41 条 | 有 position_id |
| positions 中货币基金 | 4 只 / 按普通 fund 录入 | 000198 余额宝 10 万份、000638/000891/003474（current_price=1.00） |
| `money_fund_daily_worth` | 24,350 条 **全部脏数据** | 2026-05-31~06-07 旧算法（净值差×10000）写入；含普通基金误判（000001 华夏成长混合）；000198 余额宝反而无记录 |
| `daily_worth` 中货币基金污染 | 0 条（已清理） | 上一轮 commit 1a94d7a 已清 |

### 1.2 根因

1. **本金口径混乱（两条并行的货币基金记账路径）**：
   - **路径 A（导入器）**：同花顺/支付宝导入 → `asset_type='money_fund'` → `_create_cash_transfer_transaction`（孤儿流水，position_id=None）→ 微众银行 415 条即此路径；
   - **路径 B（QuickEntry 手动记账）**：`BuyForm.remoteSearch` **硬编码 `type:'fund'`**（`BuyForm.vue:602`）→ 按普通基金建仓 → positions 表 4 只货基即此路径。

2. **总资产漏算**：`summary_service.get_summary_data` / `get_sankey_data` / `get_account_groups` 与 `ledger_service.get_overview_stats` **只聚合 `positions + assets`**，孤儿流水（52.2 万净额）完全不计入 → 用户总资产里微众银行货币基金缺失。

3. **每日收益链路无消费者**：`money_fund_daily_worth.nav_per_10k` 无任何读取代码（`calculators.py` 只查 `DailyWorth`）；且存量 24,350 条为旧算法脏数据（含普通基金 000001 误判），须清空重建。

## 2. 目标

1. **本金口径统一**：货币基金净额进入总资产/账户汇总，不再漏算（第一象限：账目正确性）。
2. **每日收益链路打通**：读取 `nav_per_10k` 计算每日收益并展示（第二象限）。

## 3. 方案设计

### 3.1 本金口径：孤儿流水净额并入汇总（改动小、风险低）

**改动文件**：`backend/app/services/summary_service.py`、`backend/app/services/ledger_service.py`

**做法**：在 `get_summary_data` / `get_sankey_data` / `get_account_groups` / `get_overview_stats` 四处，增加对**孤儿流水**（`asset_type IN ('money_fund','reverse_repo')` 且 `position_id IS NULL`）的净额聚合：

```
净额 = SUM(CASE WHEN type IN ('buy','deposit') THEN amount
                WHEN type IN ('sell','withdraw') THEN -amount
                ELSE 0 END)
```

- 净额 > 0 → 计入资产（货基）；净额 < 0 → 视同负债/现金流出（不常见，按负数处理并归入资产负值）。
- 按 `ledger_id` 归组（`get_overview_stats`/`get_account_groups`），无 ledger 归「游离」；`get_summary_data`/`get_sankey_data` 归入「流动资金/cash」大类。
- **不修改 `calculators.py`（XIRR 仍排除货基，语义不变）**；`EXCLUDED_ASSET_TYPES` 保留。

**核心决策点**：QuickEntry 手动记账（路径 B）目前建 positions 持仓（4 只），与孤儿流水（路径 A）**并存**。为不动前端大规模改动，本方案**不强制二选一**，两条路径都进总资产即可；后续可再讨论统一为一条路径。

### 3.2 每日收益链路

**前置：重建 `money_fund_daily_worth` 数据**（必须，否则读取的是脏数据）：

1. 备份现有 24,350 条 → 删除；
2. 用已修复的 `XalphaAdapter.fetch_fund_nav` 对全部货基（funds.fund_type_id=6，357 只）跑一次全量增量同步 → 正确写入 nav_per_10k（万份收益）。
   - 注：同步逻辑已修（commit 1a94d7a），000198 实测走 pingzhongdata、is_money_fund=True。

**新增后端**：`backend/app/services/money_fund_income.py`

- 函数：`get_money_fund_daily_income(db, symbol, date)` → 读取 `MoneyFundDailyWorth.nav_per_10k`，按持仓净额/份额计算当日收益。
- 计算式：**每日收益 = 持有金额（元）× 万份收益 ÷ 10000**（货基单位净值恒 1.0，份额=金额）。
- 持仓净额来源：孤儿流水净额 + positions 中货基（type='fund'）金额，两者合并口径（与 §3.1 一致）。

**新增 API**：`GET /api/funds/money-fund-income/?date=` 或并入现有 summary 接口返回 `money_fund_daily_income` 字段。

**前端展示**：账户详情页/仪表盘（Overview）在货基相关卡片上显示「今日收益 +¥x.xx」（涨红跌绿、走语义变量）。

### 3.3 数据迁移与回滚

| 操作 | 备份 | 回滚 |
|:---|:---|:---|
| 删除 money_fund_daily_worth 24,350 条脏数据 | 导出 CSV 到 `C:\Users\imoyao\AppData\Local\Temp\opencode\mf_daily_worth_backup.csv`（与上次备份同目录） | 恢复 CSV → 重新 INSERT |
| 新增汇总逻辑（净额并入） | 无数据迁移，纯代码 | `git revert` 即可 |
| 同步重建 nav_per_10k | 无（从公开源拉取，可重跑） | 重跑 `pdm run sync --job fund_nav` |

### 3.4 验证标准（验收）

1. **总资产正确**：微众银行货币基金净额（51.8 万）出现在总资产/账户汇总，与 `probe` 计算值一致。
2. **每日收益正确**：000198 余额宝某日收益 = 持有金额 × 万份收益 ÷ 10000；与支付宝「昨日收益」对账一致（抽样 1-2 天）。
3. **单元测试**：新增 `tests/services/test_summary_money_fund.py`（孤儿流水净额聚合 + 收益计算），全量 pytest 通过。
4. **无回归**：XIRR 计算仍排除货基；`get_money_fund_stats` 行为不受影响（或按新口径更新）。

## 4. 工作量与风险

- 总工时约 1 天（§3.1 半天 + §3.2 半天）。
- 风险：低。改动集中在聚合层与新增计算服务，不触碰 API 契约冻结区；`money_fund_daily_worth` 数据删除有备份可回滚。

## 5. 待确认

1. 本金口径是否接受「两条路径并存都进总资产」（推荐）？
2. 每日收益前端展示位：仪表盘 Overview 还是账户详情页？（建议账户详情页 + 概览）
3. 是否顺带清理 positions 中 4 只「按普通基金录入」的货基持仓（历史口径，建议保留不动，避免破坏既有流水关联）？
