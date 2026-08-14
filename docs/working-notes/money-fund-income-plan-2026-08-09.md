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
- 按 `ledger_id` 归组（`get_overview_stats`/`get_account_groups`）；`get_sankey_data` 归入「流动资金/cash」大类，`get_summary_data` 直接并入 `total_assets`（该函数输出无大类字段）。
  - 实现细化（2026-08-14 落地，差异与原因见 §7 D4/D5/D6）：`get_overview_stats` 悬空净额（None/已删 ledger）并入 `deleted` 分组；`get_account_groups` 孤儿流水按 `ledger_id` 归组（无 ledger 归「游离」），与按 `account_name` 归组的 positions/assets 并存。
- **不修改 `calculators.py`（XIRR 仍排除货基，语义不变）**；`EXCLUDED_ASSET_TYPES` 保留。

**核心决策点**：QuickEntry 手动记账（路径 B）目前建 positions 持仓（4 只），与孤儿流水（路径 A）**并存**。为不动前端大规模改动，本方案**不强制二选一**，两条路径都进总资产即可；后续可再讨论统一为一条路径。

### 3.2 每日收益链路

**前置：重建 `money_fund_daily_worth` 数据**（必须，否则读取的是脏数据）：

1. 备份现有 24,350 条 → 删除；
2. 用已修复的 `XalphaAdapter.fetch_fund_nav` 对全部货基（funds.fund_type_id=6，357 只）跑一次全量增量同步 → 正确写入 nav_per_10k（万份收益）。
   - 注：同步逻辑已修（commit 1a94d7a），000198 实测走 pingzhongdata、is_money_fund=True。

**新增后端**：`backend/app/services/money_fund_income.py`

- 函数：`calculate_money_fund_income(db, start_date, end_date, scope, ledger_id, family_id)` → 读取 `MoneyFundDailyWorth.nav_per_10k`，按持仓净额/份额计算区间每日收益（2026-08-14 实现：单日单基金签名不足以支撑展示需求，改为范围 + 多基金 + scope，见 §7 D1）。
- 计算式：**每日收益 = 持有金额（元）× 万份收益 ÷ 10000**（货基单位净值恒 1.0，份额=金额）。
- 持仓净额来源：孤儿流水净额 + positions 中货基（type='fund'）金额，两者合并口径（与 §3.1 一致）。

**新增 API**：`GET /api/performance/money-fund-income/`（scope=ledger/family，最终契约见 §6.3，取代本节的早期设想，见 §7 D2）。

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

## 5. 待确认（2026-08-14 已确认）

1. 本金口径：**统一流水式**（用户确认，见 §6）——货基只记孤儿流水，不建 positions 持仓。
2. 每日收益前端展示位：**账户详情页 + 仪表盘**（用户确认）。
3. 历史货基持仓：**一并清理**（迁移为孤儿流水，保留金额，非删除）。

## 6. 统一流水式口径补充设计（2026-08-14 用户确认）

> 决策：货基领域本质是"类现金"（单位净值恒 1.0、份额=金额、T+0 申赎、无价格波动），
> 不需要持仓实体。统一为流水式：持有金额 = Σ孤儿流水净额，收益 = 持有金额 × 万份收益 ÷ 10000。
> 路径 B（`BuyForm.remoteSearch` 硬编码 `type:'fund'` 导致货基被当普通基金建仓）是历史实现缺陷，一并修复。

### 6.1 历史持仓迁移（positions 中 4 只货基）

- 对象：000198 余额宝 10 万份、000638/000891/003474（current_price=1.00）
- 迁移前**必须核查**：这 4 只持仓是否有 `transactions.position_id` 关联流水（plan §5.3 曾提示"避免破坏既有流水关联"）；有则一并处理（关联流水改挂孤儿流水或保留 position_id 悬空需评估）
- 迁移动作：为每只持仓创建对应买入孤儿流水（`amount`=份额×1.00 元→分，`position_id=None`、`entry_status='orphan'`、关联原 `ledger_id`/`account_name`/`fund_code`），再删除 positions 行
- 一次性迁移脚本（`backend/scripts/` 或临时脚本），跑前备份 positions 表（CSV）
- 回滚：恢复备份 CSV

### 6.2 BuyForm 修复（`frontend/src/components/QuickEntry/BuyForm.vue:602`）

- 现状：`remoteSearch` 硬编码 `type:'fund'` → 货基被当普通基金建仓
- 修复：搜索选中基金时按类型分流——货基（搜索接口返回的基金类型/`is_money_fund` 标记）→ `type:'money_fund'`，后端 `position_service.py:165` 已有现金管理路径（孤儿流水），无需后端改动

### 6.3 展示组件（账户详情页 + 仪表盘）

- 后端 API：新增 `GET /api/performance/money-fund-income/`（scope=ledger/family，返回每日收益序列 + 今日/累计收益），前端 `api/performance.ts` 封装
- 账户详情页：货基区块显示「今日收益 +¥x.xx」「累计收益」（涨红跌绿、MoneyDisplay/RiseFallText、语义变量）
- 仪表盘 Overview：货基卡片/区块同款展示
- 无非硬编码假数据、无静默 catch 吞错

### 6.4 收益计算式（全程整数分，无裸 float）

```
每日收益（分）= 持有金额（分） × nav_per_10k（分） ÷ 1_000_000
```

推导：万份收益 w 元 = 每万元当日收益；持有 H 元 → 收益 = H×w/10000 元。
分单位代入：H分=H×100、w分=w×100 → 收益分 = H分×w分/1_000_000。
示例：H=500 元（50000 分）、w=0.35 元（35 分）→ 精确值 1.75 分 → **round half-up 到 2 分 = 0.02 元**。
舍入说明（2026-08-14 实现补充，见 §7 D3）：金额最小单位是分，1.75 分无法在展示层表达；逐基金 round half-up 到整数分再求和，符合「金额展示到分」的人类阅读习惯。

### 6.5 测试清单（新增）

- `money_fund_income.py` 单测：给定 nav_per_10k 序列，断言每日/累计收益正确（含跨日、零持有、脏数据缺失日兜底）
- summary/overview 单测：孤儿流水净额并入总资产/账户汇总（正净额计入、负净额处理）
- 迁移脚本验证：迁移后持有金额不变、无孤儿 position_id 残留
- XIRR 无回归：货基仍排除（`EXCLUDED_ASSET_TYPES` 不变）

### 6.6 实施 lane 划分（2026-08-14）

- L1 后端聚合：`summary_service.py` + `ledger_service.py` 孤儿流水净额并入（§3.1）
- L2 后端收益：`services/money_fund_income.py` + `performance/views.py` 新端点 + 单测（§3.2 + §6.4）
- L3 数据操作：备份/清空重建 `money_fund_daily_worth` + 4 只持仓迁移（§3.3 + §6.1）
- L4 前端：BuyForm 修复 + 展示卡片 + API 封装（§6.2 + §6.3）
- 依赖：L3 重建验证依赖 L1/L2 代码就绪；L1/L2/L4 可并行

## 7. 实现与文档差异记录（2026-08-14 L1/L2 落地后核对）

> 原则：文档与实现冲突时，以代码实况为准更新文档，并记录差异与原因，不做静默修改（AGENTS.md「文档拉平纪律」）。

| # | 位置 | 文档原表述 | 实现 | 原因 |
|:--|:--|:--|:--|:--|
| D1 | §3.2 | 函数 `get_money_fund_daily_income(db, symbol, date)` 单基金单日 | `calculate_money_fund_income(db, start_date, end_date, scope, ledger_id, family_id)`，范围 + 多基金 + scope | 前端展示需要「每日收益序列 + 今日/累计」，单日单基金签名无法支撑；scope=ledger/family 与既有 performance API 风格一致 |
| D2 | §3.2 | API `GET /api/funds/money-fund-income/?date=` 或并入 summary | `GET /api/performance/money-fund-income/`（§6.3 契约） | §6.3 已细化最终契约，§3.2 为早期设想，予以取代 |
| D3 | §6.4 | 示例 1.75 分 = 0.0175 元（精确值） | round half-up 到 **2 分 = 0.02 元** | 金额最小单位是分，1.75 分无法在展示层表达；逐基金 round half-up 到整数分再求和，符合人类阅读习惯 |
| D4 | §3.1 | 无 ledger 归「游离」 | `get_overview_stats` 悬空净额（None/已删 ledger）并入 `deleted`（已删除账户）分组 | overview 既有游离聚合（positions/assets 的 None/已删 ledger）本就是 deleted 分组，孤儿净额并入同分组避免重复计数、口径统一 |
| D5 | §3.1 | `get_summary_data`/`get_sankey_data` 归入「流动资金/cash」大类 | `get_summary_data` 无大类字段，直接并入 `total_assets`；仅 `get_sankey_data` 并入 `category_totals['cash']` | summary 输出无分类维度，无法归入大类，只能并入总额 |
| D6 | §3.1 | 按 ledger_id 归组，无 ledger 归「游离」 | `get_account_groups` 孤儿流水按 `ledger_id` 归组（无 ledger 归「游离」），与按 `account_name` 归组的 positions/assets 并存（「游离」与「未指定账户」两个独立桶） | positions/assets 既有分组维度是 account_name，孤儿流水仅能关联 ledger_id，维度不同无法强合并；不重复计数已在各函数内保证 |
| D7 | §3.2 | positions 中货基为 `type='fund'`（按普通基金录入） | L2 `_collect_position_market_value` 过滤 `asset_type == 'money_fund'`（ORM 属性，物理列 `type`），**真实 DB 货基持仓 type='fund' 匹配不到**，迁移前兼容基线实际不生效 | 真实数据货基以 `type='fund'` + funds.fund_type_id=6 关联识别；L3 迁移后 positions 货基清空、孤儿流水覆盖，最终口径正确。兼容基线仅为防御性代码（保留无害），已注释说明；测试夹具建了 `type='money_fund'` 持仓故单测通过 |

另：孤儿流水判定用 `position_id IS NULL`（与 `asset_type` 组合），未用 `entry_status='orphan'` 过滤——新建路径两者等价，历史导入器早期数据 `entry_status` 可能不统一，`position_id IS NULL` 判定更可靠、更宽松。

## 8. L3 数据实况复核（2026-08-14，执行迁移前侦查）

> §1.1 为 2026-08-09 侦查，执行 L3 前按当前库复核（invest.db 直查）。**§1.1 数据已过时，以本节为准。**

### 8.1 货基持仓全集（positions.type='fund' 且 symbol 去 `SZ` 前缀后命中 funds.fund_type_id=6）

| id | symbol | 名称 | 份额（份×10000） | 金额（元） | ledger_id | account_name | 备注 |
|:--|:--|:--|:--|:--|:--|:--|:--|
| 244 | 000198 | 天弘余额宝货币 | 100000000 | **10,000**（1 万份×1.00，`multiply_price_quantity` 实测） | **1（已删除）** | None | 1 条关联流水 1 万元，**金额一致**（见 8.3；plan §1.1「10 万份」为错误数据） |
| 18 | 000638 | 华宝现金宝货币A | 74200 | 742 | 5 | 天天基金 | 与 id=15 同 symbol 同数量（疑似重复导入） |
| 15 | SZ000638 | 华宝现金宝货币A | 74200 | 742 | 5 | 天天基金 | 同上 |
| 19 | 000891 | 博时现金宝货币B | 48200 | 482 | 5 | 天天基金 | 与 id=12 同 symbol 数量不同 |
| 12 | SZ000891 | 博时现金宝货币B | 158200 | 1,582 | 5 | 天天基金 | 同上 |
| 23 | 003474 | 南方现金增利货币B | 10 | 0（0.1 分，量化为 0） | 5 | 天天基金 | 与 id=17 同 symbol 同数量；金额 < 1 分无法表达 |
| 17 | SZ003474 | 南方现金增利货币B | 10 | 0（同上） | 5 | 天天基金 | 同上 |
| 11 | SZ001937 | 银华现金添利货币 | 108800 | 1,088 | 5 | 天天基金 | plan §1.1 未列，复核新增 |
| 22 | 001982 | 天弘余额宝货币B | 100 | 1（0.01 元） | 5 | 天天基金 | 疑似货基（funds 未映射类型） |
| 30 | 001821 | 华安现金富利货币B | 39736100 | 3,973.61 | 5 | 天天基金 | 疑似货基（funds 未映射类型） |
| 42 | 003535 | 华夏现金增利货币B | 20 | 0（0.2 分，量化为 0） | 5 | 天天基金 | 疑似货基（funds 未映射类型） |

合计：1,401,998 分 = **14,019.98 元**（含 3 条金额为 0 的持仓）。

### 8.2 孤儿流水净额（asset_type + type 列）

| ledger_id | asset_type | 条数 | 净额（分） | 净额（元） |
|:--|:--|:--|:--|:--|
| 3（微众银行） | money_fund | 415 | 51,826,618 | 518,266.18 |
| 5（天天基金） | money_fund | 19 | 9,086 | 90.86 |
| 7（同花顺） | reverse_repo | 4 | 20,200,084 | 202,000.84 |

### 8.3 000198 关联流水（唯一一条持仓关联流水）

- id=1640：`000198 buy 1,000,000 分（1 万元）`，trade_date 2026-08-07，confirm_date 2026-08-10，position_id=244，entry_status=None
- **持仓金额与流水金额一致**（均 1 万元，2026-08-14 复核更正：plan §1.1「10 万份」为错误数据）。迁移处理方式见 §8.5 决策 2。

### 8.4 money_fund_daily_worth

- 24,350 条，仍为旧算法脏数据（§1.1 不变），L3 备份后清空重建。

### 8.5 迁移决策点（待用户确认）

1. **迁移对象**：仅 fund_type_id=6 关联的 8 条，还是也纳入 001982/001821/003535（名称判定的疑似货基）？
2. **000198 关联流水 1640（1 万元）**：复核更正——持仓金额与流水金额**一致**（均 1 万元），原方案 B/C 的「持仓 10 万 vs 流水 1 万」前提不成立。推荐：1640 改挂孤儿（position_id=NULL）+ 删持仓 244，**不新建/删除流水**（金额守恒、保留流水历史）。
3. **重复记录**（000638×2 同量、003474×2 同量、000891×2 异量 158200 vs 48200）：逐条迁移（金额守恒，总资产不变）还是按 symbol 去重？000891 两条数量不同，疑似重复导入，需用户判断是否为真实双份持有。
4. **000198 ledger_id=1 已删除**：孤儿流水保持 ledger_id=1（归 overview `deleted` 分组），确认即可。
5. **L5 根治（des-1 建议）**：`/api/funds/search/` 返回补 `fund_type`/`is_money_fund` 字段，前端 `resolveFundAssetType` 升级为「字段优先、代码段兜底」，覆盖场外货基（000198 即 000 开头）——本次是否一并实施？
