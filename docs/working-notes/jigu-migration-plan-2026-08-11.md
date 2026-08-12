# 基估宝（jigu）→ 多多贝（fundmate）数据迁移方案（2026-08-11）

> 状态：**草案待确认**。决策点以"推荐默认值"标注，用户确认或修改后进入脚本开发。
> 数据源：`imoyao/jigu`（fork of `hzm0321/real-time-fund`，v2.4.1）。基估宝为用户自部署实例，拥有 Supabase（`zhfiyyupbegeyvnigenk`）全量数据 + 本地 localStorage。

## 0. 背景与目标

- 用户部署并拥有自己的基估宝实例，核心数据在 **Supabase `user_configs` 表的 `data` JSON 列**（前端 localStorage 为镜像缓存，同步字段 `localUpdatedAt` 佐证）。
- 目标：**一次性**把基估宝用户数据完整迁入 fundmate（SQLite），用户无感；迁移后基估宝退役。
- **不是**双系统长期同步——是单次 ETL + 映射 + 校验。

## 1. 基估宝数据实证（用户真实导出，2026-08-11）

### 1.1 key 清单与迁移分类

| key | 内容 | 迁移分类 |
|---|---|---|
| `holdings` | 全局持仓，**22 只**基金，含 `cost`/`share`/`addedAt` | ✅ 迁（持仓权威源） |
| `groupHoldings` | 分组持仓，`"持有"` 分组 **21 只**（与全局重叠 21 只） | ⚠️ 只作归类，不迁持仓 |
| `favorites` | 自选，**18 个**代码 | ✅ 迁（WATCHING） |
| `groups` | 3 组：`fav`(预置) / `持有` / `嘲风成长` | ✅ 迁（`fav` 忽略） |
| `tags` + `fundTagLists` | **18 个**自定义标签 + 基金↔标签映射 | ✅ 迁 |
| `transactions` | **仅 2 笔**（519771 卖、006650 买） | ⚠️ 不完整，见 §4.2 |
| `fundDailyEarnings` | 2026-04-08 起每日收益历史（all + 持有分组） | ❌ 不迁（fundmate 用净值重算） |
| `fundValuationTimeseries` | 估值分时序列 | ❌ 运行时数据 |
| `funds` | 基金净值/估值快照 | ❌ 不迁（fundmate 自有同步） |
| `pendingTrades` / `dcaPlans` | 空 | ❌ 跳过 |
| `customSettings` / `theme` / `viewMode` | UI 偏好 | ❌ 不迁 |
| `marketIndexSelected` | 指数选择 | ❌ UI 状态 |
| `fundDividends` | 分红 | ❌（可后置，fundmate 无此维度） |

### 1.2 分组/汇总重复 bug 实证

- 全局 `holdings` 22 只 = `groupHoldings["持有"]` 21 只 + `006650`（006650 只在全局）。
- 基估宝 `useSummaryCalculations.js` 汇总逻辑 = 全局 + 各分组累加 → "汇总"tab 实际计算 22+21=43 条，**21 只重复计入**。
- `fundDailyEarnings` 亦印证：`all` 与 `持有分组` 下收益数据几乎完全重叠。
- **结论：迁移到 fundmate 必须去重，否则复刻基估宝 bug。**

### 1.3 持仓明细（22 只，全局权威）

`110012 / 118001 / 160222 / 519771 / 002095 / 002340 / 002910 / 003625 / 005827 / 007356 / 008924 / 008928 / 010710 / 011452 / 012414 / 012708 / 014340 / 015916 / 019053 / 023887 / 025162 / 006650`

自选 18 只中未持有的观察标的：`010624 / 018495 / 013883 / 018550 / 001414 / 016780 / 004814`（其中 `001414` 在 `rtf_unadded_ds` 有"未添加数据源"标记，需单独处理）。

`嘲风成长` 分组 codes：`003231 / 022852`（不在 holdings，属观察仓）。

## 2. fundmate 目标表结构（已核对源码）

| 表 | 关键字段 | 来源文件 |
|---|---|---|
| `watchlist` | symbol/market/asset_type/venue/status/favorite/cost_price/quantity | `backend/app/domains/watchlist/models.py` |
| `watchlist_groups` | name/color/sort_order/is_system/entity_type | 同上 |
| `watchlist_item_group` | item_id/group_id | 同上 |
| `watchlist_tag_defs` | name/color | 同上 |
| `watchlist_item_tags` | item_id/tag_id | 同上 |
| `positions` | symbol/name/market/asset_type/ledger_id/account_name/quantity(**0.0001份**)/avg_price(**分**)/currency/current_price/confirm_date | `backend/app/domains/positions/models.py` |
| `ledgers` | name/ledger_type('fund')/default_allocation/fee_config | `backend/app/domains/ledgers/models.py` |
| `transactions` | symbol/txn_type/trade_date/quantity(**0.0001份**)/price(**分**)/fee/amount(**分**)/status/import_hash | `backend/app/domains/transactions/models.py` |

**精度铁律**：所有金额整数分（×100）、份额×10000，必须走 `app/core/money.py` 的 `Money`。基估宝存的是元/份浮点，迁移脚本必须经 `Money` 换算。

## 3. 决策点（推荐默认值，待用户确认）

| # | 决策 | 推荐 | 理由 |
|---|---|---|---|
| D1 | 持仓权威源 | **`holdings`（全局）唯一权威源**，`groupHoldings` 只作分组归类 | 避免复刻基估宝重复 bug；分组归属以 `groupHoldings["持有"]` 判定，006650 归"未分组/默认" |
| D2 | 标签 | **全部 18 个标签迁移** | 保留完整分类信息，成本低 |
| D3 | 交易流水 | **持仓快照 + 2 笔真实交易均迁入** | 保证持仓准确；缺失历史交易用户后续补录（文档/README 提示） |
| D4 | 分组→账户 | "持有"→`ledgers`(fund, 名"基金持仓")；"嘲风成长"→WATCHING 分组（无持仓不建账户） | 语义保留 + 不产生空账户 |
| D5 | `001414`（未添加数据源） | 迁入 WATCHING 并打标记，但**不参与净值同步** | 与基估宝行为一致 |

## 4. 字段映射表

### 4.1 持仓 → `positions` + `ledgers`

```
ledgers: name="基金持仓"  ledger_type="fund"  default_allocation="longterm"
positions: symbol=基金代码  name=基估宝 name（若无则 fundmate funds 表补）
           market="CN_A"  asset_type="fund"  venue→ledger_id
           quantity=Money.shares_to_min_unit(share)   avg_price=Money.yuan_to_cents(cost/share)
           currency="CNY"  confirm_date=addedAt 前一日（基金 T+1 规则，可空）
```

> 注：`avg_price` = cost/share（元）换算分；需与基估宝 `funds[].addBaseNav` 交叉核验。

### 4.2 交易 → `transactions`

- 字段映射：type→txn_type(买入/卖出)、date→trade_date、share→quantity(×10000)、price→price(×100)、amount→amount(×100)、status='success'。
- `import_hash` = `sha256(f"{symbol}|{type}|{trade_date}|{quantity}|{price}")`，防重导。
- **已知不完整**：仅 2 笔。fundmate 成本/盈亏以 `positions` 快照为准，`transactions` 只用于流水展示，不反推成本。

### 4.3 自选 → `watchlist`

```
favorites 全部 → watchlist: status='WATCHING'（未持有）/ 'HOLDING'（已持有）
       asset_type='fund'  venue='OTC'  market='CN_A'
       cost_price=holdings[code].cost/share（若有）  quantity=share
favorite=true（基估宝 favorites 本身即"自选"语义）
```

### 4.4 分组 → `watchlist_groups` + `watchlist_item_group`

- 忽略 `fav`（isPreset）预置组；迁 `持有`、`嘲风成长`。
- `持有` 组 21 只 = 由 D1 判定为 HOLDING 的 watchlist 项；`嘲风成长` 2 只 = WATCHING。
- color 由 fundmate 默认色板分配（基估宝无颜色字段）。

### 4.5 标签 → `watchlist_tag_defs` + `watchlist_item_tags`

- 18 个 `tags[].name` 迁入 defs（color 默认分配）；`fundTagLists` 映射逐条写入关联。

## 5. 迁移流程

1. **拉数据**：Supabase REST `select * from user_configs`（用服务端 key 或用户 token），落 `backend/scripts/jigu_migration/` 临时 JSON（gitignore）。
2. **清洗**：去重（holdings 为权威）、字段规范化、code 标准化（6 位数字校验）。
3. **换算**：经 `Money` 转分/0.0001份。
4. **入库**：直接写 SQLite（事务包裹，先建 ledger → 再 positions → transactions → watchlist → groups → tags）。
5. **校验**：① 迁入后持仓总数==22；② 每只成本=基估宝 cost 误差<1 分；③ watchlist==favorites 全集；④ 分组归属与 `groupHoldings` 一致；⑤ 校验报告输出。
6. **幂等**：脚本可重复跑（按 import_hash / 唯一约束去重），失败回滚事务。

## 6. 风险与回滚

| 风险 | 应对 |
|---|---|
| 精度错误（元/分、份） | 全部经 `Money`；校验步骤 ② 兜底 |
| transactions 不完整导致成本偏差 | 成本以 positions 快照为准，不依赖流水 |
| 代码失效（基金清盘/改名） | 迁移脚本记录 `001414` 类特殊标记，不参与同步 |
| 误迁移 | 先跑 dry-run 输出报告；正式跑前备份 `invest.db` |

## 7. 待办

- [ ] 用户确认 D1–D5 决策点
- [ ] 拉取 Supabase 全量 `user_configs` 数据核对字段名（key 名与前端一致则复用）
- [ ] 写 `backend/scripts/jigu_migration/` 迁移脚本（ETL + 校验）
- [ ] dry-run 报告 → 正式迁移 → 校验报告
- [ ] fundmate 净值同步任务补拉 22+2 只基金历史净值，验证持仓市值
- [ ] 用户侧确认：持仓/自选/标签/分组在 fundmate 呈现一致后，退役基估宝

## 8. 关联

- 基估宝源码：`imoyao/jigu`（`app/hooks/useSyncManager.js` 同步机制、`useSummaryCalculations.js` 汇总逻辑）
- fundmate 精度规范：`docs/spec/conventions.md` §4.2/§4.3（Money 换算、schema 同步）
- 看板：待建迁移专题 issue
