# 对账中心第二轮优化方案（用户视角 · 细节与上下文补全）

> 状态：**已拍板、已实施**（2026-11-07）。§2 诊断写于动工前，保留原样作为依据；
> 实际落地与验证结果见 §11，**以 §11 为准**。
> 上一版 `reconcile-workbench-redesign.md` 已实施并合入（PR #2974，`1971c618d0`）。
> 本轮依据 owner 第二轮截图与逐条反馈：页面骨架方向对了，但**单条待办内部的上下文、术语、
> 数据口径与长列表交互仍不合格**。
>
> owner 拍板结果：① 两处后端小改**都允许**；② **右侧抽屉 + 队列分页**；
> ③ 「把持仓改成」**本期不合并**手动录入持仓表单（见 §7）。

---

## 1. 结论先行

上一轮解决的是「用户该做什么」，本轮要解决的是「用户能不能看懂并做对」。
实证后发现三类问题，性质不同，不能混在一起改文案了事：

| 类别 | 问题 | 性质 |
|---|---|---|
| A. 缺数据 | 差异列表没有产品名；`cash` 没翻译；货币基金被误判为要补税 | **数据链路断了**，改文案无效 |
| B. 缺上下文 | 补充弹窗只有表单、没有「缺哪条」；看不到交易流水与账本 | **信息架构问题**，需改容器形态 |
| C. 缺交互约束 | 队列几百条全堆一页；处理区在队列下方，处理完要往回滚 | **长列表交互问题**，需分页 + 抽屉 |

⚠️ 有一处与上一版文档 §9「后端 API 路径、请求体、数据库零改动」冲突：
A 类里「补产品名」「货币基金免税」各需后端一处小改。见 §7，**owner 已批准两处都做**。

---

## 2. 逐条诊断（owner 反馈 → 代码根因 → 修法）

### 2.1 只有代码、没有产品名

- 根因：`GET /api/reconciliation/discrepancies/` 出参 13 个字段**无 `name`**
  （`backend/app/domains/reconciliation/views.py:125-170`，字段清单 `:154-167`）；
  `DiscrepancyItem`（`frontend/src/api/reconciliation.ts:8-21`）也没有 `name`。
  `DomainBDiscTable.vue:11` 只渲染 `prop="symbol"`；`SupplementDialog.vue:4` 标题
  `` `就地补充 · ${target?.symbol}` ``；`reconGroupTitle()`（`utils/reconDisplay.ts:127-130`）
  **原样返回 symbol**，不做任何名称/特殊码翻译。
- 对比：E 域 `DividendTaxPendingItem` **有 `name`**（`api/reconciliation.ts:258-274`，
  后端 `PendingTaxItem.name = div.position_name`），`taxItem()` 也用了它
  （`utils/reconQueue.ts:237,244`）——所以「补记缺漏」有名字，「核对差异」没有，**不是全站都没做**。
- 修法：后端出参补 `display_name`，批量解析（见 §7.1）；前端表格把「代码」列换成
  「产品」列（主行 `名称`，副行 `代码`），弹窗/抽屉标题统一 `名称 · 代码`。

### 2.2 「类型」列 / 「数量」/「孤儿」/「理论 / 实际 / 差异」看不懂

- 根因：`DISCREPANCY_TYPE_LABELS`（`frontend/src/constants/index.ts:202-207`）
  = `{ quantity: "数量", cost: "成本", cash: "资金", orphan: "孤儿" }`，
  经 `discFormat.ts:typeLabel()` 直接进表格。`orphan: "孤儿"` 是**数据库术语**，不是人话。
  列名「类型 / 理论 / 实际 / 差异」全是后端列名直译，且数值**没有单位**（都是份额）。
- ⚠️ 该映射是全站共享（同文件 `:198-200` 注释：`DiscrepancyBanner` 也用），
  **不能直接改全局表**，否则别的页面文案一起变。
- 修法：对账表格用**本页专用**翻译表，列名与取值一起改：

  | 现在 | 改成 | 说明 |
  |---|---|---|
  | 类型 | 问题 | 列头带一句「哪里对不上」 |
  | 数量 | 份额对不上 | 说明两处份额不一致 |
  | 成本 | 成本对不上 | — |
  | 资金 | 资金对不上 | — |
  | 孤儿 | 有持仓、缺流水 | 说清现象，不说存储术语 |
  | 理论 | 按流水算 | 加单位「份」 |
  | 实际 | 账上记的 | 加单位「份」 |
  | 差异 | 差多少 | 加单位「份」，正负加上「多 / 少」|

  数字统一走 `reconQuantity()`（最多 4 位、千分位、负号只生成一次），
  并在表格上方加一行「按流水算 = 期初快照 + 之后所有买卖；账上记的 = 当前持仓」。

### 2.3 「处理区 · 001982」后面的数字看不懂

- 根因：`ReconQueueDetail.vue:11` `` :title="`处理区 · ${item?.title || domainLabel}`" ``，
  而 `item.title = reconGroupTitle(row.symbol)` = 裸基金代码 `001982`。
  「处理区」也是技术词。
- 修法：抽屉标题改 `产品名 · 代码`；「处理区」一词全站删除；
  副标题写这一条要做的动作（如「对照流水，决定按哪边记」）。

### 2.4 补充弹窗没有上下文，用户无法对照

- 根因：`SupplementDialog.vue` props 只有 `{ modelValue, target }`，模板 `:9-66`
  **只有一张表单**，零上下文。用户看不到：这条差异是哪种问题、理论/实际/差额是多少、
  属于哪个账本、什么时候发现的、之前有哪些交易。
  唯一能对照的信息是标题里的代码。
- 判定：**内容不够**。现有表单 5 个字段（补充方式 / 操作类型 / 数量 / 价格 / 日期 / 原因）
  全部是「要填什么」，没有一处回答「为什么填这个数」。
- 修法：改右侧抽屉，内容自上而下分三段（见 §3.2）：
  ① 这条差异的来龙去脉 → ② 该产品在该账本的投资轨迹 → ③ 补充表单。
  容器从 `el-dialog` 换 `el-drawer`，宽度 720px / 移动端全屏。

### 2.5 「设定持仓」文案 + 是否与手动录入持仓界面通用（owner 明确要求核实）

**实证结论：不通用，四套表单并存，且直接合并有风险。**

| | 对账中心 `SupplementDialog` | 手动录入持仓 `EaccountManualPanel` | 记一笔 `BuyForm` |
|---|---|---|---|
| 端点 | `POST /api/reconciliation/adjustments/` | `POST /api/importers/holdings/confirm/` | `POST /api/positions/` |
| 落库 | `set` → `positions` + `adjustment_logs` + 差异置 `cleared`；`increment` → `transactions` + `positions` | `positions`（不建流水） | `transactions` + `positions` |
| 份额 | `quantity`「数量」precision=4 | `quantity`「份额」precision=4，`>0` | `shares`「确认份额」，基金 2 位 / 股票 0 位 |
| 价格 | `avg_price`「价格」precision=4 | `price`「成本价」precision=4，`>0` | `price` 净值 + `buyAmount` 金额 + `fee` 手续费 |
| 日期 | **单个** `confirm_date` 变量，按 kind 映射成 `confirm_date` / `snapshot_date` | `snapshot_date`「快照日」必填，默认今天 | `trade_date` 必填 + `confirm_date` 派生 |
| 账本 | **表单里没有**，从 `target.ledger_id` 隐式带入 | `manualLedgerId` 面板级下拉，必选 | `ledger_id` 下拉，必选 |
| 备注 | `reason`「原因」 | **无此字段** | `notes`「备注」 |
| 校验 | 仅 `!quantity || !avg_price` 一句 warning | 5 条逐行校验 + 账户必选 | `el-form :rules` 6 条 + 价格区间 |

`SupplementDialog.vue:143-157` 两个 Tab **打到同一个端点**，靠 `kind` 分派；
后端 `reconciliation_service.py:383-398` 的 `kind='set'` 最终调
`PositionService.upsert_from_holding(..., allow_anchor_rewind=True)`，
语义是 **SET 绝对值覆盖持仓**，不是「补一点」。

**回答 owner 的两个问题：**

1. 「设定持仓」是不是把持仓直接改成最新状态？——**是，覆盖式 SET**，不是增量。
   现有文案会让用户以为在「补充」，实际是把账上份额改成他填的数。
2. 「细节是一样的吗？会不会导致字段录入后更多问题？」——**不一样，且已经有风险**：
   - `set` 分支复用了 `confirm_date` 这个变量名却提交成 `snapshot_date`，label 随 Tab 切换，
     用户按「确认日期」理解填了交易日，落库变成快照日；
   - 表单缺账本显示/选择、缺产品名称与类型、缺金额与手续费、缺 `>0` 与日期必填校验；
   - 没有显示「当前账上是多少」，覆盖前无法自检；
   - `el-input-number :min="0"` 允许 0，`!quantity` 又会把 0 判成没填，边界不一致。

**修法（本期）**：文案改「把持仓改成」，表单上方固定显示
「账上现在是 X 份 → 改成 ___ 份」并二次确认；补齐 `:rules`（份额/成本价 >0、快照日必填）；
字段标签与精度对齐 `EaccountManualPanel` 口径；显示账本名（只读，不允许改，避免写错归属）。
**本期不强行合并两套表单**：合并要动 `/adjustments/` 的载荷与审计语义，属独立后端改造，
另开一张卡，不在本轮 UI 优化里做（见 §9「不做的事」）。

### 2.6 待办队列太长 + 处理完要往回滚

- 根因：`index.vue:101-112` `v-for="item in visibleItems"` **全量渲染，没有分页**；
  `ReconQueueDetail` 挂在队列**下方**（`index.vue:116`），选中一条后页面内容向下生长，
  处理完用户得滚回原位置找下一条。
- 域 B 表格**已有**客户端分页（`DomainBDiscTable.vue:72-82,116-130`，50/100/200），
  但那是处理区内部的表格，跟待办队列是两回事。
- 修法：
  - 队列加 `el-pagination`（`[10, 20, 50]`，默认 10，`layout="total, prev, pager, next, sizes"`），
    范式直接抄 `DomainBDiscTable.vue`；筛选变化回第 1 页。
  - 处理区改**右侧抽屉**，队列 DOM 不位移、滚动位置不变。
  - 处理成功后：保留当前页码与筛选，只重取数据；若当前页因处理变空，自动回上一页。
  - 翻页时把队列头 `scrollIntoView({ block: "start", behavior: "smooth" })`。

### 2.7 `cash` 显示成 `cash`

- 根因：`taxItem()` 用 `name || reconGroupTitle(row.symbol)`；`PendingTaxItem.name`
  取自 `div.position_name`，**这条为空**时回退到 `symbol`（`cash`）。
  `reconGroupTitle()` 不翻译特殊码。
- 后端**早就有词表**：`backend/app/core/asset_types.py:63` `'cash': '现金'`；
  支付宝解析器还写 `'__CASH__'`（`importer/parsers/alipay_fund.py:191-199`）。
- 修法：`reconDisplay.ts` 增 `SPECIAL_SYMBOL_LABELS`（`cash` / `__CASH__` / `_cash` → 「现金」），
  `reconGroupTitle()` 优先命中；`taxItem()` 的 title 与 facts 全部走它。
  补一条单测钉住「不许出现裸 `cash`」。

### 2.8 场内货币基金收益被当成要补红利税（owner 猜测「关联没关联正确」——**猜对了**）

- 后端**已有免税白名单**：`dividend_tax_service.py:103`
  `_NO_DIVIDEND_TAX_ASSET_TYPES = {'bond','money_fund','reverse_repo','cash','bank','bank_wealth'}`，
  `_is_dividend_income()` `:190-212` 第 1 条判据就是它。
- 但 `:341` `asset_type = txn.asset_type or position_types.get(symbol)`，
  而 `_position_asset_types()` `:180-187` **只 SELECT `Position.symbol, Position.asset_type`**。
  关键事实（`core/investment_tiers.py:124-126`）：
  > 「货基持仓的 `asset_type` 是 `'fund'`（`'money_fund'` 只出现在流水上）……
  > 实测真实库：231 行 fund 持仓里有 20 行 `is_money_fund=1`。」

  即：**持仓表里货币基金靠 `positions.is_money_fund` 标记，不靠 `asset_type`**，
  而税扫描没读这个标记 ⇒ 场内货基永远拿到 `fund`，永远不被白名单排除。
  叠加 `:212`「`notes` 为空时默认算分红（宁可提醒，不可漏）」⇒ 误报。
- 次生问题：前缀码（`SH511xxx`）与 positions 里的裸码可能对不上，
  `position_types.get(symbol)` 返回 `None` 时同样不排除。
- 修法（**治本在后端**）：
  1. `_position_asset_types()` 同时 SELECT `is_money_fund`，为 True 的返回 `money_fund`；
  2. 查表键做代码归一化（去市场前缀，复用 `core/venues.py` / `symbol_utils`）；
  3. 前端**不做**特殊过滤，避免在两处各写一套免税判据（口径分叉）。
  4. 补后端单测：货基分红不进待办、普通股票分红仍进待办、前缀码货基也排除。
- ⚠️ 这是本轮唯一需要改后端业务逻辑的一处，见 §7.2 拍板项。

### 2.9 「为什么找我？」没有活人感

- 根因：`ReconTaskBrief.vue:79,89` 三段式第二段 label 硬编码；
  `reconTasks.ts` 里 `why` 字段注释也写成「为什么找我 / 影响什么」。
- 修法：三段改成「这是什么 / **放着不管会怎样** / 处理后会怎样」。
  语义闭环：定义 → 不做的后果 → 做的后果，且不与第三段重复。
  同步重写 `reconTasks.ts` 的 `what/why/next`：去掉「资产报表只能取其中一个数」这类
  系统自述，改成用户能感知的后果（例如「账户里的份额会一直和券商对不上，
  年底算收益时少算/多算这笔」）。

### 2.10 「就地补充」窗口名奇怪

- 根因：`SupplementDialog.vue:4` 标题；`:138` 还有 `ElMessage.warning("请填写数量与价格")`
  **违反 `design.md:1083` 禁「请」**。
- 修法：抽屉标题 `补录这笔 · <产品名>`；主按钮「补上这笔」；
  校验文案改「份额与成本价都要填」；「原因」→「备注（选填）」。

### 2.11 要看到投资轨迹 / 买卖记录 + 账本信息

owner 指出的两个既有入口都成立，且**已有可复用资产**：

- `frontend/src/components/TransactionTable/index.vue`（#2104 统一组件，
  产品详情页 / 账本 Tab / 持仓抽屉三处共用）：纯 props 传入 `rows`，
  `mode="compact"`、`show-account`、`show-fee`、`price-label` / `quantity-label` 可覆写；
  组件无内建空态，容器自己写。
- 取数：`getLedgerTransactions(ledgerId, { page, per_page, search })`
  （`api/ledger.ts:508-515`）一次同时满足「按账本 + 按标的」；
  `getTransactions({ symbol, per_page })` 按标的查；`getLedgers()`（`api/ledger.ts:125`）拿账本名。
- 修法：抽屉第 ② 段固定展示
  「账本：<名称> · 该产品最近的交易」+ `TransactionTable :rows mode="compact" show-account show-fee`
  + 空态「这个账本里还没有该产品的交易流水，先去交易导入补流水」+ 跳产品详情页/账本详情页的入口。
  **`ledger_id` 为空时**（域 G 这类孤儿流水）明确显示「未归账本」，并给「前往账本页归置」入口，
  不能悄悄留白——owner 说的「没有账本，用户还是没办法做确认」正是这里。

---

## 3. 信息架构调整

### 3.1 队列 → 抽屉，不再「下方展开」

```
┌ 页头 PageHeaderBar ─────────────────────────────────────┐
├ 三张任务卡 + 三段式说明 ────────────────────────────────┤
├ 状态筛选 / 关键词 / 批次 / 批量栏 ──────────────────────┤
├ 待办队列（分页 10 条/页，页码条吸底）──────────────────┤   ← 不位移
│  · 卡片 1 … 卡片 10                                     │
│  [ 1 2 3 … 24 ]  共 236 条                              │
└─────────────────────────────────────────────────────────┘
                                    ╔ 右侧抽屉 720px ═════════════╗
                                    ║ ① 来龙去脉（产品/账本/差额）║
                                    ║ ② 投资轨迹（TransactionTable）║
                                    ║ ③ 处理动作（表单/既有面板）  ║
                                    ╚═════════════════════════════╝
```

理由：抽屉不占队列的文档流，处理完关掉即回到原位置；同时 720px 宽度才放得下
「上下文 + 流水表 + 表单」三段，520px 弹窗塞不下（这是截图 2 弹窗内容不够的物理原因）。

### 3.2 抽屉三段式（每段的判据）

| 段 | 内容 | 判据 |
|---|---|---|
| ① 来龙去脉 | 产品名 + 代码、账本名、问题类型（人话）、按流水算 / 账上记的 / 差多少、发现时间、这笔要我做什么 | 用户不用回到队列就能复述「我在处理什么」 |
| ② 投资轨迹 | 该账本该标的的交易流水（时间 / 类型 / 价格 / 份额 / 金额 / 账户）、账本名、空态与补流水入口 | 用户能对照着判断该补哪一笔 |
| ③ 处理动作 | 复用既有域面板与写路径（B/C 表格、E 补税、F/G 回填…），补充表单内嵌在抽屉里 | **写路径零重写**（上一轮实机 23 项用例不回归） |

---

## 4. 文案对照表（一次改齐，不留半截）

| 位置 | 现在 | 改成 |
|---|---|---|
| 三段式 ② | 为什么找我 | 放着不管会怎样 |
| 处理区标题 | 处理区 · 001982 | 华夏××混合 · 001982 |
| 弹窗标题 | 就地补充 · SH688223 | 补录这笔 · <产品名> |
| 补充方式 B | 设定持仓 | 把持仓改成 |
| 补充方式 A | 补一笔交易 | 补一笔交易（保留） |
| 字段 | 数量 / 价格 | 份额 / 成本价 |
| 字段 | 确认日期（set 时切快照日期） | 确认日期 / 生效日期（各自独立字段，不再共用一个变量） |
| 字段 | 原因 | 备注 |
| 校验 | 请填写数量与价格 | 份额还没填 / 份额要大于 0 / 单价还没填 / 单价要大于 0 |
| 按钮 | 确认补充 / 补一笔 | 补上这笔 / 改成这个持仓 |
| 表格列 | 代码 / 类型 / 理论 / 实际 / 差异 | 产品 / 问题 / 按流水算 / 账上记的 / 差多少 |
| 表格值 | 数量 / 成本 / 资金 / 孤儿 | 份额对不上 / 成本对不上 / 资金对不上 / 有持仓、缺流水 |
| 特殊码 | `cash` / `__CASH__` | 现金 |

---

## 5. 组件拆分与文件清单

**实际落地**（初版设想与现实的差异见 §11.2；每个 `.vue` ≤ 400 行，过 `check_vue_size.mjs`）：

| 文件 | 职责 |
|---|---|
| `components/ReconQueueDetail.vue` | **就地改成** `el-drawer` 壳（未另建 `ReconDetailDrawer`）：三段式布局、720px / 窄屏 100%、加载只加遮罩不卸载内容 |
| `components/ReconContextPanel.vue` | ① 来龙去脉：产品名 + 代码、账本名、差额对照、问题类型人话 |
| `components/ReconInvestmentTrail.vue` | ② 投资轨迹：有账本走 `getLedgerTransactions(ledgerId, {search})`，无账本走 `getTransactions({symbol})`；复用 `TransactionTable`，含空态与补流水入口 |
| `components/ReconQueuePagination.vue` | 队列分页条（`[10,20,50]`、默认 10、翻页 emit `changed` 回队列头） |
| `components/SupplementContext.vue` | 补录弹窗「补的是哪一条」；**为 400 行门禁从 `SupplementDialog.vue` 拆出** |
| `composables/useReconLedger.ts` | 模块级账本名缓存（一次 `getLedgers(true)` 两处消费；失败降级「账本编号 X / 未归账本」） |
| `utils/reconLabels.ts` | 对账专用术语表（差异类型 / 特殊码 / 列名 / 口径说明），与全站 `DISCREPANCY_TYPE_LABELS` 解耦 |

改造：`index.vue`（分页接线 + `:open`）、`SupplementDialog.vue`（上下文 / 两档解释 / `el-form :rules` / 二次确认）、
`DomainBDiscTable.vue`（产品列 + 列名术语 + 口径说明行）、`reconDisplay.ts`（特殊码 / 名称标题）、
`reconQueue.ts`（名称 / 术语 / `cash` / **数组守卫**）、`useReconQueue.ts`（客户端分页）、
`useWorkbenchActions.ts`（`detailOpen`、不再滚到处理区）、`reconTasks.ts` + `ReconTaskBrief.vue`（三段式文案）、
`api/reconciliation.ts`（`display_name` 类型）。
后端：`views.py`（批量 `display_name`）、`dividend_tax_service.py`（`is_money_fund` + 前缀码归一化）。

---

## 6. 数据口径与兼容性

- **名称解析优先级**：后端 `display_name`（若批准）> 前端 `resolveProduct` / `searchAssets`
  批量查（缓存、并发 ≤6、失败降级「代码 + 名称待补」）> 裸代码。
  绝不因为查名称失败就让整条待办消失。
- **特殊码**：`cash` / `__CASH__` / `_cash` → 「现金」，并在队列里标注
  「这不是一只产品，是账户里的现金余额」，避免用户以为要去找一只叫 cash 的基金。
- **货币基金**：前端不做免税判断；修复落在后端 `_position_asset_types()`。
- **e2e 契约**：`.workbench-head` / `.workbench-head__title` / `.workbench-banner` /
  `?domain=A…G` 入站 / 切视图不重挂载 / hash 不写 `domain=` 全部保留。
  抽屉默认 `append-to-body`；`?domain=F/G` 入站会把 `activeDomain` 置上，**抽屉自动展开**，
  故 `.df-summary` / `.olg-summary` / `.dr-panel` 的 `toBeVisible` 语义不变。
  实机复核：既有 4 份 spec 共 23 条用例**一行未改全绿**（§11.3），
  初版「这两处要同步改」的担心不成立。

---

## 7. owner 拍板的决策（已定，记录在案）

### 7.1 是否允许两处后端小改（与上一版「后端零改动」约束冲突）

| 改动 | 内容 | 不做的代价 |
|---|---|---|
| ① `views.py:list_discrepancies` 出参加 `display_name` | 批量查 `positions` / `funds` / `securities`（可复用 `watchlist_display.resolve_display_name` 的批量链），**不新增端点、不改表** | 只能前端逐码查，几百条差异要发几百个请求；或降级成「代码 + 名称待补」，owner 提的「用户怎么知道改的是哪个产品」**没真正解决** |
| ② `dividend_tax_service._position_asset_types` 读 `is_money_fund` + 代码归一化 | 一个函数，约 10 行；**不改端点、不改表** | 货币基金收益继续误报要补税，前端只能靠特判屏蔽，形成两套免税口径 |

建议：**都允许**。两处都不新增端点、不动表结构，风险远小于「前端绕过去」。

### 7.2 容器形态：右侧抽屉 vs 保持下方展开

建议 **右侧抽屉 + 队列分页**（§3.1）。保持下方展开的话，
即便加了分页，「处理完往回滚」的问题依然存在，只是滚得少一点。

### 7.3 「把持仓改成」是否本期与手动录入持仓界面合并

建议 **本期不合并**（§2.5）：只对齐字段标签/精度/校验并补上下文，
两套端点与审计语义的合并另开卡。强行合并会动 `/adjustments/` 载荷，
把一次 UI 优化变成后端改造，且会牵动上一轮已跑通的写路径 e2e。

---

## 8. 分阶段实施与验证判据

| 阶段 | 内容 | 判据 |
|---|---|---|
| P0 数据口径 | 后端 ① ②（若批准）、`reconLabels.ts`、特殊码翻译、`display_name` 接入 | 后端单测：货基分红不进待办 / 普通分红仍进 / 前缀码货基排除；前端单测：界面零裸 `cash`、零 「孤儿」、零英文枚举 |
| P1 抽屉与上下文 | `ReconDetailDrawer` + `ReconContextPanel` + `ReconInvestmentTrail`，替换下方处理区 | 实机：点开一条 → 抽屉内有产品名/代码/账本/差额/交易流水；关闭后队列滚动位置不变；域 F/G 写路径 10 条用例全绿 |
| P2 分页与文案 | 队列分页、三段式文案、表格列名与术语、补充表单字段与校验 | 实机：236 条待办只渲染 10 条；翻页后队列头可见；处理完页码与筛选保留；`design.md` 禁「请」零命中 |
| 收尾 | 同步 e2e spec、`vue-tsc`、全量 vitest、eslint/stylelint、四个守卫、`check_vue_size --mode fail`、Playwright 实机 | 全绿；新增 `.vue` 无 `[NEW]` 红 |

**反向验证**（防「恰好绿」）：把 `SPECIAL_SYMBOL_LABELS` 与差异术语表删掉后，
对应单测必须转红；把后端 `is_money_fund` 分支还原后，货基用例必须转红。

---

## 9. 不做的事（边界）

- 不改 `/adjustments/` 端点与载荷语义，不合并四套持仓表单（另开卡）。
- 不新增后端端点、不改表结构。
- 不把 A~G 域重新变回 tab，不新增页内左侧导航。
- 不重写任何写路径（归因 / 忽略 / 补税 / 回填 / 撤销全部沿用既有实现）。
- 不做服务端分页：队列是前端由七个域快照合成的一条列表，服务端分页要重排七个接口，
  本期用客户端分页即可（几百条量级无性能问题）。

## 10. 回滚

- 代码全在独立 worktree 分支，主仓 `dev` 保持只读与 `git pull --ff-only` 可用。
- 后端两处改动各自独立、无迁移、无数据写入，回滚即还原函数体。
- 抽屉组件为新增文件，回滚只需把 `index.vue` 的处理区引用切回 `ReconQueueDetail`
  的内联块（上一版实现仍在 git 历史 `1971c618d0` 中）。

---

## 11. 实施结果（2026-11-07，本节为准）

### 11.1 落地范围

| 类别 | 交付 |
|---|---|
| A 缺数据 | 后端差异出参批量补 `display_name`（`Position.name` > `Security.name` > `Fund.name`，前缀码剥掉回查裸码）；`is_money_fund` 进免税判据 + 代码归一化；前端 `cash` / `_cash` / `__CASH__` → 「现金」 |
| B 缺上下文 | 右侧抽屉（720px）三段：来龙去脉（产品 + 代码 / 账本 / 问题 / 三个数 / 发现时间）→ 投资轨迹（复用 `TransactionTable`）→ 处理动作（既有域面板零重写）；补录弹窗也带同一份「补的是哪一条」 |
| C 交互约束 | 队列客户端分页（默认 10）、筛选变化回第 1 页、处理完当前页空了自动退到最后一页、翻页把队列头带回视野；抽屉不占文档流，处理完不需要往回滚 |
| 文案 | 「为什么找我」→「放着不管会怎样」；「就地补充」→「补录这笔 · <产品名>」；「设定持仓」→「把持仓改成」；表格列「产品 / 问题 / 按流水算 / 账上记的 / 差多少」+ 一行口径说明；「孤儿」零露出 |

### 11.2 与初版设想的偏差（如实记录）

1. **没有新建 `ReconDetailDrawer.vue`**：直接把 `ReconQueueDetail.vue` 就地改成 `el-drawer`。
   七个域面板的 `v-if/v-else-if` 链与写路径 emit 一行未动，回归面更小。
2. **没有 `useReconNames.ts`**：批量名称解析放在后端一次 `IN` 查询完成，前端只消费
   `display_name`，不需要缓存 / 并发上限 / 逐码请求。
3. **补录弹窗仍是 `el-dialog`，不是抽屉内的一段**：抽屉负责「看清楚」，弹窗负责「改数据」。
   弹窗内嵌 `SupplementContext` 复述上下文，避免用户在两个容器之间丢信息。
4. **新增 `SupplementContext.vue`**：`SupplementDialog.vue` 一次写到 486 行，
   `check_vue_size.mjs --mode fail` 判 `[NEW]` 红；按项目纪律拆子组件而非改基线，
   落在 392 / 134 行，门禁通过。
5. **口径说明只放一处**：`DISC_CALIBER_HINT` 最终放在 `DomainBDiscTable` 表头上方
   （紧挨被解释的三个数），抽屉里不再重复一遍。
6. **补录表单没有改成「快照日必填」**：后端 `apply_decision` 对 `set` 有
   `data.setdefault('snapshot_date', date.today())` 兜底；前端默认填本地日历日，
   用户可改，不强制。真正必须卡的是 `ledger_id` 非空、份额 > 0、单价 > 0（见 11.5）。

### 11.3 验证结果

| 项 | 结果 |
|---|---|
| 后端 pytest（`test_dividend_tax_service.py` / `test_reconciliation.py`） | 76 passed |
| 后端反向验证：去掉 `is_money_fund` 分支 | 3 条货基参数化用例转红，恢复后转绿 |
| 全量 `vitest run` | **2323 passed / 170 files**；对账纯函数定向复跑 31 passed / 2 files |
| `cash` 反向验证（删 `SPECIAL_SYMBOL_LABELS.cash`） | 对应用例转红，恢复后转绿 |
| 新增 `reconQueue.spec.ts`「畸形 200」用例 | `ghostIgnored` 写成对象时不抛错，降级成空数组 |
| `vue-tsc --noEmit --skipLibCheck` | 0 error |
| ESLint / Stylelint（20 个改动前端文件） | 双双全绿 |
| `ruff check` + `ruff format --check`（4 个改动后端文件） | 双双全绿 |
| `guard_segmented.py` / `guard_soft_banner.py` / `guard_breakpoints.py` / `check_css_vars.mjs` / `guard_a11y_interaction.py` / `guard_input_focus.py` / `guard_ts_any.mjs` | 全绿 |
| `check_vue_size.mjs --mode fail --baseline` | 通过，527 个 `.vue` 无 `[NEW]` 红（`SupplementDialog.vue` 396 行 / `SupplementContext.vue` 134 行） |
| Playwright 实机 6 份 spec | **28 passed**（既有 23 条**一行未改**全绿 + 新增 5 条） |

### 11.4 实机抓到的两个坑（有长期价值）

1. **「一直转圈」不等于请求没回来**。新增 e2e 桩漏了
   `/api/reconciliation/ghost-duplicates/ignored/` 的窄桩，宽桩把
   `{groups, ignored_count}` 对象当成数组写进 `ghostIgnored`，
   `buildReconQueue` 的 `for...of` 在 computed 里抛错 → Vue 只报 warn、把 DOM
   **冻在末次成功渲染（加载态）**，既不白屏也不崩，看起来像「接口卡住」。
   `page.on('pageerror')` 抓到 `source.ghostIgnored is not iterable` 才定位。
   两处都修：桩补窄规则；`buildReconQueue` 加 `rowsOf()` 数组守卫并补单测。
   新 spec 每条用例 `afterEach` 断言零未捕获异常，防止这类假绿回潮。
2. **本机 vite 二次启动会被安全删除钩子挡住**：`loadCachedDepOptimizationMetadata`
   要 `fs.rm(node_modules/.vite/deps)`，沙箱 shim 的 trash 操作报
   `Some operations were aborted`，dev server 起不来。仅对测试进程设
   `CODEBUDDY_SAFE_DELETE_ENABLED=0` 即可，不动仓库配置。

### 11.5 回答 owner 对「设定持仓」的两个问题（实证）

- **是不是直接把持仓改成最新状态？** 是。`kind='set'` 走
  `PositionService.upsert_from_holding(..., allow_anchor_rewind=True)`，
  写 `positions` 锚点 + `adjustment_logs`，把差异置 `cleared`，**不新增交易流水**。
- **和手动录入持仓界面通用吗？录进去会不会有更多问题？** 不通用（`§2.5` 四套表单对照），
  且原先确实有风险。本期在不合并端点的前提下修掉：
  - `confirm_date` / `snapshot_date` 拆成两个独立字段，不再一个变量两种语义；
  - `ledger_id` 为空时**直接挡住** `set`（后端 `resolve_snapshot_intent` 会 400），
    并提示先归账本或改用「补一笔交易」；`increment` 则给「流水也会没有账本」的告知；
  - `el-form :rules` 卡住份额 > 0、单价 > 0（后端同口径），`el-input-number` 不再靠
    `!value` 把 0 判成「没填」；
  - 覆盖前显示「账上现在 X 份」，提交前 `ElMessageBox.confirm` 二次确认写清
    「不新增买卖记录、原有快照会被覆盖」；
  - 透传 `display_name` 到 `name`，避免新建持仓行只落一个裸代码；
  - 校验文案去「请」（`design.md:1083`）。
  字段标签与 4 位精度对齐手动录入持仓；**端点、审计语义、差异状态变更仍各归各的**，
  合并另开卡。

### 11.6 遗留（明确不做）

- 四套持仓表单的端点合并（需动 `/adjustments/` 载荷与审计语义）。
- 服务端分页：队列由七个域快照在前端合成，本期客户端分页够用。
- 后端 `apply_decision` 的 `set` 兜底仍用 `date.today()`（UTC 16:00–24:00 与上海业务日
  可能差一天）；前端已默认传本地日历日规避，后端统一 `today_shanghai()` 另开卡。
- `el-pagination` 的 `small` prop 在 Element Plus 3.0 将废弃，全站一起换 `size` 时处理。
