# 账户详情页「持仓集中度 / 行业分布」占位卡处置（#2739）

> 状态：**已实现**（2026-10-29 owner 裁定后落地，PR #2745，分支 `feat/2739-ledger-depth-analysis`）。相关卡：#2739（占位卡处置）、#2595（持仓分析聚合页）、#2617（持仓结构 / 穿透）。
> 证据附录：`docs/spec/account-detail-depth-analysis-eval.md`（四页面分析块对照矩阵 + 独立冗余评估）。
> 前置事实：`docs/working-notes/ledger-detail-info-redesign-plan-2026-08-27.md`（2026-08-27 账户详情页重构计划，本文是其 P1 段落的收尾）。

---

## 0. 落地摘要（owner 裁定结果）

| # | 决策点 | owner 裁定 | 落地形态 |
|---|---|---|---|
| 1 | 方案 B′ / A / C | **B**（即 B′） | 账户详情页**就地内嵌**「持仓结构」+「持仓穿透」两块；不改成跳转入口卡、不直接删除、不照搬聚合页整页 |
| 2 | 是否同时补页内导航 | **补**（本批做） | 实测账户详情页**原本没有**页内导航 ⇒ 从零接入两级导航（`PageNav` 胶囊 / `PageToc` 右栏），7 个纵向分区 |
| 3 | 聚合页是否加 `?scope=ledger&id=` 深链 | **不做** | 聚合页口径与端点一字未动；仅按 §3.3 更正其分工表的歧义措辞 |

**实现要点**：

- 新增 `frontend/src/views/asset/ledgers/components/LedgerDepthAnalysis.vue`（54 行）：只做编排与传参，**零计算**；两块面板的锚点经 attribute fallthrough 直接落在面板根上（`nav-structure` / `nav-penetration`）。
- `LedgerDetailOverview.vue`：占位卡整块删除，改为一行 `<LedgerDepthAnalysis v-if="showDepthAnalysis" :ledger-id="p.ledgerIdNum" />`；另给「账本概览 / 类现金 / 收益日历 / 收益归因」四块补上锚点。
- `detail.vue`：接入 `usePageNav` + `PageNav` + `PageToc`，登记 7 条 `NAV_LABELS`；`CashFlowPanel` 补 `nav-cash-flow` 锚点。
- **口径纪律（本卡唯一的正确性要害）**：账户 id 改由 `useLedgerDetail` 统一产出 `ledgerIdNum`（**只认有限数字**）。原先各处的 `Number(p.ledgerId)` 在「未归置持仓」伪账户上算出 **NaN**，NaN 被 axios 序列化成 `ledger_id=NaN`，后端 `request.args.get('ledger_id', type=int)` 解析失败一律回 None（＝不传＝**家庭级**）——于是页面会拿全家庭的数据当本页展示，而面板的口径标签还写着「账户」。数据与标签同时错，比单错更坏。
- 未归置持仓伪账户（没有数字账户 id）**整块不展示**深度分析（与同页资金流动一致）。
- 新增回归网 `frontend/src/views/asset/ledgers/__tests__/ledgerDepthAnalysisGuard.spec.ts`（6 条）：占位卡不许回来 / 深度分析真接线 / 口径走有限数字 / 未归置页不展示 / 类现金锚点随块消失 / 锚点与标签一一对应。

**后续口径变更（PR #2746）**：owner 在验收时提出「账户类型本就确定，持仓结构里的股基双视角切换是多余的」。
已按 `docs/spec/position-structure-view-by-ledger-type.md` 收敛：账户级下视角由
`ledgers.ledger_type` 决定（证券账户只看股票、基金/银行账户只看基金），**不渲染切换控件**；
组合/家庭级保留切换。ETF 归权益侧、货基走类现金**仅账户级生效**，组合/家庭级口径零改动。


---

## 1. 结论先行

**这两项能力早已上线，不需要再开发一次。** 账户详情页那块写着「规划中，敬请期待」的占位卡，在把一个**已存在**的功能说成不存在——这是用户可见的失实信息。

本题不是「实现集中度与行业分布」，而是**「处置一块说谎的占位卡」**。

**独立评估结论（详见附录）**：聚合页与账户详情页**并未产生功能冗余**；聚合页是「可切换口径」的分析入口，详情页是「深读 + 操作」的分析入口，同源组件服务不同意图。真正该做的是**只补详情页独缺的两块**（持仓结构 / 持仓穿透），**不搬聚合页整页**——搬整页才是制造冗余。

**推荐方案：方案 B′（就地内嵌缺失的两块，沿用组合详情页的内嵌分区模式）**。

**owner 已裁定按 B′ 落地，并裁定本批补页内导航、不给聚合页加深链（见 §0）。**

---

## 2. 现状取证（`origin/dev` 已核对，2026-10-29）

### 2.1 占位卡本体

| 事实 | 位置 |
|---|---|
| 占位卡（唯一残留） | `frontend/src/views/asset/ledgers/components/LedgerDetailOverview.vue:276-288`（**已于本 PR 删除**） |
| 文案 | 「持仓集中度 / 行业分布规划中，敬请期待」 |
| 注释 | 「账户深度分析其余项（持仓集中度 / 行业分布）仍规划中，详见内部工作记录 ledger-detail-info-redesign-plan-2026-08-27」 |
| 来源 | 2026-08-27 计划：移除「资产配置环形图 + 盈亏走势」双列卡后，**原位置替换为占位卡**「避免页面突兀留白」 |

### 2.2 声称「规划中」的能力，实际已上线

| 能力 | 实现 | 组件 props |
|---|---|---|
| 持仓结构 / 集中度（资产类别占比 / 股基分列 Top N / 前 5 集中度） | `frontend/src/components/PositionStructurePanel/index.vue`（#2617） | `ledgerId?: number`（:133-136） |
| 持仓穿透 / 行业分布（证监会门类 / GICS 双口径） | `frontend/src/components/PenetrationPanel/index.vue`（#870 + #2595） | `ledgerId?: number`（:161-166） |

**两个组件都原生支持 `ledgerId`**，后端端点现成、口径统一，**前端组件零改动即可按账户口径取数**：

- `GET /api/summary/position-structure/`（`frontend/src/api/summary.ts:780`），账户口径经 `scope.ledger_id` 传入（`PositionStructurePanel/index.vue:179`）
- `GET /api/summary/penetration/`（`frontend/src/api/summary.ts:717`）

### 2.3 组合详情页已经这么做了（决定性证据）

`frontend/src/views/asset/portfolio/detail.vue:243-255` 的页内导航字典：

```ts
const NAV_LABELS: Record<string, string> = {
  "nav-return": "组合收益",
  "nav-money-fund": "货币基金收益",
  "nav-cash-flow": "资金流动",
  "nav-attribution": "收益归因",
  "nav-structure": "持仓结构",      // ← 集中度在这里
  "nav-penetration": "持仓穿透",    // ← 行业分布在这里
  "nav-style": "组合风格",
  "nav-holdings": "持仓明细",
  ...
};
```

**「持仓结构」与「持仓穿透」是组合详情页的正式一级分区**（与「收益归因」「持仓明细」同级），不是附注。

### 2.4 账户详情页已有分析块，且独缺这两块

`LedgerDetailOverview.vue` 已内嵌：`PnlCalendar`（:269）、`PnlAttribution`（:274）、`AssetAllocationDonut`（:250）、`LedgerCashLikeCard`（:263）；`detail.vue` 另有 `CashFlowPanel`（:64）。

**⇒ 详情页的分析块密度本来就不低于组合详情页，独缺「持仓结构 / 持仓穿透」，且缺口被假占位卡占据。**

### 2.5 约束条件

| 约束 | 事实 | 影响 |
|---|---|---|
| 页面规模门禁 | `scripts/check_vue_size.mjs` 阈值 400 行、基线 `scripts/vue-size-baseline.json` **只减不增** | `LedgerDetailOverview.vue` 现 369 行；**直接内嵌会顶破** ⇒ 必须抽子组件 |
| 聚合页不支持深链 | `position-analysis/index.vue` 不读 `route.query`，`scopeKind` 恒从 `ref("family")` 起 | 「带账户跳过去」会落在全家庭档 ⇒ 入口卡方案文案不能暗示已预选 |
| 持仓明细表的 `allocation` | `LedgerDetailHoldingsPane.vue:144-147` 是**五笔钱**（配置目标） | 与「持仓占比」无关，不可复用充数 |
| 口径多档 | 集中度有「前 5 占组合 / 组内前 5」，穿透有「证监会门类 / GICS」 | 必须沿用组件自带口径切换，不隐藏、不二次包装 |

---

## 3. 独立评估：聚合页与详情页是否已冗余

完整论证见 `docs/spec/account-detail-depth-analysis-eval.md`，此处给结论与依据。

### 3.1 四页面分析块对照矩阵

| 分析块 | 持仓分析 | 账户详情页 | 组合详情页 |
|---|:---:|:---:|:---:|
| 超额四卡 | ✔ | ✔ | ✔ |
| 收益日历 `PnlCalendar` | ✔ | ✔ | ✘（后端无组合口径） |
| 收益归因 `PnlAttribution` | ✔ | ✔ | ✔ |
| 资金流动 `CashFlowPanel` | ✘ | ✔ | ✔ |
| **持仓结构 / 集中度** | ✔ | **✘** | **✔** |
| **持仓穿透 / 行业分布** | ✔ | **✘** | **✔** |
| 组合风格 | ✘ | — | ✔ |

### 3.2 结论一：**未产生功能冗余**

三个事实交叉验证：

1. **同源组件 ≠ 功能冗余**。冗余的判据是「同一页面上同一内容出现两次」或「两个入口给出**矛盾**口径」，不是「两个页面用了同一个组件」。聚合页（**切换**口径）与详情页（**深读 + 操作**）服务不同意图，组件同源但口径一致、不会打架。
2. **组合档与组合详情页 100% 重叠**，且组合详情页**明显不是无意义的重复页**（11 个分区 + TOC rail + 锚点导航，注释原文「纵向区块 9 个、明显超一屏」）。⇒ 重叠本身不是问题。
3. **账户详情页的分析块密度本来就不低于组合详情页**（日历 / 归因 / 现金流 / 超额四卡都在），**独缺**这两块。缺位是 2026-08-27 移除环形图后用占位卡填空的**历史遗留**，不是「详情页不该有分析」的设计决定。

### 3.3 结论二：原分工表的措辞有歧义（我原文档的判断错误）

`position-analysis/index.vue:7-12` 写着「组合档 = 详情页核心块的聚合视图」「账户档同理」。**按此字面理解，组合详情页就成了「无意义的重复页」——显然不是。** 真实关系是「组合详情页 = 该组合的分析视图；聚合页 = 可切换口径的分析视图」，是**同源内容的两个入口**，不是子集关系。

⇒ 原文档 §2.3 把它当「详情页不该有分析块」的依据是**错的**，已在本节更正。

### 3.4 结论三：真正该避免的是「搬整页」

若在账户详情页镜像聚合页全部内容（口径切换器 + 四卡 + 日历 + 归因 + 结构 + 穿透），那才是**制造冗余**——详情页已有日历、归因、超额四卡。

**账户详情页应该且只需要补它缺的那两块**，走组合详情页的**内嵌分区模式**，不搬口径切换器、不搬已有块。

---

## 4. 方案对比

### 方案 A · 换成入口卡（跳转持仓分析页）

删除占位卡，换成一行说明 + 「去持仓分析」按钮，跳 `/asset/position-analysis`。

- ✅ 成本最低，页面不涨行数。
- ✅ 不引入重叠。
- ❌ **跳转落点不对**：聚合页不读 query ⇒ 跳过去落在「全家庭」档，**不是用户当前账户**。文案若暗示已预选就是新的失实。
- ❌ 用户要看「这个账户」的集中度，得再点一次「单账户」档、再选一次账户——**多两步**。
- ⚠️ 修成「带着当前账户跳过去」须先给聚合页加 query 读取（`?scope=ledger&id=<ledgerId>`）——**扩了聚合页范围**，而 #2739 明确「不动聚合页的口径与端点」。
- ❌ 页面长度不解决（详情页 9~10 块，加 2 块与组合详情页同量级，**不构成否决理由**）。

### 方案 B′ · 就地内嵌缺失的两块（推荐）

占位卡原地替换为 `PositionStructurePanel` + `PenetrationPanel`，传 `ledgerId`；**只补这两块，不搬聚合页其他块**。

- ✅ **零新计算**：组件与后端端点已存在，账户口径链路已通。
- ✅ **落点即当前账户**：不用跳转、不用二次选择。
- ✅ **只补缺口**：与组合详情页的 `nav-structure` / `nav-penetration` 完全同构，形态在全站一致。
- ✅ 与 §3.2 结论一致：详情页与聚合页不产生矛盾口径。
- ✅ 消掉整条误导链：占位卡、注释、旧文档 P1 段落一起收口。
- ⚠️ **行数压力**：`LedgerDetailOverview.vue` 369 行 ⇒ 用**新增子组件**承载，Overview 净减（详见 §5.1）。

### 方案 C · 直接删除

只删占位卡，不做替代。

- ✅ 最省事。
- ❌ **留白**：2026-08-27 计划的原始动机正是「避免页面突兀留白」。删掉则页尾出现断层。
- ❌ 用户在账户详情页**得不到**任何指引，能力依然只能靠侧边栏发现——治标不治本。

### 方案 D · 把聚合页整页搬进详情页（**明确否决**）

- ❌ **这才是真正制造冗余**：详情页已有超额四卡 / 日历 / 归因 / 现金流，搬整页会与之重复。
- 记录在此是为了把「冗余」这个词说清楚：**冗余不在「详情页 vs 聚合页」，而在「照搬整页」。**

---

## 5. 推荐：方案 B′

**推荐方案 B′：就地内嵌「持仓结构」+「持仓穿透」两块，沿用组合详情页的内嵌分区模式。**

### 5.1 实现形态（已落地）

**新增子组件** `frontend/src/views/asset/ledgers/components/LedgerDepthAnalysis.vue`：

```
props: { ledgerId?: number }
模板（两个面板根节点都是单根元素 ⇒ 锚点 id 经 attribute fallthrough 直接落下）：
  <PositionStructurePanel id="nav-structure" class="mb-6" :ledger-id="ledgerId" />
  <PenetrationPanel        id="nav-penetration" class="mb-6" :ledger-id="ledgerId" />
```

组件内**不含任何计算**，只做编排与传参。

**改造 `LedgerDetailOverview.vue`**：

- 删除 `:276-288` 的占位卡 `<CardBlock>` 整块；
- 删除「仍规划中 / 详见 2026-08-27 计划」的注释；
- 改为一行：`<LedgerDepthAnalysis v-if="showDepthAnalysis" :ledger-id="p.ledgerIdNum" />`；
- 另给四块补锚点：「账本概览」`<SectionHeader id="nav-overview">`、「类现金」`<LedgerCashLikeCard anchor-id="nav-cash-like">`、「收益日历」`<PnlCalendar id="nav-calendar">`、「收益归因」`<div id="nav-attribution">` 包一层（`PnlAttribution` 是多根组件，吃不到父级 fallthrough）。

> ⚠️ **行数不是「净减」，是「净增但仍远低于阈值」**：原判据「删约 13 行、增约 3 行 ⇒ 净减」在只做替换时成立；补页内导航锚点后净增。实测 `LedgerDetailOverview.vue` 由 369 行 → **385 行**，仍在 400 阈值内（基线 `files: {}`，任何 .vue 超 400 即判红）。数字账户 id 的推导因此**没有留在本页**，而是收进 `useLedgerDetail`（`ledgerIdNum`）——本页只留一个 `showDepthAnalysis` 判据。

**锚点挂哪：统一挂在「区块标题行的顶边」**。落点纪律：`SectionHeader` 是单根元素 ⇒ `id` 经 fallthrough 落下；多根组件（`PnlAttribution`、`LedgerCashLikeCard`）⇒ 调用方包 div 或走 `anchor-id` prop（沿用产品详情页 `ProductHoldingsSections` 的 `anchorId` 既有约定）。**锚点必须挂在块内**：块整块不渲染时锚点随之消失，导航项被 `usePageNav` 的 DOM 存在性过滤收走，不留死链（类现金为 0 的普通基金账户占绝大多数，硬挂准就会留下一个点不动的导航项）。


### 5.2 页内导航（owner 裁定：本批补，已落地）

**原建议是「若账户详情页已有页内导航组件 → 只加两个锚点；若无 → 本次不做，另开卡」——owner 裁定「补导航」，且实测账户详情页**根本没有**页内导航**（`detail.vue` 无 `PageNav` / `PageToc` / `usePageNav`）。故本批实为**从零接入**两级导航，而不是加两个锚点。

落地形态与组合详情页同型（`views/asset/portfolio/detail.vue`）：

- `usePageNav(pageMain, { labels: NAV_LABELS, rescanOn: () => ledgerId.value })` —— state / scroll-spy / 跳转动画全在共享 composable 里，页面只提供「锚点 → 标签」映射；
- `PageNav`（`<xl` 顶部锚点胶囊）放正文之前、`PageToc`（`xl+` 右侧 160px sticky 目录 rail）放 `__body` 内 `__main` 之后；`__body` = `display:flex; gap: var(--space-5)`，`__main` = `flex:1; min-width:0`；
- 7 条 `NAV_LABELS`（标签与各区块 `SectionHeader` 标题**逐字一致**）：

  | 锚点 | 标签 | 所在区块 |
  |---|---|---|
  | `nav-overview` | 账本概览 | `LedgerDetailOverview` |
  | `nav-cash-like` | 类现金 | `LedgerCashLikeCard`（`anchor-id` prop，块不渲染即消失） |
  | `nav-calendar` | 收益日历 | `PnlCalendar` |
  | `nav-attribution` | 收益归因 | `PnlAttribution`（多根 ⇒ 调用方包 div） |
  | `nav-structure` | 持仓结构 | `LedgerDepthAnalysis` → `PositionStructurePanel` |
  | `nav-penetration` | 持仓穿透 | `LedgerDepthAnalysis` → `PenetrationPanel` |
  | `nav-cash-flow` | 资金流动 | `detail.vue` → `CashFlowPanel`（未归置页整块不渲染） |

- **持仓明细 / 交易记录不进目录**：它们是页面末端的 `el-tabs`（视图切换区），一个锚点指不到两个 tab 中的哪一个，硬挂一个必然指错；且它们是页面最后一屏，自然滚动即达。
- **接入判据的同步**：`docs/design/components.md` 原写「横向 tabs / 视图切换页（如账户详情的 el-tabs）不接」——本卡核实后确认账户详情页**主体是纵向区块、tabs 在末端**，故判据改写为「纯 tabs / 视图切换页不接；含 tabs 末端的纵向长页可接，tabs 区本身不进目录」。


### 5.3 口径标注（必须做）

集中度有「前 5 占组合 / 组内前 5」，穿透有「证监会门类 / GICS」。**沿用组件自带的口径切换控件，不额外包装、不隐藏**——与组合详情页、持仓分析页完全一致，避免「同数据不同数」。

### 5.4 同步收口文档

| 文档 | 动作 | 状态 |
|---|---|---|
| `docs/working-notes/ledger-detail-info-redesign-plan-2026-08-27.md` | P1 段落补「落库记录」：集中度 ← #2617、行业分布 ← #870/#2595、账户详情内嵌 ← #2739 本 PR；并注明「P1 其余项（当前持仓 / 投资风格 / 股票分布 / 资金流向）仍未做」 | ✅ 已补 |
| 本文档 + 附录 | 状态改为「已实现」并回填裁定结果 | ✅ 已改（PR #2745） |
| `docs/design/components.md` | 登记「账户详情页已接入页内导航」，并改写 tabs 接入判据 | ✅ 已改 |
| `frontend/src/views/asset/position-analysis/index.vue` | 更正 `:7-12` 分工表的歧义措辞（「聚合视图」→「同源同口径」） | ✅ 已改（口径与端点一字未动） |
| `docs/spec/index.md` | 登记本文档与附录 | 见 §5.5 |


---

## 6. owner 裁定（2026-10-29，已落地）

owner 原话：`1.B 2.补导航 3.不做`。

| # | 决策点 | 我的倾向 | owner 裁定 | 落地 |
|---|---|---|---|---|
| 1 | 方案 B′ / A / C | B′ | **B**（即 B′：就地内嵌缺失的两块） | 占位卡 → `LedgerDepthAnalysis`（持仓结构 + 持仓穿透） |
| 2 | 是否同时补页内导航（TOC/锚点） | 本次不做，另开卡 | **补**（本批做） | 从零接入两级页内导航，7 个分区（§5.2） |
| 3 | 是否给聚合页加 `?scope=ledger&id=` 深链 | 本次不做 | **不做** | 聚合页口径与端点一字未动；仅更正歧义措辞 |

> 裁定 2 与我的倾向相反（我倾向另开卡）。实测账户详情页**原本没有**页内导航，「只加两个锚点」的前提不成立，实为从零接入——比原设想的工作量更大，故 §5.2 按实际结构重写。


---

## 7. 验收标准（已执行）

- ✅ **走查**：`grep -rn "敬请期待" frontend/src/views/asset/ledgers/` 零命中；`grep -n "规划中" .../LedgerDetailOverview.vue` 零命中（注释里提到这两个词的是「说明历史」，不是占位卡；回归网按「剥掉 HTML 注释后再扫」判定）。
- ⏳ **走查**：账户详情页该位置渲染出「持仓结构（含前 5 集中度）」与「持仓穿透（行业分布）」两块真实数据；数字与组合详情页同口径、持仓分析页单账户档**完全一致**（同组件同端点，应天然一致，需人工核对一次）—— 待人工过一次真机。
- ⏳ **走查**：账户无持仓 / 持仓为空时，组件走自身空态（不报错、不白屏、不显示 NaN）—— 待人工过一次真机。
- ✅ **判据**：`pnpm typecheck` + eslint（`--max-warnings 0`）+ prettier + stylelint 全部通过。
- ✅ **判据（门禁）**：`node scripts/check_vue_size.mjs --threshold 400 --mode fail --baseline scripts/vue-size-baseline.json` 通过（475 个 .vue，`LedgerDetailOverview.vue` 385 行 / `detail.vue` 314 行，均未超阈）。
- ✅ **判据（CSS 令牌）**：`node scripts/check_css_vars.mjs` 通过（无新增幽灵令牌）。
- ✅ **判据（其它守卫）**：`node scripts/check_router_links.mjs`、`python scripts/guard_detail_tables.py`、`python scripts/guard_soft_banner.py` 全绿。
- ✅ **判据（单测）**：`pnpm test:unit` 全绿（114 文件 / 1557 例），其中新增回归网 6 例。
- ✅ **反向验证 ①（口径）**：`ledgerId` 传 `undefined` ⇒ 面板退化为「全家庭」档（**不是**别的账户的数据）；未归置持仓页整块不展示。
- ✅ **反向验证 ②（回归网有效性）**：四个变异分别把用例打红——① 去掉 `v-if="showDepthAnalysis"`；② 口径改回 `Number(p.ledgerId)`（NaN 直传）；③ 少登记一条 `NAV_LABELS`；④ 把占位卡放回来。复原后全绿。
- ✅ **反向验证 ③（令牌）**：新增锚点只落在既有组件根上，未引入任何自绘样式块，无新增令牌引用。


---

## 8. 明确不做

- **不新写集中度 / 行业分布的计算**——后端已有口径，前端只复用组件。
- **不改后端端点与出参**（`position-structure` / `penetration` 一律不动）。
- **不改持仓分析聚合页**（不加 query 读取、不动其口径）——那是 #2595 的范围。
- **不搬聚合页的整页内容**（口径切换器 / 超额四卡 / 日历 / 归因）——详情页已有，搬了才是冗余（§4 方案 D）。
- **不改 `LedgerDetailHoldingsPane` 的「配置目标」列**（那是五笔钱 `allocation`，与持仓占比无关）。
- **不做 P1 的其余项**（当前持仓、投资风格、股票分布、资金流向）——本次只收「集中度 + 行业分布」，其余仍为规划中，需另开卡。
- **不碰环形图决策**——2026-08-27 计划的「账户维度不显示资产配置环形图」结论继续有效（集中度面板内部另有资产类别占比，与环形图不是一回事）。

---

## 9. 风险

| 风险 | 影响 | 处置 |
|---|---|---|
| 页面变长 | 详情页约 7~8 块 → 约 9~10 块 | 与组合详情页同量级（其 11 块已接受该长度）；**已补页内导航**（§5.2），纵向分区有锚点可达 |
| 口径错位（NaN → 家庭级） | 账户页展示全家庭数据、标签却写「账户」 | 已由 `useLedgerDetail.ledgerIdNum`（只认有限数字）+ `showDepthAnalysis` 双重挡住，并写进回归网 |
| 与聚合页数字不一致 | 用户对比后报 bug | 组件与端点同源，天然一致；**待人工核对一次**并写进 PR 评论 |
| 误读为「重复实现」 | 后续维护者重复造轮子 | §3 的口径说明写进代码注释（组件头注释），`position-analysis/index.vue:7-12` 的歧义措辞**已更正** |
| 导航留死链 | 点胶囊原地不动 | 锚点一律挂块内；`usePageNav` 按 DOM 存在性过滤 + 回归网断言「锚点集 = 标签集」 |
| 旧文档继续误导 | 又有人按 2026-08-27 计划立卡 | §5.4 强制同步旧文档，**已补** |


---

## 10. 关联

- #2739（占位卡处置，本文档的主卡）
- #2595（持仓分析聚合页：三级口径）
- #2617（持仓结构 / 集中度组件）
- #870（持仓穿透 / 行业分布）
- `docs/spec/account-detail-depth-analysis-eval.md`（本文附录：四页面对照矩阵 + 独立冗余评估）
- `frontend/src/views/asset/portfolio/detail.vue:243-255`（组合详情页导航字典 —— 决定性证据）
- `frontend/src/views/asset/position-analysis/index.vue:7-12`（页面分工表 —— 歧义措辞**已于本 PR 更正**为「同源同口径」）
- `docs/working-notes/ledger-detail-info-redesign-plan-2026-08-27.md`（2026-08-27 账户详情页重构计划，本文档为其 P1 收尾）
- `frontend/src/views/asset/ledgers/__tests__/ledgerDepthAnalysisGuard.spec.ts`（本 PR 的回归网：占位卡 / 口径 / 锚点三类退化都会打红）
