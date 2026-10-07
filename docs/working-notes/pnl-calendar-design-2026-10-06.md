# 每日收益日历（#1812）设计与口径

> 状态：设计定稿，待实施
> 关联 issue：#1812（宿主 #1123 账户深度分析）
> 分支：`feat/1812-pnl-calendar`
> 参考设计：两张竞品截图 + `docs/features/asset-review.md`（复盘页权威输入）

---

## 0. 结论先行

**#1812 原方案（读 `asset_snapshots` 画日历）不可行**，因`asset_snapshots`
记的是「当前状态」而非「历史状态」，改持仓后历史不会更新（§1）。

本卡改为**按需派生**：从 `transactions` + `daily_worth` / `price_history`
现算任意历史日的份额与市值，日差分得日盈亏。持仓一改，历史自动跟着变——
这正是用户诉求。

落位：**投资概览（welcome）满宽12 列**，组件一形态两容器（嵌入卡 + panorama 弹窗）。

---

## 1. 为什么不用 asset_snapshots（实证）

`write_asset_snapshot`（`summary_service.py:752`）的取数链：

```
write_asset_snapshot(db, family_id, snapshot_date)
  └─ get_distributions(db, family_id)        # summary_service.py:769 —— 无日期参数
  └─ family_pnl_cents(db, family_id)         # summary_service.py:770
  └─ _load_user_assets(db, family_id)        # summary_service.py:397
       └─ db.query(Position).filter(family_id, ownership_status='active').all()
                                                  ↑ 无日期过滤
```

`AssetSnapshotJob.run`（`asset_snapshot_job.py:60`）只传当天日期。

**两个后果**：

1. 历史快照永久冻结。grep `recompute|invalidate|AssetSnapshot.*delete` → 零命中，
   无失效重算钩子。用户改持仓，日历历史数字不动。
2. **回填是主动写错**（比"不更新"更严重）。今天跑
   `write_asset_snapshot(db, fid, '2026-09-01')` 会把**今天**的持仓市值贴上 9/1 标签。
   docstring 写「用于历史回填」但实现不支持。

⇒ 本卡不动`asset_snapshots` 的语义（避免牵动 #1181/#1183/#1220 既有口径），
另建派生路径。

---

## 2. 口径定义（核心，不可含糊）

### 2.1 为什么用 total_pnl 日差分

**采用** `total_pnl_cents`（= `realized + unrealized`，累计值）的**日差分**。

理由（第一性原理）：

- `total_pnl` 是**累计**盈亏。买入建仓瞬间 `unrealized = 市值 − 成本 = 0`；
  追加投入不改变盈亏总额。
- ⇒ 它的**日差分天然免疫资金流**（存取款/买入/卖出都不产生虚假日盈亏）。
- 反之`net_worth` 日环比**会被资金流污染**：存入 ¥10,000 当天凭空"赚" 10,000。

⚠️ 这条必须写进 UI 口径说明，否则用户会看到假盈利。

### 2.2 as-of 口径定义

对日期 `D`：

```
shares_asof(pos, D)   = Σ transactions.quantity  where confirm_date <= D
                                          且 txn_type ∈ (buy, deposit) (+) / (sell, withdraw) (−)
mv_asof(pos, D)       = shares_asof(pos, D) × price_asof(symbol, D)
total_pnl_asof(D)     = Σ_pos [ mv_asof(pos,D) − cost_basis_asof(pos,D) + realized_asof(pos,D) ]
daily_pnl(D)          = total_pnl_asof(D) − total_pnl_asof(D−1)
```

- `price_asof`：基金取 `daily_worth.unit_nav`（`funds/models.py:205-219`，
  uq(fund_code,date)）；场内取 `price_history.adj_close`（**前复权**，`akshare_adapter.py:227`）。
- `cost_basis_asof`：与 `pnl_service.cost_basis_cents`（`pnl_service.py:118`）同口径——
  nav 模式 = 成本均价×份额；balance 模式 = `net_invested_by_position` 的现金流净投入。
- `realized_asof`：Σ `transactions.realized_pnl` where `confirm_date <= D`
  （该字段已按流水存储，清仓删持仓不丢，见 `transactions/models.py:36-39`）。

**恒等式（写成断言测试）**：家庭级 `daily_pnl` = Σ 各账户级 `daily_pnl`。
同 `get_ledger_pnl` 对齐 `get_ledger_distributions` 的既有做法。

### 2.3 四态（必须区分，不可把缺数据画成 0）

| 态 | 判定 | 视觉 |
|---|---|---|
| 真实盈亏 | `has_price` 且 `shares>0` | 涨红跌绿柔和填充，色深∝ \|收益\| |
| 零收益 | `has_price` 且 `daily_pnl==0` | 灰底 + `0.00` |
| **无价格序列** | `valuation_mode='balance'`（银行理财/投顾/实物） | **斜线纹理** |
| 休市 / 非交易日 | 交易日历无该日 | 空白 |

**第3 态是账户级的硬需求**：`market_value_override` 是**单值非序列**
（`positions/models.py:63-70`），`balance` 模式无历史价格 ⇒ 该账户日历整月空白。
不加斜线态用户会以为功能坏了。

⚠️ 参考图没有第 3 态（它是单账户"股票+基金"视图，全都有价序列）。

---

## 3. 数据策略准入四问（AGENTS.md 强制）

| 问 | 答 |
|---|---|
| **谁在用？** | `PnlCalendar` 组件 → welcome 嵌入卡 + panorama 弹窗；接口 `GET /api/summary/pnl-calendar/` |
| **什么场景用？** | 用户打开投资概览看"这个月哪几天赚了/亏了"；在资产总览点日历图标局部查看 |
| **缺了会怎样？** | 组件无数据 → 降级为空态卡，**可接受**（现有「收益趋势」占位本就是空的） |
| **成本多大？** | **不新增表、不加列**。纯读取既有 `transactions` / `daily_worth` / `price_history` |

**结论：不新增任何数据实体** ⇒ 无需过 `db_factory.DATA_DOMAIN_REGISTRY` 登记
（仅新增读路径 + service）。数据域归属不变（`transactions` 属 user 域，
`daily_worth`/`price_history` 属 market 域）。

⚠️ **跨域两步法**：净值在 market 域、流水在 user 域，两引擎无法 JOIN。
必须走 `services/cross_domain.py`（`AGENTS.md` 数据域硬规则 §3），
先取 `position_id → symbol` 键列表，再用 `in_` 批量取价，**禁止手写 N+1**。

---

## 4. 落位与交互

### 4.1 welcome 五排（核心资产看板扩满宽）

```
① 欢迎语 ticker
② 核心资产看板（满宽 12，资产构成分布 5 列跟着变宽）
③ 收益日历（满宽 12）← 本卡新增，替换原「收益趋势」占位
④ 年化 XIRR(8) + 市场温度(4)
⑤ 持仓市值最大资产(12)
```

**为什么②要扩满宽**：删掉右栏「收益趋势」后若仍保持 8 列，右侧留 4 列空洞。
`design.md` MetricGrid 条明令「禁止右侧大片空白」。

**为什么删得合理**：`WelcomeAssetBoard.vue:133-147` 的「收益趋势」是**纯文字空占位**
（「收益趋势 · 即将上线」，无 ECharts 实例、无数据请求）。
⇒ 删除不损失任何已有功能，两处占位合并是**空间收敛 + 功能补齐**，非重复渲染。

### 4.2 一组件两容器

| 层级 | 容器 | 触发 |
|---|---|---|
| L1 | welcome 嵌入卡（满宽） | 页面加载 |
| L2 | panorama 弹窗 | `OverviewSummaryCard.vue:136` 的 `ep:calendar`（tooltip 现为「资产月历（后续版本推出）」，**明确预留位**） |
| L3 | 复盘页 | 另开卡，路由 `/asset-review` 不存在 ⇒ 点击某天**优雅降级为提示**，不跳空白页 |

L1/L2 复用同一 `PnlCalendar`，口径唯一，绝不写两遍逻辑。

> **#1925 更新（2026-10-07）**：容器由两处变**三处**——新增账户详情页
> （`LedgerDetailOverview.vue`，传账户级 `ledger_id`）；L2 的 `ep:calendar` 由**弹窗**
> 改为**右列卡片体的原地开关**（`OverviewSummaryCard.vue` 的 `calendarVisible` 已移除），
> 页面不再被遮罩盖住，切换时标题 / tooltip / `aria-label` / 图标四者同步变化。
> 「三处复用同一组件、口径唯一」这条不变。

### 4.3 双视图（日历图 ⇄ 柱状图）

采纳用户方案：两视图共用同一份数据序列。

- **日历图**：月视图格子，回答「哪几天赚了/亏了」
- **柱状图**：**月内逐日**（30 根柱，非年级的月度），回答「月内起伏」

⚠️ 参考图的柱状图是年级的（2018-2026 每年一根）——若照做会与复盘页重复。
本卡做月内逐日，与日历互补：日历定位某天，柱状看整体节奏。

「累计收益 / 净资产走势」口径**日历覆盖不了**（那是净值曲线非日盈亏柱），
归入复盘页规划，组件不硬塞。

> **#1925 更新（2026-10-07）**：日历卡扩为**日 / 月 / 年三粒度**，柱状图随之泛化为
> 「一根柱 = 一天 / 一月 / 一年」，日历图仍只服务日粒度。
> 上面「若照做会与复盘页重复」的顾虑在 #1812 成立、到 #1925 已解除——`/asset-review`
> 至今仍不存在（L3 还是优雅降级），而「月/年切换」本就列在 §4.4 的**借鉴**清单里。
> 三粒度不是三条口径：月 / 年是**同一条日序列的切法**，聚合下推在后端
> （`GET /summary/pnl-calendar/?granularity=day|month|year`），前端只做呈现。

### 4.4 借鉴与必改（对参考图）

**借鉴**：月/年切换、格内「金额+收益率」双信息、当月合计+分项一行小字、
月份切换过渡动画、今日细边框高亮。

**必改**：
1. **饱和纯色填充 → 柔和填充**。参考图**蓝跌**，本项目规范是**绿跌**
   （`--color-fall` #7BC49A）；饱和红蓝+白字未验对比度，
   违反 `design.md`「逐一核对全部底色取最差者判达标」。
2. **「日历图/柱状图」不砍**（原判断已更正：既有"收益趋势"是空占位，非重复）。
3. **基准对照（上证指数）移复盘页**——`asset-review.md` 组件 1 已定义基准选择器，本卡重复造。
4. **必须新增第 3 态斜线纹理**（见 §2.3）。

---

## 5. 实施步骤

| # | 任务 | 产出 |
|---|---|---|
| 1 | 本文档 | ✅ |
| 2 | `services/pnl_calendar.py` | as-of 份额/价格/盈亏计算，家庭级+账户级同一路径 |
| 3 | `GET /api/summary/pnl-calendar/` | 逐日序列 + 当月合计 + 四态标记；`ledger_id` 可选 |
| 4 | `components/PnlCalendar/index.vue` | 日历图/柱状图切换，两容器复用 |
| 5 | 接入 welcome + 替换 panorama 预留位 + 删「收益趋势」占位 | — |
| 6 | 测试 + `pnpm typecheck` + 前端真机走查 | — |

## 6. 验收标准（对齐 issue + 本设计）

- [ ] 指定账户/家庭指定月份可见逐日收益
- [ ] **四态可区分**，缺数据不画成 0
- [ ] 数值全部来自后端，**前端不做二次盈亏计算**
- [ ] UI 写明口径：`total_pnl` 日差分（免疫资金流）+ 非逐持仓 + 数据日期
- [ ] 月合计 = 区间内日序列求和（含边界日）
- [ ] **存取款当日不产生虚假日盈亏**（资金流免疫验证）
- [ ] 家庭级 = Σ 账户级（恒等式断言）
- [ ] 改持仓后历史自动更新（派生口径的根本优势，需实测验证）

## 7. 遗留（另开卡，不在本卡）

- **复盘页** `/asset-review` 本体（设计输入：`docs/features/asset-review.md`）
- **`asset_snapshots` 回填语义修正**（当前 `snapshot_date` 参数形同虚设，
  历史回填会写错数据；影响 #1181/#1183 既有口径，需独立评估）
- 累计收益/净资产走势曲线（净值曲线，非日盈亏）

## 8. 已知阻塞（非本卡范围）

`daily-snapshot.yml` 最近 60 次运行**零成功**，根因非代码：
`market 域 Hrana HTTP 308 永久重定向`（Turso secret host 需人工核对，告警 issue #1490）。

用户 2026-10-06 指示暂不考虑远端 DB，已移出关键路径。
⚠️ 但派生方案的价格数据在生产同属market 域，**此洞不补则生产日历同样为空**。
