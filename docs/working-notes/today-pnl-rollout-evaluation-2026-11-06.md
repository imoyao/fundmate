# 当日收益估值扩展 · 整体评估（第二轮，2026-11-06）

> 第一轮只做评估；本轮用户已逐条拍板，并落地第一批已闭合改动。
> 代码基线：独立 worktree `D:/codes/fm-today-pnl-ui`，基于 `origin/dev` = `10a5bec195`（并发会话已推进）。
> 本批只改文案 / UI / 决策文档，**未实现估值接口**——接口形态仍在讨论。

---

## 1. 五问拍板结论（用户本轮答复）

| 问 | 用户答复 | 落地判定 |
|---|---|---|
| ①「总收益」指哪个 | **两个数据都要**：`累计总收益`（`/summary/` 的 `total_pnl_cny`，D82 四出口含买入费）与 `最新收益`（当日估值 / 当日实际收益） | 概念已澄清；**累计总收益的展示位仍待定**（见 §5 疑问 1） |
| ② 术语与集合边界 | 标题直接写「股票」「基金」（参照同花顺投资账户），集合边界改用**一行小字**，不塞进标题；决策文档一起改 | ✅ 本批已落地（D91） |
| ③ 账户列表 / 详情 | 账户列表页需要；账户详情页「工作量不大就都加上」，但担心干扰 | ✅ 详情页评估见 §4；工作量小，**建议纳入本期**，待接口落地后实施 |
| ④ 投资策略页 | 澄清：指的是 **`/asset/portfolios` 投资组合页**，不是 `/asset/strategies` 标签页 | ⚠️ 第一轮按标签页评估的前提作废，见 §3.2 |
| ⑤ 银行 / 贵金属 | 本期排除；真正的银行理财无估值时**不显示估值即可**；银行里买的是基金，可以估值 | ✅ 口径关键：**按持仓 `asset_type` 判定可估值，不按账户 `ledger_type`** |

补充拍板：

- **证券账户徽标**「证」→「股」（只改单字徽标，「证券账户」全称不改）。✅ 已落地。
- **首页负债率 `51.5%` 出现两次**（chip + 结构条图例）是 UI 错误，需修复。✅ 已落地。
- 「最新收益」定义：**盘中 / 官方净值未发布时显示估值（estimated），官方净值到位后显示实际当日收益（confirmed）**——与现有 `estimated → confirmed` 状态机（含基金收盘估值定格 #2141）完全一致，无需改代码。

---

## 2. 本批已落地改动（分支 `fix/today-pnl-labels`）

后端：`asset_class.CLASS_LABELS` 改「股票 / 基金 / 其他」；`today_pnl.py` 口径说明补「balance 模式显示 `—`、按持仓判定」；`test_today_pnl.py` 断言同步。
前端：首页两列 + 账户管理两卡标题简化为「股票」「基金」并各加一行集合边界小字；`/funds`、`/stocks` 下钻页副标题 / Tab / 空态统一；证券渠道徽标改「股」；首页家庭带结构条图例删除重复负债率百分比。
文档：按 append-only 追加 **D91**（不改 D77 原文），活跃规范 `position-structure-view-by-ledger-type.md` 补更新说明。

**关键取舍**：只改**用户可见标签**，`CLASS_*` key、D77 分桶口径（stock/etf/bond → stock、fund → fund）、`venue` 编码、代码形态、行情源等**技术口径**中的「场内 / 场外」全部保留。全仓替换会误伤 `conventions.md` 的编码规则，且「场外基金收盘估值定格」说的是数据源、不是标题。

**集合边界必须写清**：账户管理页「基金」卡 = `fund + money_fund`，首页「基金」列 = `fund`（不含货基）；两边同名不同集，小字不写清用户拿数字对不上会当成 bug。

验证：后端 `test_today_pnl.py` 11 passed；`ruff` 全绿；前端 `ledger.spec.ts` 8 passed（在 worktree 内）、`eslint --max-warnings 0` 通过；`prettier --check` / `stylelint` / `check_vue_size` 通过。新 worktree 无 `node_modules`，用目录联接到主仓依赖后完成本地校验；CI 仍需复核全量门禁。

---

## 3. 接口设计评估：「一个通用接口」 vs 「每个页面一个接口」

### 3.1 结论：**单资源 + 维度/作用域参数**，不是每页一个接口，也不是把三个域焊进一个 URL

REST 的「域」是**资源边界**，不是**页面边界**。当日估值是一个**派生只读资源**（一份当日 PnL 快照），「账户 / 组合 / 品类」是同一份数据的**作用域（scope）**与**分组维度（dimension）**，不是三种不同资源。对同一资源按维度切片，标准做法就是查询参数；为每页各开一个端点会产生 N 份状态语义、N 份估/确认徽标、N 次全仓遍历，正是用户说的「后期修改要各处修改」。

仓库已有同款先例（不需要新发明）：

| 端点 | 参数形态 |
|---|---|
| `/summary/groups/` | `dimension=type\|account\|allocation` |
| `/summary/position-structure/` | `ledger_id` / `portfolio_id`（互斥，同传 400） |
| `/summary/pnl-attribution/` | `ledger_id` / `portfolio_id`（互斥，`Σ positions[].pnl ≡` 契约） |
| `/summary/pnl-calendar/` | `ledger_id`（不传 = 家庭级） |
| `/performance/money-fund-income/` | `scope=ledger\|portfolio` |

### 3.2 耦合疑虑的正面回答：要区分两种「耦合」

| | 该集中（内聚） | 该隔离（不耦合） |
|---|---|---|
| 内容 | 盈亏口径、估/确认状态、盘中实时价替换、缺数语义、`Σ groups ≡ total` | 页面文案、占比、排序、徽标样式、卡片布局 |
| 落点 | `services/today_pnl.py` 唯一算法出口 + `services/scope.py` 唯一作用域解析 | 各页面自己的 composable / 组件 |

**一个接口 ≠ 把三个页面耦合起来**，前提是响应体是**稳定的通用契约**，后端完全不知道「这是首页还是账户页」。反例才是真耦合：后端为首页返回 `classes[]`、为账户页返回 `cards[]`、为组合页返回 `portfolios[]` 三套形状，或在服务层写 `if page == 'welcome'`。

建议契约（单端点，参数化）：

```
GET /api/summary/today-pnl/
    ?scope=family|ledger|portfolio        # 作用域，默认 family
    &ledger_id=|portfolio_id=              # 互斥，沿用 position-structure 同款 400
    &dimension=class|ledger|portfolio     # 分组维度，默认 class

→ { date, is_today, status, scope, dimension,
    total_pnl, total_rate, market_value,
    groups: [{ key, label, pnl, rate, market_value, status, holdings }],
    unvalued_count, holdings }
```

- 首页：`dimension=class`（`groups` 即现有两列，向后兼容 `classes` 别名）
- 账户列表：`dimension=ledger` —— **一次遍历返回全部账户**，不要 N 次调用
- 组合列表：`dimension=portfolio` —— 同上
- 账户详情：`scope=ledger&ledger_id=X&dimension=class`
- 组合详情：`scope=portfolio&portfolio_id=Y&dimension=class`

**为什么不用嵌套资源** `/ledgers/{id}/today-pnl/`：REST 允许，但列表页需要一次拿全部账户，嵌套会产生 N 个 URL + N 次全仓遍历，`Σ ≡ total` 也难验。本仓 `/summary/groups/?dimension=` 已给出答案。

**边界（防止退化成万能接口）**：

- 不把策略标签（多对多、`Σ 标签 ≠ 家庭`）塞进 `dimension`——第一轮的标签页前提已作废，本期不做。
- 不把「累计总收益」塞进这个资源：它是 `/summary/` 的存量口径，与「当日快照」时间语义不同，属不同资源。
- `dimension` 与 `scope` 用白名单，非法组合返回 400；参数解析放 schema / services，`summary/views.py` 视图厚度基线 441 行只减不增，逻辑必须下沉。
- 决策集恒取家庭全量（`pnl_calendar.py:991-998`），否则会重现 D80 实测过的 93,712.70 差额。

### 3.3 组合维度（`/asset/portfolios`）修正第一轮结论

用户指的是**投资组合页**（路由 `views/asset/portfolio/index.vue`），不是标签页。这反而是好消息：组合是**互斥归属**（D71，解析唯一出口 `services/scope.filter_positions_by_scope`），`Σ 组合` 可加总，不像标签多对多不可加总。

现状：组合卡只有 `pnl` / `pnl_rate`（累计）与市值；组合详情持仓表已有 `PnlDualLine`（已确认 / 当日预估逐行），但**组级当日收益为 0**。故组合页是「补一个组级聚合」，不是从零接线。

唯一硬约束：**未归属持仓不进任何组合**（D71），故 `Σ 组合 ≠ 家庭`。需决定是否单列「未归属」桶（见 §5 疑问 2）。

---

## 4. 账户详情页加当日估值：会不会干扰？

**结论：不干扰，建议纳入本期；但要「替换占位」而不是「再堆一个指标」。**

- 账户卡里「当日盈亏」本来就是 `--` 占位（`LedgerCardMetrics.vue:35-47`，`ledgers/views.py` 硬编码 `daily_pnl: None`），详情页首卡已有「总资产 + 持仓盈亏 + 货基今日收益 + 8 个次级指标 + 环形图」。把占位换成真实值，是**补完既有槽位**，不是新增第 9 个指标。
- 三条防干扰约束：
  1. 数字层级低于总资产（用 `--text-num-strong` + `tabular-nums`，不用 hero 字号），只给最关键的 1 个数上强调色；
  2. 缺数显示 `—`，绝不 0.00，且不重复出现两套「估」语义（货基今日收益是另一条链路，需标注口径差异）；
  3. 复用同一个 `today-pnl` 端点，不新增算法。
- 工作量：接口参数化后，前端只是消费一个字段 + 复用 `ValuationSourceBadge`；`LedgerDetailOverview.vue` 实测 348 行、距 400 行阈值有 52 行余量，`LedgerCard.vue` 380 行（余量 20 行）更紧。新增逻辑仍建议下沉到 `useLedgerOverview.ts` 或新子组件，避免贴线文件继续变长。属于「不大」。

---

## 5. 剩余疑问（仅 3 个，均不阻塞本批改动）

1. **累计总收益放哪**：概念已澄清（与最新收益是两个数），但展示位未定。候选：首页底注（现为家庭净资产 / 总负债）、账户管理首卡（现为净资产 + 配置）、账户卡（现为持仓盈亏）。建议**首页底注加一行**，不动已有 4 项存量数字——避免与账户管理首卡的重复继续扩大。
2. **组合维度未归属持仓**：`Σ 组合 ≠ 家庭`（D71）。组合列表是只显示已归属部分并标注「不含未归属」，还是单列一个「未归属」桶保证可加总？
3. **「最新收益」在无报价日**：沿用现有「回退最近有价交易日 + `is_today=false` + 标明截至日期 + 前端 replaceBase 实时价替换」，还是直接显示 `—`？建议沿用（现有 `today_pnl` 行为），需在验收标准里写死，避免各页面各做一套。

其余均已闭合：术语、集合边界小字、徽标、负债率去重、银行/贵金属排除、银行内基金按持仓估值、账户列表 + 详情、组合页范围。

---

## 6. 下一批实施顺序（接口形态确认后）

1. `today_pnl.build_today_pnl` 参数化 `scope` / `dimension`，泛化 `_compute_days` 收集器为多桶；`services/scope.py` 统一解析；视图只加参数校验。
2. 前端通用 `getTodayPnl(params)`，各页面自己的 composable 消费 `groups[]` 切片；文案 / 占比 / 排序留在页面侧。
3. P1 账户列表 + 账户详情 + 两张聚合卡；P2 组合列表 + 组合详情；验收 `Σ groups.pnl ≡ total_pnl`（含未归属桶）、`null → —`、`estimated` 徽标同源。
4. 银行理财 / 贵金属本期不做；`balance` 模式一律 `—`。

---

## 7. 关键证据索引

- 唯一盈亏口径：`backend/app/services/pnl_calendar.py:22-41, 991-998, 1287-1305, 1716-1738`
- 当日收益出口：`backend/app/services/today_pnl.py`、`backend/app/domains/summary/views.py:255-269`
- 参数化先例：`backend/app/domains/summary/views.py:99-126, 176-189, 276-313`
- 组合解析：`backend/app/services/scope.py`（D71）、`frontend/src/views/asset/portfolio/`
- 账户卡死位：`backend/app/domains/ledgers/views.py:394-428`、`frontend/src/views/asset/ledgers/components/ledgerCard/LedgerCardMetrics.vue:35-47`
- 治理：`AGENTS.md:2146-2153`（AI 提交标注）、`:944-953`（数据准入四问）；`scripts/guard_pr_four_questions.mjs:26-48`；`scripts/check_view_thickness.py`；`scripts/check_vue_size.mjs`
- 决策：`docs/spec/decisions.md` D77 / D80 / D82 / **D91**
