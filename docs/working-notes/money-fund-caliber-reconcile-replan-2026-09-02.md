# 货基本金口径再规划（issue #863 复核与拍板，2026-09-02）

> 性质：正式方案文档（工作记录）。承接 `money-fund-income-plan-2026-08-09.md`（首版方案，2026-08-14 已确认「统一流水式」）与 issue #863（代码现状核查），记录 2026-09-02 复核结论、纠偏、最终拍板（口径 A：持仓优先）与本期/二期实施边界。实施前以本文件 + P0-1 核验结果为准。

## 1. 决策沿革（本主题为什么反复）

| 时间 | 事件 | 结论 |
|---|---|---|
| 2026-08-09/14 | `money-fund-income-plan-2026-08-09.md` 确认「统一流水式」：货基只记孤儿流水、不建 positions；存量迁移；BuyForm 货基 `type` 分流 | 货基 = 类现金（净值恒 1、T+0），不需要持仓实体 |
| 2026-08-14 后 | #1233 决策 5「货基/逆回购保持建持仓」：手动记账（记一笔/QuickEntry）`force_create_position=True` 建仓、流水挂 `position_id` | 手动记账走回持仓路径（与统一流水式部分反转） |
| 2026-09-02 | issue #863 复核 + 评审纠偏 + 用户拍板口径 A（持仓优先） | 本文 |

> 复盘说明：#1233 决策 5 与 08-14「统一流水式」的时间先后以代码注释为准，本文不修正日期，只记录后果：**双轨并存是双计根因**，收敛方向 = 写入层互斥 + 持仓优先。

## 2. 现状核查结论（代码 + 本地库实证）

### 2.1 代码事实

- 孤儿口径：`summary_service.orphan_money_fund_net_by_ledger`（`position_id IS NULL` 的 money_fund/reverse_repo 净额）并入 6+ 处聚合；`money_fund_income._collect_orphan_flows` 按 **confirm_date** 累计本金。
- 持仓路径：`positions/views.py` 手动记一笔一律 `force_create_position=True` → 建仓 + 流水挂 `position_id`（不进孤儿口径）；导入器（交易导入）与 `auto_purchase_money_fund` 走孤儿流水。
- 收益计算：`money_fund_income._collect_position_market_value` 合并"孤儿流水净额 + money_fund 持仓市值"为持有基线。
- 判定字段：无 `is_money_fund`/`is_income`/`source_version` 列；`transactions` 无收益类型（支付宝「收益发放」硬映射 `type='deposit'`，见 `importer/mappings.py`）。
- 数据域：`funds`/`fund_types` 属 market 域（Turso），`positions`/`transactions`/`asset_snapshots` 属 user 域（Supabase）——**双库下无法 SQL JOIN**，货基判定不能靠运行期跨域关联。

### 2.2 本地 invest.db 实测（只读，2026-09-02）

| 维度 | 值 |
|---|---|
| positions | 150（fund 122 / stock 12 / etf 8 / bond 8），**无 `type='money_fund'`** |
| 货基按普通 fund 录入 | 3 只：001010@ledger13、003003@ledger20、001937@ledger20（评审所述 4 只以生产为准）|
| 孤儿货基流水 | 0 条（本地无 money_fund/reverse_repo 流水）|
| money_fund_daily_worth | 1,229,646 行；重复组 (fund_code,date) 14,538；无 source 列 |
| asset_snapshots | 31 行（家/户级幂等 upsert 已可用）|

### 2.3 纠偏结论（推翻原评审 3 处假设）

1. **总资产双计修复落点不在 `position_aggregation.py:151,190`**（那是 /funds、/stocks 列表页聚合视图）。口径 A 下聚合层累加公式**保持不动**，双计防线放在**写入层互斥**（同一 `(ledger_id, symbol)` 只能一种表达）+ **分类映射**（货基归「现金/流动资金」）。
2. **货基判定不能只判 `asset_type`**：存量货基是 `type='fund'`，需统一谓词（`type='money_fund'` 或 `is_money_fund=True`，判定源 = market 域 funds 名录货币型 + 代码段兜底）。
3. **只排除不迁移会漏计**：手动记账流水挂 `position_id`，孤儿口径（`position_id IS NULL`）兜不住；任何"金额从一处转移到另一处"的改动都必须配套数据迁移并做 dry-run 对比。

## 3. 拍板决策（2026-09-02）

| # | 决策点 | 拍板 | 说明 |
|---|---|---|---|
| D0 | **总资产口径** | **A 持仓优先**：所有 active 持仓市值照常累加；孤儿流水净额（`position_id IS NULL`）照常并入；**防双计 = 写入层互斥**（同一 `(ledger_id, symbol)` 只能是 position 或孤儿流水之一），聚合层只做**分类映射**（货基市值归入「现金/流动资金」桶，不进「基金投资」） | 持仓承载展示职责；写入层互斥比聚合层排除干净；与 #1233 兼容不回退 |
| D1 | 收益归属 | **1-A 收益本金化**：总资产 = 本金桶 + 收益桶（+ 非货基持仓/资产）。收益桶本期 = 渠道 `is_income` 流水；自动计算收益**仅展示不入总资产**（防「导入实收 vs 本地预估」双算） | 若 P0-1 核验 `is_income` 流水 = 0（纯手动用户），B2 提至本期 |
| D2 | 在途资金 | **2-A 本期 UI 标注过渡**，不建在途模型 | 前端「确认中」提示走后端只读预估端点（契约见 §7）；B1 状态机挂二期 |
| D3 | 货基判定字段 | **`positions.is_money_fund` 冗余布尔**（写路径填充 + 存量回填） | 双库跨域不能 JOIN，冗余是架构必然 |
| D4 | 存量持仓形态 | **保持 active 真实货基持仓，不转 shadow**；与孤儿流水重叠项迁移时挂回持仓或删除孤儿流水 | shadow 仅限 E账户对账待归因记录 |

### 3.1 目标不变量（任何一期不得破坏，写进回归测试）

1. `总资产 = 全部 active 持仓市值（货基归「现金/流动资金」桶）+ 通用资产(净) + 孤儿净额(本金桶, position_id IS NULL 且非 is_income) + 收益桶(渠道 is_income) + [二期：在途资金]`
2. **写入层互斥**：同一资金、同一 `(ledger_id, symbol)` 只允许一种表达（position 或孤儿流水）。建货基持仓时若存在同 `(ledger, symbol)` 孤儿流水 → **挂回 `position_id`**；孤儿流水仅在"无持仓表达"的账户形态（类现金绑定/导入路径）存在。
3. `is_income` 行只在收益桶累计，**不得进入本金/孤儿净额口径**。
4. 货基判定统一走 `fund_utils`，禁止各聚合点自行判 `asset_type`。

## 4. 本期实施清单（P0-1 → P1-6，全做完关票）

| # | 事项 | 落点 | 防呆要求 |
|---|---|---|---|
| 1 | `positions` 加 `is_money_fund`（migration+模型） | `domains/positions/models.py` | 默认 NULL=「未判定」，≠False；回填前走代码段兜底 |
| 2 | 写路径填充 `is_money_fund` | `position_service`（建仓/合并/快照）、`auto_purchase_money_fund`、importer 建仓处 | 统一走 `fund_utils`；market 名录缺失用代码段兜底 |
| 3 | 存量回填脚本 | `backend/scripts/migrate_*_money_fund_flag.py` | dry-run 出 diff；名录缺标告警不静默 |
| 4 | 统一谓词/分类工具 | 新建 `services/fund_utils.py` | 提供 `is_money_fund_symbol`（写路径）/`is_money_fund_position`（聚合分类）；代码段兜底 |
| 5 | **写入层互斥**：建货基持仓时挂回孤儿流水 | `position_service.process_buy_or_deposit` / 快照建仓 | 同 `(ledger, symbol)` 的 `position_id IS NULL` 流水（非 is_income）→ 置 `position_id` 为新持仓；挂回前后金额守恒断言 |
| 6 | 聚合层**分类映射**（不改累加公式）：货基市值归「现金/流动资金」桶 | `summary_service.get_distributions` / `get_sankey_data`（category 分布）、`ledger_service.get_cash_like_stats` 对照 | 金额不进「基金投资」；分布总额与总资产一致 |
| 7 | `transactions.is_income` 标记 + 导入映射收益行标记 | `transactions/models.py`、`importer/mappings.py` | 孤儿净额/收益计算**必须过滤 is_income**；历史收益行识别由 P0-1 决定 |
| 8 | 收益桶入总资产（Σ is_income 流水） | `summary_service`（get_summary_data / get_ledger_distributions） | 只累计 money_fund/reverse_repo 且 position_id IS NULL 的 is_income 行；与孤儿净额桶互斥 |
| 9 | `money_fund_income`：孤儿净额过滤 is_income；**保留**持仓市值基线（口径 A 下持仓+孤儿都属本金桶） | `services/money_fund_income.py` | 自动收益只展示不入总资产；测试同步 |
| 10 | QuickEntry 后端 type 归一 | `domains/positions/views.py` | 命中货基而 type≠money_fund 自动修正 + 日志，不拒绝 |
| 11 | `money_fund_daily_worth` 加 `source_version`；限定持仓代码集 + 2025-09-01 后窗口软删重抓；修 `nav_per_10k` 类型/注释 | `funds/models.py`、migrate 脚本、`fund_nav_job.py` | 清前 dry-run；补 (fund_code,date) 唯一约束消除重复 |
| 12 | 存量迁移：3~4 只货基保持 active + `is_money_fund=True`；重叠孤儿流水挂回持仓（或删除）；无重叠流水保持独立持仓 | migrate 脚本 | dry-run 对比「迁移前 vs 后」总资产与孤儿净额；人工确认后执行 |

> 事项 5（写入层互斥）是核心：它使 6+ 处聚合无需"排除逻辑"，把双计风险封死在入口。

## 5. 二期清单（挂账，随各自 issue 承接）

- B1 在途资金状态机（pending/confirmed + 确认任务，依赖 #1182 调度器）——替换 §7 预估端点数据源，契约不变。
- B2 自动收益纳入总资产（复投模拟 + 与 is_income 的「渠道确认日+收益日」双键去重）——D5 触发时提至本期。
- B3 收益起息/展示口径（T+1 确认、T+2 起息、T 日收益次日可查）。
- B4 reverse_repo 是否从现金等价物拆出——本期继续跟随货基，`CASH_EQUIVALENT_TYPES` 单点定义。
- B5 总资产构成拆分 UI（持仓/在途/收益三栏 + 差额解释）。

## 6. P0-1 生产核验（Supabase user 域 + Turso，先行项）

> 本地 invest.db 无孤儿流水，无法本地还原；评审所述 4 只持仓 / 434 条流水 / 24,350 脏数据以生产为准。执行前先读 `AGENTS.md` 与 `docs/dev/db-data-domain.md` 确认双库连接方式。

```sql
-- ① 孤儿流水全景（money_fund + reverse_repo，按账户/代码/类型）
SELECT ledger_id, asset_type, symbol,
       COUNT(*) AS cnt,
       SUM(CASE WHEN type IN ('buy','deposit') THEN amount ELSE -amount END) AS net_cents
FROM transactions
WHERE asset_type IN ('money_fund','reverse_repo') AND position_id IS NULL
  AND family_id = 1
GROUP BY ledger_id, asset_type, symbol;

-- ② 持仓侧货基全集（type='money_fund'；type='fund' 需经 funds 名录货币型确认，双库下分开查后内存合并）
SELECT id, ledger_id, symbol, quantity, current_price FROM positions
WHERE type = 'money_fund' OR type = 'fund';

-- ③ is_income 候选（关键分支：D1 动态开关）
-- 注意：生产 schema 无 category/trade_type/memo/is_income 列；
-- 收益行 = type='deposit' 且 notes/extra 含收益特征。先抽 50 行样本确认特征再定 Count 口径。
SELECT COUNT(*) AS cnt, SUM(amount) AS sum_cents
FROM transactions
WHERE asset_type IN ('money_fund','reverse_repo') AND position_id IS NULL
  AND type = 'deposit'
  AND (notes LIKE '%收益%' OR extra LIKE '%收益%' OR position_name LIKE '%收益%');

-- ④ 持仓 vs 孤儿流水重叠（双计实锤判定：同 ledger+symbol 两边都有）
--   取 ① 结果与 ② 结果在 (ledger_id, symbol) 上的交集，比对金额。
```

核验结果驱动迁移：重叠且等额 → 挂回持仓（§4-12）；无重叠 → 各自独立口径；`is_income` Count=0 → 触发 D1 动态开关（B2 提前）。

## 7. 在途预估接口契约（本期实现，B1 换源预留）

`GET /api/ledgers/{id}/pending-estimate`（scope 内 ledger 归属校验同既有 404 策略）

- 数据源：`transactions WHERE status='success' AND confirm_date > today AND asset_type IN ('money_fund','reverse_repo')`，按 `trade_date`（未确认申购的付款日）金额汇总；**不碰持仓表**。
- 返回：`{ pending_amount_cents, estimated_confirm_date, note: "预估金额，待基金公司确认后计入总资产" }`。
- 契约预留：B1 上线后路径与字段不变，仅数据源切到 pending 表；前端不裸算。

## 8. 验收标准

1. 货基在总资产中只计一次：持仓表达 or 孤儿净额表达（写入层互斥保证），不双计、不漏计。
2. 分布/桑基图中货基市值归「现金/流动资金」，不进「基金投资」；分布总额 = 总资产。
3. `is_income` 流水从本金口径完全隔离，收益桶可独立核对。
4. `positions.is_money_fund` 回填率 100%（含名录未覆盖的代码段兜底项）。
5. 回归：§3.1 四条不变量各有断言；`test_summary_money_fund` / `test_money_fund_income` 全绿。

## 9. 关联

- issue #863（本批次主卡）、#1233（决策 5 反转背景）、#1182（调度器，B1/B2 前置）
- `money-fund-income-plan-2026-08-09.md`（首版方案与 08-14 差异记录 D1~D7）
