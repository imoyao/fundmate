# 对账中心重构方案（reconcile-workbench）

> 状态：**已实施**（2026-11-07，P0+P1+P2 一轮做完；单测 / 类型检查 / 守卫脚本 / 规模门禁 / Playwright 实机 23 例均已通过，见 §12）。
> 触发：2026-11-07 用户反馈三张截图——「信息不完整、语句不通顺」「不是给人类用的」「demo 数据直接上页面」「tab 太多」「和其他页面风格差异太大」。
> 取证范围：`frontend/src/views/asset/investment/reconcile-workbench/**`、`frontend/src/api/reconciliation.ts`、`frontend/src/components/**`、`frontend/src/style/**`、`frontend/e2e/*reconcile*`、`scripts/vue-size-baseline.json`。
> 本文所有「现状」均附代码位置，未做推测；无法确认的一处已标注「待现场核验」。

---

## 1. 结论摘要

根因不是视觉不好看，是**信息架构按后端域编号组织，且把数据库字段原样渲染**。

- 7 个平铺 tab 对应后端域 A~G，是工程分区，不是用户任务。
- 域标题、说明、徽标**根本没渲染**：`index.vue:47` 给 `CardBlock` 传了 `:title` / `:description` / `#action`，而全局 `CardBlock` 是零 props 纯容器（`components/CardBlock/index.vue`），三者被静默吞掉。用户看到的只有统计条和卡片，没有「这一屏在讲什么」。这是「信息不完整」的直接根因。
- 域 F/G 的卡片把 `group.key`、`txn_type`、内部 ID、`active`、ISO 时间戳直接输出，没有任何展示层翻译。
- 域 E 整套用 `--el-*` 变量，其余用项目令牌；页头自写 `WorkbenchHead`，不用 `PageHeaderBar`；卡片自绘，不用 `CardBlock`。风格割裂由此而来。

重构目标：**把「7 个域列表」改成「3 张任务卡 + 1 条待办队列」，把「字段直出」改成「用户语言」，补齐加载/空/错/进度四态与批量处理，全量对齐设计系统组件与令牌。**

**根因再下一层（用户拍板）**：必须把后端视角 / 程序员视角与用户视角分开。用户只关心
「我应该做什么」「我应该看什么、关注什么」；A~G 是扫描器分区，不是任务。旧页面缺一层
「翻译」，把存储字段直接端上桌，所以看起来像草稿。

---

## 2. 实证诊断

### 2.1 结构层

| # | 问题 | 代码位置 | 后果 |
|---|---|---|---|
| S1 | 7 个横向 tab 平铺，按后端域编号 A~G | `constants/domainTabs.ts:43-110`、`index.vue:38-158` | 1400px 内容列里 tab 已挤满，加徽标后更不可读；用户要在 7 个工程概念间切换 |
| S2 | `CardBlock` 的 `:title` / `:description` / `#action` 不生效 | `index.vue:47-50` vs `components/CardBlock/index.vue` | 每个域的标题、说明、类型徽标全部消失；`domainTabs.ts` 里精心写的「措辞边界」用户一个字都看不到 |
| S3 | `<MetricGrid :cols="3">` 是已删除的假 prop | `index.vue:16` vs `components/MetricGrid/index.vue:7-10` | 参数不生效，布局靠 flex 兜底 |
| S4 | `level="待处理"` 借用温度档徽标 | `index.vue:26` | `TemperatureLevelBadge` 的未知文本落「适中·暖沙金」，语义错配 |
| S5 | 顶部指标卡 `caption="可撤销（P2 接入）"` 把开发排期写进 UI | `index.vue:33` | 与 `domainTabs.ts:10-11`「界面上不再出现只有开发者关心的话」自相矛盾 |
| S6 | 顶部「待裁决差异」只统计当前激活域，与各域自己的统计条重复计数 | `index.vue:267-269`、`useWorkbenchDomains.ts:118-140` | 同一个数字出现两次，口径不一致 |
| S7 | 「运行对账」在全局页头，但只跑域 B | `useWorkbenchDomains.ts:309-322`（`runReconciliation("B")`） | 标签承诺全量、实现只跑一类，功能与文案不符 |
| S8 | 页头自写 `WorkbenchHead`，不用 `PageHeaderBar` | `components/WorkbenchHead.vue` | 与 `views/asset/inventory/index.vue` 的基线不一致 |
| S9 | 域 C「对账单导入」是入口动作，却占一个 tab | `index.vue:118-152` | 把工具和待办混排 |

### 2.2 截图 1：补记红利税弹窗

`components/DomainEDividendTaxTable.vue:107-125` 用 `ElMessageBox.prompt` 单输入框：

| # | 问题 | 证据 |
|---|---|---|
| E1 | 语句不通顺：「请对照券商交割单，填写 中金公司 2026-08-21 这笔分红的实际扣税额（元）。」——「填写 X 这笔分红的税额」结构断裂，单位「（元）」挂在宾语后像脚注 | 第 112 行 |
| E2 | 信息不完整：不显示税前分红金额、所属账户、已记税额、扣税日期、记入后会发生什么 | 弹窗只有一个输入框 |
| E3 | **placeholder 是猜数**：`例如 ${dividend_cents * 0.1 / 100}` 按 10% 推算，与同文件第 105-106 行注释「刻意不给默认金额：推算出来的税额是猜的」直接矛盾。用户会把 4.60 当建议值抄进账本 | 第 115 行 |
| E4 | 按钮叫「记一笔」，与右下角全局 FAB「记一笔」同名，语义污染 | 第 118 行 |
| E5 | 校验只有 `inputPattern`，没实现页面文案已声明的「红利税不超过 20%」业务上限 | 第 116 行 vs 第 55 行 |
| E6 | 整段用 `--el-*` 变量（`--el-text-color-regular` 等），与项目令牌脱钩 | 第 158-217 行 |

### 2.3 截图 2：数据缺失（域 F）

`components/DomainFDanglingRefs.vue` + `DanglingRefGroupCard.vue`：

| # | 现状输出 | 问题 |
|---|---|---|
| F1 | `20\|001982 001982` | `group.key` 复合主键直出，重复一次标的代码，用户无法解读 |
| F2 | `7 条交易 · 净额 71.68 · 现存持仓 #697（96.41 份，active）· 2026-06-07 18:33` | 内部 ID、`active` 英文、无单位净额、导入时间挤成一行，无主次 |
| F3 | `has_candidate` / `net_mismatch` | 后端 flag 枚举直出（`DanglingRefGroupCard.vue:52-60` 直接 `{{ f }}`） |
| F4 | `#57 buy 2025-12-12T00:00:00 1.05 份 / 1.05 元 原持仓编号 #25` | `buy` 英文、ISO `T00:00:00`、内部 ID 当主标识、「原持仓编号」无解释 |
| F5 | 6 个统计数字平铺，口径重叠（待处理记录 / 可直接补上关联 / 待处理分组 / 导入批次 / 缺标的代码 / 缺交易日期），全部用 `--color-warning-ink` | 无主次、无可操作性，「导入批次」属工程指标 |
| F6 | 「其中 532 条暂时没法处理…系统不会替你猜归属，补全信息后重新检查即可继续」 | 解释系统行为，没给下一步动作；532 与 637/105 的算术关系未说明 |
| F7 | 122 个分组只有「按批次筛选」，无搜索、无状态筛选、无排序、无批量入口 | 逐组点 122 次不现实 |

### 2.4 截图 3：缺账本流水（域 G）

`components/DomainGOrphanLedger.vue` + `OrphanLedgerGroupCard.vue`：

| # | 现状输出 | 问题 |
|---|---|---|
| G1 | `#3029 dividend_tax 缺交易日期 同花顺（银河证券） -17.5 元 → #12` | 英文枚举、内部 ID、裸负数、箭头指向内部 ID |
| G2 | `目标账本 #12（同花顺（银河证券））· 按账户名精确同名唯一判定` | 括号嵌套；后半句是后端实现说明，不是用户语言 |
| G3 | 26 条明细默认全量铺开，无分页、无默认折叠 | 长页面无节奏 |
| G4 | 统计条与域 F 各写一份几乎相同的 CSS（`.df-summary` / `.olg-summary`），数字全用警示色 | 重复实现、语义错误 |
| G5 | 「其中 N 条…请到「记一笔」或账户页核对后重新扫描」 | 把用户导向无关入口；缺「无法归属」的具体原因清单 |
| G6 | 右侧「流水没有归属账本」带框提示 | **待现场核验**：怀疑是 `title` 属性 tooltip 或域标题残留，需实机确认来源后再处理，不猜 |

### 2.5 功能性缺口（跨三张截图）

| # | 缺口 | 证据 |
|---|---|---|
| Q1 | **失败态缺失**：所有 loader 都 `catch { 置空 }`，加载失败与「没有待办」渲染完全一样 | `useWorkbenchDomains.ts:209-211, 229-233, 246-249, 259-262, 274-278, 344-347` |
| Q2 | 无处理进度、无「本次处理 X 条」结果反馈；后端已有 undo 端点但入口藏在弹窗里 | `api/reconciliation.ts:459-465, 562-568` |
| Q3 | 批量能力后端已支持但前端未用：`reattachDanglingRefs({transaction_ids: number[]})`、`backfillOrphanLedgers({transaction_ids: number[]})` | `api/reconciliation.ts:445-456, 551-559` |
| Q4 | 无空态出路（`<el-empty description="暂无数据缺失" />` 只有一句） | `DomainFDanglingRefs.vue:55-59` |
| Q5 | 每条记录没回答「这是什么 / 为什么找我 / 处理后会怎样」 | 全部卡片模板 |

---

## 3. 重构目标与验收判据

| 目标 | 可验收判据 |
|---|---|
| 条理清晰 | 一级导航 ≤3 项；每个任务视图首屏有「标题 + 一句人话说明 + 待办数 + 主行动按钮」 |
| 人能读懂 | 界面上不出现 `has_candidate`、`net_mismatch`、`dividend_tax`、`active`、`T00:00:00`、`20\|001982`；内部 ID 不出现在任何主视觉行 |
| 语句通顺 | 所有文案按「这是什么 → 为什么找我 → 下一步做什么」三段式重写，主语明确、无括号套括号 |
| 信息完整 | 补记弹窗展示标的、分红日、税前金额、账户、已记税额；每项操作前说明后果，操作后给结果与撤销入口 |
| 风格统一 | 页头 `PageHeaderBar`、区块 `SectionHeader` / `CardBlock`、提示 `SoftBanner`、分段 `SegmentedControl`；零 `--el-*` 硬用；暗色靠 `dark.scss` 自动跟随 |
| 功能完整 | 加载 / 空 / 错 / 正常四态齐备；状态筛选 + 关键词搜索 + 批量处理 + 处理进度 |
| 不破坏契约 | 见 §8 |

---

## 4. 信息架构：7 个域 → 3 张任务卡 + 待办队列

> **2026-11-07 用户拍板修订**。初版方案是「左侧纵向任务导航 + 右侧详情区」，被否：
> 全局侧边栏（`layout/components/lay-sidebar/NavVertical.vue`）已占左侧，页内再加一条
> 纵向任务栏就是「双抽屉」；且 `docs/design/navigation-ia.md` §七的反向约束
> 「业务顶级下不再设目录层，多一层 = 多一次点击 + 多一个要学的名字」同样约束页内导航。
> 换方向不等于减层级。定稿见下。

### 4.1 根因再下一层

「tab 太多」的本质不是导航摆在哪，是**把 7 个后端扫描域当成 7 件用户要做的事**。
用户不关心系统有几个扫描器，只关心「我现在能处理什么、还差什么」。故导航维度从
**数据来源**换成**待办状态**：

| 现状维度（后端视角） | 定稿维度（用户视角） |
|---|---|
| A E账户 / B 持仓快照 / C 导入 / D 重复 / E 分红 / F 缺失 / G 缺账本 | 可直接处理（系统已判定归属，点一下就好）/ 需要我判断（两处数字对不上）/ 需先补全信息（缺代码、缺日期、找不到账本） |

### 4.2 骨架（对齐姐妹页「全面盘点」）

参照 `views/asset/inventory/index.vue` 的 `PageHeaderBar` + 顶部横向 `CategoryTabs`
+ `CategoryDescBar` + `SectionHeader`：全是横向的，**不新增任何纵向栏**。

```
PageHeaderBar  对账中心 / 把账上不一致、记录不全的地方集中核对并修好
  └ 三张横向任务卡（role=button + aria-pressed，带待办数与一句说明；不是 tab）
      核对差异 163  |  补记缺漏 12  |  修正数据 663
  └ 三段式说明条（这是什么 / 为什么找我 / 处理后会怎样）
  └ 待办状态筛选（SegmentedControl，3 档带计数）
      可直接处理 / 需要我判断 / 需先补全信息
  └ 搜索 + 批次 + 批量操作栏
  └ 待办队列（统一卡片，域只作为「来源」小标签）
```

- **一级可见导航 = 3 张卡**，不再是 7 个 tab，且不新增导航容器。卡片本身承载
  「标题 + 数字 + 一句说明」，把 `CardBlock` 假 props 吞掉的信息补回来。
- **点卡片后不是二级 tab**，而是按待办状态筛选的队列。域（A~G）从导航里消失，
  只在卡片上留「来源」标签，供用户定位「这批数据是哪来的」。
- **「对账单导入」不占导航项**，作为「补记缺漏」卡内的行动按钮（它本来就是入口）。
- **默认落地**：无 `?domain=` 时选中待办数最大的任务（对齐 `pickFirstPendingDomain`）。
- **窄屏**：三张卡 `grid-cols-1 md:grid-cols-3`，说明条与筛选行堆叠。

### 4.3 保持的页内行为契约

- 切卡片 / 切状态筛选**只替换队列区**，不重挂载页面组件（`data-mount-probe` 探针判据）。
- URL hash 不写 `domain=`；`?domain=A…G` 入站寻址仍映射到对应任务下的队列。
- 横幅点击 → 落到第一个有待办的任务并定位到队列区。
- 页头保留 `.workbench-head` / `.workbench-head__title` 锚点，任务卡沿用
  `.workbench-tabs` 与 `.domain-tab-count` 锚点，减少 e2e 改动面。

**「运行对账」处置**：现实现只跑域 B（`useWorkbenchDomains.ts:309-322`），却挂在全局页头
承诺全量。定稿 (a)：文案改「重新检查持仓差异」并收进「核对差异」任务说明区，零后端改动、
消除误导。全量扫描另立卡，本期不做。

---

## 5. 组件与文件清单

### 新增（均控制在 400 行门禁内）

| 文件 | 职责 |
|---|---|
| `constants/reconTasks.ts` | 三张任务卡元数据：标题、人话说明、影响说明、主行动文案、收纳的原域 key、状态色、待办数口径。替代 `domainTabs.ts` 的展示职责（后者保留 `WorkbenchDomainKey` 类型与入站寻址） |
| `utils/reconDisplay.ts` | **展示层单一来源**：枚举→中文、日期、金额、内部 ID 降级、复合键解析；份额最多 4 位不抹精度。配套 `__tests__/reconDisplay.spec.ts` |
| `utils/reconQueue.ts` | **7 域 → 一条用户队列**的映射层；`countByTask` / `countOpenItemsByTask` / `countByState` / `filterQueue` / `sortQueue` / `batchableItems`；和式不变量。配套 `__tests__/reconQueue.spec.ts` |
| `utils/reconDetail.ts` | 处理区只读快照类型 + 域 → loader 错误键，供「失败只重试这一个 loader」 |
| `composables/useReconQueue.ts` | 队列页面状态：筛选 / 选中 / 计数 / 入站寻址，全部从同一条队列派生 |
| `composables/useWorkbenchActions.ts` | 弹窗状态、处理区上下文、批量回补后刷新、入站寻址；让 `index.vue` 守住 406 行基线 |
| `components/WorkbenchTaskCards.vue` | 三张横向分诊卡，`role="button"` + `aria-pressed`（**不挂 tablist**），带待办数与一句说明；沿用 `.workbench-tabs` / `.domain-tab-count` 锚点 |
| `components/ReconTaskBrief.vue` | 卡片下方的「这是什么 / 为什么找我 / 处理后会怎样」三段式说明 |
| `components/ReconStatBar.vue` | `MetricGrid` + `MetricCard` 的队列总览，去掉 `level="待处理"` 与「可撤销（P2 接入）」这类开发语义 |
| `components/ReconQueueFilter.vue` | `SegmentedControl`（全部 + 4 档带计数）+ 关键词 + 导入批次 + 批量操作栏 |
| `components/ReconQueueCard.vue` | 统一队列卡：状态徽标、来源小标签、人话摘要、事实 chips、批量勾选、处理按钮 |
| `components/ReconStatusState.vue` | 加载 / 空 / 错 / 正常四态容器，统一文案与重试按钮 |
| `components/ReconQueueDetail.vue` | 主从结构的「处理区」：按来源域分发到既有域面板，保留全部写路径与二次确认 |
| `components/ReconBatchDialog.vue` | 批量回补：影响预览 → 写 → 结果条数 → 凭 `log_id` 撤销；部分成功也保留已完成日志 |
| `components/RecordTaxDialog.vue` | 替换 `ElMessageBox.prompt` 的正式补记弹窗（§7），删掉 10% 猜数 placeholder |

### 改造

| 文件 | 改动 |
|---|---|
| `index.vue` | 换成 `PageHeaderBar` + 总览/任务导航/详情区骨架；去掉不生效的 `CardBlock` props 与 `:cols`；保留 `?domain=` 入站、切域不重挂载、URL 不写 domain |
| `DomainFDanglingRefs.vue` / `DomainGOrphanLedger.vue` | 接入 `ReconStatusState`、`ReconStatBar`、`ReconFilterBar`、`ReconGroupCard`；补错误态与批量 |
| `DanglingRefGroupCard.vue` / `OrphanLedgerGroupCard.vue` | 收敛到 `ReconGroupCard`，或保留薄壳只做数据适配 |
| `DomainEDividendTaxTable.vue` | 令牌改项目变量；补记动作改走 `RecordTaxDialog`；去掉 10% placeholder |
| `composables/useWorkbenchDomains.ts` | 各 loader 增加 `error` ref，区分「加载失败」与「无待办」；不改 API 调用与返回类型 |
| `components/WorkbenchHead.vue` | 收敛到 `PageHeaderBar`（保留 `.workbench-head__title` 作 e2e 锚点，或同步改 spec） |

### 保持不动

- `api/reconciliation.ts`（后端契约零改动）
- `utils/discFormat.ts`、`domainFocus.ts`、`domainQuery.ts`、`*Guard.ts` 及其 spec（纯函数导出签名不变）
- 所有修复 / 回填 / 撤销弹窗的业务逻辑（`DanglingRefFixDialog`、`OrphanLedgerFixDialog`、`DanglingRefRemediationDialog`）
- `dark.scss`（项目令牌自动跟随，不新增硬编码色）

---

## 6. 数据呈现与文案规范

### 6.1 技术字段 → 用户语言（`utils/reconDisplay.ts`）

| 输入 | 现状 | 重构后 | 规则 |
|---|---|---|---|
| `group.key = "20\|001982"` | 原样显示 | 不显示；主标题用 `001982 · 〈名称〉`，key 只作 `:key` | 复合主键永不进视觉层 |
| `txn_type: buy\|sell\|dividend_tax\|bond_redeem` | `buy`、`dividend_tax` | 买入 / 卖出 / 红利税扣款 / 债券兑付 | 复用并**补全** `@/constants/index.ts` 的 `TXN_TYPE_LABELS`；兜底显示「其他」而非露英文 |
| `flags: has_candidate\|net_mismatch` | 原样 | 已找到可挂回的持仓 / 份额与流水不一致 | 新增 `DANGLING_FLAG_LABELS` |
| `ownership_status: active` | `active` | 有效（或省略） | 新增映射 |
| `trade_date: 2025-12-12T00:00:00` | 原样 | `2025-12-12` | 统一 `formatDate`（`@/utils/date`） |
| `trade_date: null` | `缺交易日期` 混在明细行 | 「交易日期未填」+ 状态徽标，可筛选 | 缺值不伪装成内容 |
| `amount: -17.5` | `-17.5 元` | `扣款 ¥17.50` | `formatAmount`（`@/utils/currency`）；负数用文字表意，不用裸负号 |
| `dividend_cents` | `/100` 手算 | `centsToYuan` + `formatAmount` | 禁止散写 `/100` |
| `#3029` / `#12` / `#697` | 当主标识 | 折叠进「技术详情」，标注「记录编号」 | ID 不占主视觉行 |
| `resolved_ledger_id: 12` | `→ #12` | 「拟归入：同花顺（银河证券）」 | 用名称不用 ID |

### 6.2 文案对照（逐条替换）

| 现在 | 重构后 |
|---|---|
| `20\|001982 001982` | `001982 · 〈基金名称〉` + 徽标「需回补关联」 |
| `7 条交易 · 净额 71.68 · 现存持仓 #697（96.41 份，active）· 2026-06-07 18:33` | 「这 7 笔交易还挂在一条已删除的持仓上，共 71.68 份。系统找到一条现存持仓（96.41 份），可以挂回去。」 + 次要行「来自 2026-06-07 18:33 的导入」 |
| `has_candidate` `net_mismatch` | 「已找到可挂回的持仓」「份额与流水不一致」 |
| `#57 buy 2025-12-12T00:00:00 1.05 份 / 1.05 元 原持仓编号 #25` | 明细表行：`2025-12-12` \| `买入` \| `1.05 份` \| `¥1.05` \| `指向已删除的持仓` |
| `#3029 dividend_tax 缺交易日期 同花顺（银河证券） -17.5 元 → #12` | `红利税扣款` \| `交易日期未填` \| `同花顺（银河证券）` \| `扣款 ¥17.50` \| `拟归入：同花顺（银河证券）` |
| `目标账本 #12（同花顺（银河证券））· 按账户名精确同名唯一判定` | 「这 26 笔流水的账户名与账本「同花顺（银河证券）」完全一致，可归入该账本。」 |
| `其中 532 条暂时没法处理：有的没填标的代码，有的对应持仓记录已被删除。系统不会替你猜归属，补全信息后重新检查即可继续。` | 「还有 532 笔暂时不能自动处理：缺标的代码，或对应持仓已删除。先补全信息，再回来批量挂回。」 + 按钮「去补全信息」 |
| `其中 N 条按账户名找不到唯一同名账本，系统不会猜测归属；请到「记一笔」或账户页核对后重新扫描。` | 「有 N 笔找不到唯一对应的账本，没有被自动归入任何账户。常见原因：账户名与账本名不一致、同名账本有多个。可在账户管理中核对名称后重新检查。」 |
| `逐条核对并归集` / `逐条核对并回填` | 「核对 26 笔并归入账本」 |
| `按批次筛选` | 「来自哪次导入」+ 下拉 |

### 6.3 三段式模板（每条任务统一）

```
这是什么   〈一句陈述事实，含数量与对象〉
为什么找我 〈一句说明影响：报表会漏算 / 账户视图看不到 / 账外少一笔〉
下一步      〈主行动按钮〉+〈处理后会发生什么，写清是否可撤销〉
```

示例（修正数据 · 数据缺失）：
> **有 637 笔交易缺少完整信息**
> 这些交易找不到对应的持仓记录，或缺少标的代码、交易日期，资产报表会漏算这部分。
> 系统只在能确定归属时才允许回补；先补全缺失字段，再批量挂回。每次回补都可撤销。

---

## 7. 补记红利税弹窗规格（替换 `ElMessageBox.prompt`）

对齐 `SupplementDialog.vue` / `DividendForm.vue` 的项目级表单规范：

- **标题**：「补记这笔分红的扣税」
- **上下文卡（只读）**：标的名称与代码 / 分红日期 / 税前分红金额 `¥…` / 所属账户 / 当前已记税额
- **说明**：「这笔分红在券商交割单上被扣了税，账里还没有记录。红利税按实际持股期计算，税率取决于买入批次，系统不替你推算，请按交割单填写。」
- **输入**：
  - 实际扣税额：`el-input-number`，`¥` 前缀，`:precision="2"`，`:min="0"`，`:controls="false"`
  - **删除**按 10% 推算的 placeholder，改为辅助文案「以交割单上「红利税」一栏金额为准」
  - 扣税日期：`el-date-picker`，默认分红日，可改
- **校验**：必填、> 0、≤ 税前分红 × 20%（与页面已声明的业务上限一致）、最多两位小数
- **后果说明**：「确认后会生成一笔扣税流水，可在交易流水中查看或撤销；同一标的同一天的重复提交不会重复记账。」（后端 `recordDividendTax` 幂等，见 `api/reconciliation.ts:298`）
- **footer**：`取消` / `确认补记`（不再叫「记一笔」，避免与全局 FAB 混淆）
- **样式**：全部项目令牌，零 `--el-*`

---

## 8. 兼容性契约（不可破坏）

1. **e2e 锚点**：`.workbench-head__title`、`.df-summary`、`.olg-group__block`、`.olg-hint`、`.df-hint`、`.recon-notice__title`、`.domain-tab-count`、`.recon-banner` 等被 8 个 spec 引用。结构变了必须**同步改 spec**，不能留红灯。清单：`reconcile-workbench-head.spec.ts`、`dangling-ref-remediation.spec.ts`、`orphan-ledger-domain-g.spec.ts`、`discrepancy-banner-slim.spec.ts`、`reconcile.spec.ts`、`recognizer-import.spec.ts`、`eaccount-draft.spec.ts`、`eaccount-ai-quota.spec.ts`。
2. **行为判据**：「切任务 / 点横幅不重挂载页面组件」（`data-mount-probe` + 请求数）、「URL hash 不含 `domain=`」——左侧导航切换必须同样满足。
3. **入站寻址**：`?domain=A…G` 继续有效，`normalizeDomain` 与 `pickFirstPendingDomain`（优先级 B→C→A→D→E）不变。
4. **纯函数**：`utils/discFormat.ts`、`domainFocus.ts`、`domainQuery.ts`、`*Guard.ts` 导出签名与判据顺序不变，对应 5 个 spec 全绿。
5. **后端**：API 路径、请求体、数据库零改动。批量能力用现有数组参数，不新增端点。
6. **规模门禁**：`scripts/check_vue_size.mjs` 阈值 400；`index.vue` 基线 406（当前 386，只减不增）；任何新增 `.vue` 不得 >400 行。
7. **守卫脚本**：`guard_segmented.py`（只用 `SegmentedControl`）、`guard_soft_banner.py`、`guard_breakpoints.py`、`check_css_vars.mjs`、`audit_text_contrast.mjs`。亮色改动不改 `dark.scss`。

---

## 9. 分阶段实施与回滚

| 阶段 | 内容 | 独立价值 | 验证 |
|---|---|---|---|
| **P0 止血** | `reconDisplay.ts` + 单测；域 F/G 卡片与文案翻译；补记弹窗重写；去掉 10% placeholder；`--el-*` → 项目令牌；loader 错误态 | 不动架构即可解决三张截图里「读不懂」和金融误导 | `vitest` 5+1 个 spec、`check_vue_size`、`check_css_vars` |
| **P1 架构** | `PageHeaderBar` + 三张横向任务卡 + 三段式说明 + 待办队列 + 主从处理区；`SectionHeader` / `CardBlock` / `SoftBanner` / `MetricGrid` 对齐；去掉不生效 props | 7 个 tab→3 张卡，标题说明真正渲染出来 | 同步改 4 个 e2e spec；实机切任务不重挂载 |
| **P2 功能** | 状态筛选 + 关键词搜索 + 批量处理 + 处理进度与撤销入口；四态容器全量接入 | 663 条待办可批量收敛 | 实机跑一次批量回补 + 撤销 |

**提交与回滚**：
- 从 `dev` 切 `feat/reconcile-workbench-ia-redesign`，每个阶段一个独立 commit，可单独 `revert`。
- 回滚不涉及数据迁移、不涉及后端、不涉及 API；最坏情况 `git revert <commit>` 回到现状。
- 改动前先 `git diff` 确认主仓只有他人留下的未跟踪文件，不误带。

**验证命令**（`frontend/` 下）：
```bash
pnpm exec vitest run src/views/asset/investment/reconcile-workbench/utils/__tests__
pnpm exec playwright test e2e/reconcile-workbench-head.spec.ts e2e/orphan-ledger-domain-g.spec.ts e2e/dangling-ref-remediation.spec.ts
node ../scripts/check_vue_size.mjs --threshold 400 --mode fail --baseline ../scripts/vue-size-baseline.json
node ../scripts/check_css_vars.mjs
```

---

## 10. 决策记录（2026-11-07 已拍板）

| # | 决策 | 结果 |
|---|---|---|
| **D1** | 信息架构形态 | ~~左侧任务导航~~ **否决**：与全局侧栏构成双抽屉，且只是把导航换个方向摆。<br>定稿：**三张横向任务卡 + 待办队列**（§4.2），对齐姐妹页「全面盘点」，不新增纵向栏；导航维度从「数据来源」换成「待办状态」 |
| **D2** | 本期范围 | **P0+P1+P2 全做**（止血 + 架构 + 批量/搜索/进度/撤销） |
| **D3** | 「运行对账」按钮 | **(a)** 改名「重新检查持仓差异」并收进「核对差异」任务说明区，零后端改动 |
| **D4** | e2e 锚点 | **(a)** 同步改 spec 匹配新结构；但保留 `.workbench-head` / `.workbench-tabs` / `.domain-tab-count` 三个高频锚点，减少改动面 |

按 P0→P1→P2 实施，每阶段独立 commit、可单独 revert。

---

## 11. 设计规范符合性清单（2026-11-07 读 `frontend/design.md` + `docs/design/components.md` 后补充）

用户要求「把 UI 做得精致、阅读 design 设计、规范化代码编写」。以下每条都是**机械约束**，
不是风格建议；违反会被 CI 守卫拦截或与设计语言冲突。

### 11.1 三张任务卡不是 tab（重要修正）

`design.md:966` 与 `components.md:33,157` 定稿：`role="tablist"` 的「多选一」按钮组
**一律走 `SegmentedControl`**，页面手写 tablist 视为回潮，由 `scripts/guard_segmented.py` 拦截。
初稿把三张任务卡标成 `role="tablist"` / `role="tab"` 会直接踩守卫。

定稿形态：**三张卡 = 数据分诊摘要卡**，对齐 `design.md:848`「导入预览问题摘要三卡片」(#1791)：

- 「卡即过滤器」：点卡片过滤下方队列，卡片常驻；不是切换视图的 tab。
- 语义用 `role="button"` + `aria-pressed`（沿用姐妹页 `CategoryTabs.vue` 的既有写法），
  **不挂 tablist**，因此不触发 `guard_segmented.py`。
- 卡上承载「条数 + 一句说明 + 状态色」，语义色只标任务性质，不表示条数多少。
- 待办状态筛选（4 档带计数）走 **`SegmentedControl` `default` 档**，符合 `design.md:843`
  「一级筛选平铺、带计数、不横向滚动」。
- `design.md:844` 明文「二级筛选严禁放左侧边栏」——正是用户否决左侧导航的同一条判据。

### 11.2 令牌与组件（禁止手写）

| 项 | 必须用 | 依据 |
|---|---|---|
| 页面页头 | `PageHeaderBar`（`#action` 槽放操作，不另起工具条） | `design.md:426`「一层页头」、`components.md:31` |
| 区块标题 | `SectionHeader`（禁手写 `<h2>` + 散落图标） | `components.md:69` |
| 指标数字 | `MetricGrid` + `MetricCard`（无 `cols` prop） | `components.md:16`、`design.md:412` |
| 金额 | `MoneyDisplay` / `formatAmount`，¥ 与数字同基线 | `design.md:1095-1118` |
| 日期 | `formatDate` / `formatDateTime`，**ISO 带 T 禁止原样渲染** | `design.md:1128-1133` |
| 卡片容器 | `CardBlock`：`--bg-card` / `--radius-md` / `--shadow-raised` / `--space-standard` | `design.md:679` |
| 徽章 | `--bg-soft` / `--text-secondary` / `--radius-pill`；**红绿仅涨跌专用** | `design.md:688` |
| 主按钮 | 40px / `--radius-sm`，底色 `--brand-solid`（白字 4.92:1 达 AA） | `design.md:596-602` |
| Focus | `--focus-ring` | `design.md:369` |
| 断点 | `@/style/breakpoints` 的 `bp.below/above`，禁裸像素媒体查询 | `components.md` / `guard_breakpoints.py` |
| 提示条 | `SoftBanner`（禁自绘） | `guard_soft_banner.py` |

暗色不新增硬编码色：只引用语义令牌，由 `dark.scss :root.dark` 覆盖（`design.md:340`）。

### 11.3 文案口径（`design.md §Voice & Content`）

- **禁说「请」「非常」「卓越」**；标题/按钮用「动词 + 名词」，禁「确定」「OK」。
  → 原弹窗「请对照券商交割单，填写…」必须重写。
- 错误提示 = 描述问题 + 给出下一步；成功提示 = 直接陈述结果（含条数）；
  进行中 = 动词 + 省略号；空态 = 指向第一个行动。
- 数字：阿拉伯数字 + `¥` + 千分位（`¥3,245.67`）；份额 2 位；负数用减号且**只生成一次符号**。
- **技术标识不进用户语言**：内部 ID、英文枚举、`active`、复合键一律翻译或降级到「技术详情」。

### 11.4 交互状态与无障碍

- 交互态按 `design.md:584` 四态（Default / Hover / Active / Focus / Disabled）；
  软按钮点击不做位移，只用底色加深反馈（`design.md:621`）。
- 卡片点击区 ≥ 44px；`:focus-visible` 用 `--focus-ring`；
  `prefers-reduced-motion` 下禁用非必要过渡。
- 三张分诊卡用 `aria-pressed` 表达选中，队列列表用语义 `<ul>/<li>`，
  空态与加载态用 `role="status"` / `aria-live="polite"`。

---

## 12. 实施结果（2026-11-07）

### 12.1 落地形态

```
PageHeaderBar（.workbench-head / __title / __subtitle 锚点，AI 识别 + 重新检查持仓差异）
  └ WorkbenchBanner（有 N 项差异待办，点击落到第一个有待办的任务）
  └ 加载失败 SoftBanner（几类数据没加载 + 重新加载，不再伪装成没待办）
  └ ReconStatBar（待办事项 / 可直接处理 / 涉及记录）
  └ WorkbenchTaskCards（3 张卡，卡即过滤器，二次点击取消筛选）
  └ ReconTaskBrief（这是什么 / 为什么找我 / 处理后会怎样）
  └ 识别草稿面板（持仓 + 交易，不再藏在域 tab 里）
  └ 待办队列（SegmentedControl 4 档 + 关键词 + 批次 + 批量栏 + 四态）
  └ ReconQueueDetail（点一条 → 展开对应来源的既有域面板）
```

- 域 A~G 从**导航维度**降为队列卡上的「来源」小标签；`?domain=A…G` 仍可入站直达，
  页面据此选中任务卡并展开处理区（即使该类 0 条也显示空态）。
- 页内切任务 / 切筛选**不写回 URL**、**不重挂载**（`.workbench-head` 探针仍存活）。
- 写路径零重写：归因覆盖、删除重复交易、补全 / 回补 / 撤销全部沿用既有弹窗与端点；
  新增的批量能力只用后端已有的 `transaction_ids` 数组与 `log_id` 撤销。

### 12.2 翻译层覆盖的旧问题

| 旧输出 | 新输出 |
|---|---|
| `20\|001982 001982` | 只显示 `001982`，复合主键只作 `:key` |
| `has_candidate` / `net_mismatch` / `active` | 已找到可挂回的持仓 / 份额与流水不一致 / 有效 |
| `#57 buy 2025-12-12T00:00:00` | `2025-12-12` \| `买入`，内部编号降级为「记录编号」 |
| `-17.5 元 → #12` | `扣款 ¥17.50` + `拟归入：同花顺（银河证券）` |
| `dividend_tax` / `bond_redeem` | 红利税扣款 / 债券兑付（`TXN_TYPE_LABELS` 已补全） |
| `按账户名精确同名唯一判定` | 「账户名与账本名不一致，或同名账本有多个」+ 下一步 |
| 补记弹窗「例如 4.60」 | 删除猜数；展示税前分红 / 账户 / 已记税额 + 20% 上限校验 + 后果说明 |

### 12.3 校验结果

| 命令 | 结果 |
|---|---|
| `vitest run .../utils/__tests__` | **74 passed / 7 files** |
| `vue-tsc --noEmit --skipLibCheck` | 通过（0 error） |
| `eslint --max-warnings 0`（改动文件） | 通过（`--fix` 收敛 Prettier 后 0 error） |
| `guard_segmented.py` / `guard_soft_banner.py` / `guard_breakpoints.py` | 全绿 |
| `check_css_vars.mjs` | 通过（无新增幽灵令牌） |
| `check_vue_size.mjs --mode fail` | 通过；`index.vue` 由 386 → **313 行** |
| `vitest run`（全量） | **2302 passed / 169 files** |
| `playwright test`（4 个已同步 spec + 全局横幅 spec） | **23 passed**：`reconcile-workbench-head` 4、`dangling-ref-remediation` 6、`orphan-ledger-domain-g` 4、`recognizer-import` 4、`discrepancy-banner-slim` 5 |

### 12.4 实机暴露并修掉的一个回归

首轮 e2e 有 3 条写路径用例红灯（补全 / 显式删除 / 回填撤销）：处理区外层原本用
`ReconStatusState` 在 `loading` 时替换内容，而 `DanglingRefRemediationDialog` /
`OrphanLedgerFixDialog` 挂在被替换的域面板内部。写完触发刷新 → 面板卸载 → 弹窗被
连带关掉，用户看不到「已处理 / 日志编号 / 撤销」结果。

**修法**：处理区改为 `v-loading` 遮罩（只盖住、不卸载）+ 独立 `SoftBanner` 错误提示；
域面板内部各自的四态容器只管列表区，弹窗放在容器之外。修完 10 条域 F/G 用例全绿。

**剩余待办**：批量回补 + 撤销尚无 e2e 用例覆盖（本轮由 `ReconBatchDialog` 实现，
后端端点与 `log_id` 撤销链路已复用既有契约），建议下个迭代补一条批量桩用例。
