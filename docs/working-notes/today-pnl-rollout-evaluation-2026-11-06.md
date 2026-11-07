# 当日收益估值扩展 · 整体评估与落地（2026-11-06 ~ 11-07）

> 第一轮只做评估；第二轮用户逐条拍板并落地术语 / UI / 决策（D91）；
> 第三轮（2026-11-07）完成通用估值接口与首页 / 账户 / 组合全站接入（D92），详见 §8。
> 代码基线：独立 worktree `D:/codes/fm-today-pnl-ui`，功能分支 `fix/today-pnl-labels`，
> 基于 `origin/dev` = `10a5bec195`（远程后推进到 `d410061f2e`，改动文件不重叠）。
> §3 ~ §7 保留评估当时推理；**最终契约以 §8 与 D92 为准**（含 `scope` 不入参等勘误）。

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

评估建议契约 → **最终落地契约**（2026-11-07，D92）：

```
GET /api/summary/today-pnl/
    ?dimension=class|ledger|portfolio     # 分组维度，默认 class
    &ledger_id=|portfolio_id=             # 互斥，沿用 position-structure 同款 400

→ { date, is_today, state, status, total_pnl, total_rate,
    invested_value, invested_ratio_of_assets, other_value,
    unvalued_count, unvalued_value,
    scope, dimension, ledger_id, portfolio_id, excludes_unassigned,
    groups: [{ key, label, pnl, rate, market_value, status }],
    classes: [...], holdings: [...] }
```

**勘误**：评估稿曾把 `scope` 也列为 query 入参；实现时按仓库 `position-structure`
惯例**去掉**——`scope` 由两个 id 推导并在响应回带，不给调用方制造可能与 id 矛盾
的第三种真相。另 `groups[]` 不含 `holdings`（价格替换明细只在 `dimension=class`
的顶层 `holdings[]` 下发）。

- 首页：不传参（`dimension=class` / `scope=family`）—— `classes` 与 `groups` 同源
- 账户列表：`dimension=ledger` —— **一次遍历返回全部账户**，不要 N 次调用
- 组合列表：`dimension=portfolio` —— 同上，按 `excludes_unassigned` 标小字
- 账户详情：`ledger_id=X`（维度默认 class）
- 组合详情：`portfolio_id=Y`（维度默认 class）

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
- 工作量：接口参数化后，前端只是消费一个字段 + 复用 `ValuationSourceBadge`；**勘误**：评估时写的 348 / 380 行是旧快照，复核时 `LedgerDetailOverview.vue` 与 `LedgerCard.vue` 已分别约 385 / 394 行，距 `check_vue_size` 的 400 行阈值只剩十几行（行数随并发会话持续变化，不再写死）。落地时据此把逻辑下沉到 `useLedgerOverview.ts` 与新建的 `LedgerTodayPnlMetric.vue`，并压缩 `LedgerCard.vue` 顶部注释实现净减行数；CI 同款 `--mode fail --baseline` 门禁复核通过。属于「不大」。

---

## 5. 三个剩余疑问：已拍板并落地（2026-11-06 用户答复）

1. **累计总收益放哪** → 按建议，**首页底注加一行**，取 `props.summary.total_pnl_cny`，不动家庭净资产 / 总负债 4 项存量数字，不新增请求。落地：`WelcomeAssetBoard.vue` → `TodayPnlCard.vue` 底部 `.today-pnl__cumulative`。
2. **组合维度未归属持仓** → 用户拍板「只显示已归属部分，不单列未归属桶，并标记不含未归属」。落地：桶函数对未归属持仓返回 `None`，`total_pnl = Σ groups[].pnl` 天然只含已归属；响应 `excludes_unassigned` 为 true 时，组合列表页与组合详情收益卡各显示一行小字「当日收益不含未归属持仓」。
3. **「最新收益」在无报价日** → 沿用现有方案（回退最近有价交易日 + `is_today=false` + 标截至日期 + 前端 `replaceBase`）。落地：`_pick_target` 改为按动态桶键判定有价日，新增直接单测钉住；首页与账户 / 组合页共用同一份 `date` / `is_today`。

其余均已闭合：术语、集合边界小字、徽标、负债率去重、银行 / 贵金属排除、银行内基金按持仓估值、账户列表 + 详情、组合页范围。

---

## 6. 实施顺序：已按此顺序落地（2026-11-07）

1. ✅ `build_today_pnl` 参数化 `dimension` / `ledger_id` / `portfolio_id`；`_compute_days` 新增可选桶函数；`services/scope.py` 唯一解析；参数白名单下沉 `TodayPnlQuery`，视图净减 3 行。
2. ✅ `getTodayPnl(params)` + 唯一取数底座 `useTodayPnlGroups.ts`；页面只消费 `groups[]`，文案 / 排序留页面侧。
3. ✅ 账户列表 / 详情 / 两卡 + 组合列表 / 详情全接入；`Σ groups.pnl ≡ total_pnl`、`null → —`、`estimated` 徽标同源均有判据。**勘误**：「含未归属桶」是评估稿口径，用户拍板改为不单列，见 §5.2。
4. ✅ 银行理财 / 贵金属本期不做；`balance` 模式一律 `—`（不入桶）。

---

## 7. 关键证据索引

- 唯一盈亏口径：`backend/app/services/pnl_calendar.py:22-41, 991-998, 1287-1305, 1716-1738`
- 当日收益出口：`backend/app/services/today_pnl.py`、`backend/app/domains/summary/views.py` 的 `today_pnl()`
- 参数化先例：`backend/app/domains/summary/views.py` 的 `position-structure` / `pnl-attribution` 端点
- 组合解析：`backend/app/services/scope.py`（D71）、`frontend/src/views/asset/portfolio/`
- 账户卡当日盈亏槽位：`frontend/src/views/asset/ledgers/components/ledgerCard/LedgerCardMetrics.vue`（后端历史占位见 §8.4）
- 治理：`AGENTS.md:2146-2153`（AI 提交标注）、`:944-953`（数据准入四问）；`scripts/guard_pr_four_questions.mjs:26-48`；`scripts/check_view_thickness.py`；`scripts/check_vue_size.mjs`
- 决策：`docs/spec/decisions.md` D77 / D80 / D82 / **D91** / **D92**

---

## 8. 最终落地（2026-11-07）

### 8.1 后端

| 文件 | 改动 |
|---|---|
| `services/pnl_calendar.py` | `_compute_days` 新增可选 `bucket_of` / `bucket_keys`，默认 `class_of_position` 且逐位等价；桶函数返回 `None` = 不进任何桶，docstring 明确 `total_pnl` 必须取分桶和而非 `daily_pnl` |
| `services/today_pnl.py` | `build_today_pnl(db, family_id, *, dimension, ledger_id, portfolio_id)`；`_dimension_buckets` 统一三种分组与「可估值 + 已归属」过滤；`_market_value_by_class` → `_market_value_by_bucket`；组装 `groups[]` 与 `excludes_unassigned` |
| `domains/summary/schemas.py` | `TodayPnlQuery`：`dimension` 白名单 + 可选正整数 id |
| `domains/summary/views.py` | `parse_query` 放在 try 外；`ValueError → 400`；`**query.model_dump()` 一行接线；端点 15 → 12 行 |
| `scripts/check_view_thickness.py` | `summary/views.py` 基线 441 → 438（收紧，附 dated 注释） |

三条写进模块 docstring 的硬口径：**决策集家庭全量 / 值集按 scope 缩小**；判据是持仓 `asset_type` 而非账户 `ledger_type`；**`total_pnl = Σ groups[].pnl`**。

### 8.2 前端

- `api/summary.ts`：`TodayPnlDimension` / `TodayPnlQuery` / `TodayPnlGroup`；`getTodayPnl(params?)`；`TodayPnlData` 补 `scope` / `dimension` / `groups` / `excludes_unassigned`。
- `composables/useTodayPnlGroups.ts`：唯一取数底座，一次批量取数 + `byKey` 索引 + getter 参数 `watch` 自动重取；路由 id 为 `NaN` 时跳过请求。页面只消费，**不二次计算盈亏**。
- 首页：`WelcomeAssetBoard` 直出 `total_pnl_cny`，`TodayPnlCard` 底注加「累计总收益」（`size="xs"` + 600 字重 + `tabular-nums`，中性色不抢 hero）。
- 账户列表：`useLedgerList` 一次 `ledger` + 一次 `class` 批量取数；`LedgerCardMetrics` 把 `--` 换成数字 / `—` + `ValuationSourceBadge`；`LedgerOverviewSection` 两卡补当日收益小字，基金卡显式标「不含货基」（其市值含货基、当日收益不含，集合本就不同）。
- 账户详情：`useLedgerOverview` → `useLedgerDetail` 透传 `todayPnlData`，新建 `LedgerTodayPnlMetric.vue`（父页仅 +2 行）。
- 组合列表：`index.vue` 一次 `dimension=portfolio`，`PortfolioCard` 补「当日收益」，页面级小字按 `excludes_unassigned` 显示。
- 组合详情：组级收益放进自含取数的 `PortfolioReturnCard`，`detail.vue` **零改动**（398 行贴线）。

### 8.3 验收

- 后端：`pytest tests/services/test_today_pnl.py -p no:xdist -q` → **20 passed**（11 条首页回归 + 9 条新用例）；`ruff` 绿；`check_view_thickness.py` 绿。
- 前端：`pnpm typecheck`（tsc + vue-tsc）、`pnpm test:unit` **164 files / 2242 tests**、`eslint --max-warnings 0`、`prettier --check`、`stylelint`、CI 同款 `check_vue_size --mode fail --baseline` 全绿。
- 关键回归：默认请求逐位等价、`Σ groups.pnl ≡ total_pnl`、scope 互斥与非法参数、组合「显式覆盖继承」与未归属排除、无估值资产不入桶、单次 `_compute_days`、动态桶键回退、账户级 `holdings` 裁剪。

- **CI 首轮红灯与修复（提 PR 后补）**：本地只跑 `ruff check`、漏跑 `ruff format --check`，CI 抓到 `today_pnl.py` 两处多行调用需压行；`guard_service_size.py` 基线未随通用化回写（该判据要求基线与实测**逐项相等**，不是「不超过」），按 #2141 先例以 `--report` 实测值回写 `today_pnl` / `pnl_calendar`，并把 `asset_class` 压缩 docstring 后收紧到 63 行，附 dated 注释。教训：后端本地验证要跑全守卫（`ruff format --check .` + `guard_service_size.py` + 对应单测），不能只对改动文件跑 lint。

### 8.4 未做 / 边界

- 银行理财、贵金属等 `balance` 模式本期不做，一律 `—`；不新增估值数据源。
- 策略风格标签（多对多、`Σ 标签 ≠ 家庭`）不进 `dimension`。
- 组合维度 `Σ 组合 ≠ 家庭`（D71）是口径而非缺陷，靠一行小字说明。
- `origin/dev` 已推进到 `d410061f2e`（#2879 import 预览行重构），与本分支改动文件不重叠；分支只 push、暂未开 PR（待确认后再提，避免 auto-merge 抢在人工审阅前合并）。
- **同批清理**：`ledgers/views.py::get_ledger_summary()` 的历史占位 `daily_pnl: None` 已删除。核实链路：`LedgerService` 三个 stats 方法均不产出该字段、`LedgerSummaryData` 全接口无声明、前端零消费；唯一消费方是 `test_ledgers.py` 里一条把占位钉住的 `assert data['daily_pnl'] is None`，已改为**正向契约判据** `assert 'daily_pnl' not in data`（防止死字段回潮）。留着这个字段会诱导后来者在这里另算一套当日盈亏（D92 要防的分叉）。删除**不增加行数**（只去掉一个 dict key），故 635 行视图厚度基线不受影响；字段归属说明并入原有 docstring 行。**过程勘误**：初查曾误判「测试零断言」，是 `test_ledgers.py` 全量单测跑出 `KeyError` 才暴露——判据以测试实跑为准，不以文本搜索为准。
