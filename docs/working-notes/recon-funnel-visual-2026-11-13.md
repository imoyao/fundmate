# 对账中心阶段漏斗：视觉 spec（2026-11-13）

> 上位结构 spec：[recon-funnel-2026-11-13.md](./recon-funnel-2026-11-13.md)（§2 阶段归属、§3.2–§3.6 实现口径）。
> 上位设计规范：`frontend/design.md`「先删，再重排」（2026-11-13）与「反 AI 味：界面不是给作者自己看的」（2026-11-13）。
> 本文件是**视觉与文案**的实现口径：lane B 的 fixer 照本文件改下列文件，不需要再问。
>
> 覆盖文件（均为 lane B 范围，本文只写不改）：
> `WorkbenchTaskCards.vue`、`ReconQueueDetail.vue`、`DomainFDanglingRefs.vue`、
> `DanglingRefGroupCard.vue`、`ReconItemAction.vue`、`index.vue`、`utils/*`、`constants/*`、`composables/*`。
> 两个弹窗（`DanglingRefRebuildDialog.vue` / `DanglingRefRemediationDialog.vue`）已由 lane A 按「先删，再重排」精简完毕，本文件不再覆盖。

## 0. 全局口径（每一节都适用，先读）

1. **第一遍是删**：动任何区块前，先删三类东西——① 标语（标题已把话说完）；② 解释操作机制的套话（「这是写操作」「可凭日志编号撤销」「有二次确认」）；③ 与结构区重复的复述句。删完再读一遍，看得懂就收工。
2. **标题是标签，不是句子**：`·` 后面只放**计数或单位**（`重建持仓 · 2 组 6 条`），不放从句与判断（「按现在能不能动手排好了」一律不写）。
3. **不对界面做旁白**：「点一条待办，右侧会打开…」「下面的操作会写回账本…」这类句子要么做成可见结构（分组、计数、状态徽标），要么删掉。
4. **机制解释不进界面**：可撤销、写审计日志、按什么口径派生 → 文档与日志。界面上只留用户**当下要做的那个决定**。
5. **样式只用 CSS 变量**，禁硬编码 hex；禁止 Emoji；涨红跌绿用语义变量；分段控制器只用 `SegmentedControl`；离线图标只用 `ep:*` 或内联 SVG。
6. **行数门禁**：`.vue` 单文件 ≤400 行；`index.vue` 在 `scripts/vue-size-baseline.json` 基线内（406），只降不涨。
7. **不新增写路径、不改提交参数语义、不动 `danglingNextStep`**（结构 spec §5「明确不做」）。阶段归属判据只有 `danglingRefEnrichScope.ts` 一份，组件只消费不重算。

---

## 1. 分诊卡 3 → 4（`WorkbenchTaskCards.vue` + `constants/reconTasks.ts`）

### 1.1 现状与要删的东西

| 现状 | 处置 | 为什么 |
|---|---|---|
| 三张卡（核对差异 / 补记缺漏 / 修正数据） | 保留，追加第 4 张 | 域 F 的 `rebuild` 组是**待重建任务**，挂在「修正数据」下语义错位（结构 spec §2 表格） |
| 卡脚注「N 件可一键处理」「· 另有 M 件需你逐条判断」 | **整段删掉** | 角标已给总数；「可一键处理」是队列筛选器的一档（`RECON_QUEUE_STATES` 的 `可直接处理`）、统计条 `ReconStatBar` 也给全局 ready 数——这是同一口径的第三、四处出现。删掉脚注后，「脚注数字和角标对不上」的问题自动消失，不需要再修 |
| `readyCounts` prop、`manualCount()` 函数 | 删 | 只服务于被删的脚注 |
| 空态「暂无待办」 | 保留 | 告诉用户这张卡现在没事，是行动信息不是占位旁白 |

### 1.2 第 4 张卡：数据（`constants/reconTasks.ts` 已落地，本节只做对齐确认）

`rebuild` 任务条目与 `tone: "neutral"` 枚举已由结构 lane 写入 `constants/reconTasks.ts`（hint「交易还挂在账里，但持仓记录没了，收益会漏掉这一段」、what / why / next 三段式同在）。**以仓库现状为准，本 lane 不重写文案**；本文件只裁定展示层的三件事：

- **tone 的视觉含义 = 「无专属语义色」**：`.recon-task-card--neutral .recon-task-card__label` 不需要新规则（标签保持默认 `--text-primary`）。若想显式自证意图，写一条 `color: var(--text-primary);` 即可，不引入任何新令牌。四卡色序：蓝（核对差异）→ 品牌（补记缺漏）→ 橙（修正数据）→ 默认墨（待重建持仓），无相邻冲突。
  - 本文件原稿曾建议 `brand`（与「补记缺漏」同属「把缺的东西补回账里」）；`danger` 已否决——按规范危险色只留给破坏性操作，「重建」是建设性恢复，用红会把「这里损失了数据」误读成「这个动作危险」。
- **不新增 tone 枚举值、不加彩色 CSS**：`neutral` 在 `WorkbenchTaskCards.vue` 里只要求类型与模板正常工作（`:class` 绑定 `recon-task-card--neutral` 无对应规则也合法）。

### 1.3 4 张卡的栅格（窄屏降列方案）

现状 `repeat(auto-fit, minmax(220px, 1fr))` 在 4 卡时会出现 **3+1 孤行**（容器宽约 964–1168px 时前 3 列 + 第 4 张掉到第二行左侧）。改用**确定性栅格 + 断点单一来源**（`guard_breakpoints.py` 禁裸媒体查询，须走 `bp` mixin）：

```vue
<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.workbench-tabs {
  display: grid;
  grid-template-columns: 1fr;          /* 默认单列（手机） */
  gap: var(--space-3);
  margin-bottom: var(--space-standard);
}

/* ≥640px：两列两行 */
@include bp.above("sm") {
  .workbench-tabs {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

/* ≥1024px：一行四张（桌面工作台常态） */
@include bp.above("lg") {
  .workbench-tabs {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
</style>
```

- 卡内布局（label + 角标 / hint / 空态）不变；`minmax(0, 1fr)` 防长词撑爆列。
- 同步把文件头注释里「auto-fit 让窄屏自动收成单列」那句改成上面的断点口径，别留过期注释。
- 断点取值来自 `frontend/src/style/_breakpoints.scss` 单一来源，与 Tailwind `sm:` / `lg:` 前缀同阈值。

### 1.4 验收

- `RECON_TASKS` 四张卡齐全；任一队列数据下 `taskCounts` 各键之和 = 队列 open 项数（和式不变量，结构 spec §3.3 要求单测钉住）；
- 桌面 ≥1024px 一行四张等宽；640–1023px 两列两行；<640px 单列——**任何宽度都不出现 3+1**；
- 卡面用户可见文本 = label + 角标数字 + hint 一行 +（空态时）「暂无待办」；脚注拆分消失；
- `scripts/check_vue_size.mjs --mode fail` 无回涨。

---

## 2. 队列区标题与说明（`index.vue`）

### 2.1 现状

```html
<SectionHeader
  :title="`待办队列${taskLabel ? ` · ${taskLabel}` : ' · 全部任务'}`"
  info="按「现在能不能动手」排序。点一条待办，右侧会打开这条的来龙去脉、投资轨迹和处理动作。"
/>
```

### 2.2 最终形态

```html
<SectionHeader :title="taskLabel ? `待办队列 · ${taskLabel}` : '待办队列'" />
```

- **`info` 整个删掉**（不是改短）。「按『现在能不能动手』排序」是排序机制的自我说明；「点一条待办，右侧会打开…」是交互旁白——用户点一次就知道了，不需要预告。排序本身已经由队列卡的「可直接处理 / 需要判断 / 需先补全」状态徽标**可见地**表达，不需要句子。
- **`· 全部任务` 删掉**：`·` 后面只放计数或单位（反 AI 味 ①）。「全部任务」既不是计数也不是单位；未筛选时「待办队列」三个字本身就是全部。筛选中保留 `· 核对差异` 这类**任务名**（它是一个范围限定词，与弹窗标题「补全信息 · 名称」同构）。

### 2.3 验收

- 未筛选：标题就是「待办队列」，下方无任何说明条；筛选中：`待办队列 · {任务名}`；
- 页面不再出现「来龙去脉」「右侧会打开」「按…排序」字样；
- `index.vue` 行数下降（基线 406，只减不增）。

---

## 3. 抽屉：阶段面板（`ReconQueueDetail.vue` 的 `activeStage` 分支 + `DomainFDanglingRefs.vue` 改纯导航）

### 3.1 什么时候渲染什么

| 状态 | 抽屉内容 |
|---|---|
| `activeStage` 非空（点队列聚合项进来） | **阶段面板**：只列该阶段的组，每组一张组卡（§4） |
| `activeStage` 为空且 `?domain=F` 直达 | 阶段面板的全量形态（所有阶段按 `DANGLING_STAGES` 固定顺序 `fill → reattach → rebuild` 连续渲染，每段一个小标题） |
| 该阶段 0 组 | **整段不渲染**——不渲染空标题、不渲染「暂无」占位（design.md「空阶段不渲染」） |

### 3.2 阶段面板标题（`SectionHeader`）

```html
<SectionHeader :title="`${stageLabel} · ${groups.length} 组 ${txnSum} 条`" />
```

- `stageLabel` 取 `DANGLING_ACTION_LABEL[stage]`（`utils/reconQueue.ts` 已有：回补关联 / 补全信息 / 重建持仓），**不新造第二份阶段名**。
- `txnSum` = 该阶段各组 `txn_count` 之和（与队列聚合项的 `count` 同一和式，别另算）。
- 无 `info`。阶段面板上方不需要「这些是…的交易」句子——标题已经说了有几组几条。
- 抽屉头部（`recon-detail__sub`）在阶段模式下显示阶段动作名；把兜底旁白 **「对照上面的记录再决定怎么处理」删掉**（它是给「不知道怎么决策」的用户写的一句安慰话，实际什么也没说；`stateReason` 有值时照旧显示）。头部标题维持 `domainLabel`（「数据缺失」）不动。

### 3.3 `DomainFDanglingRefs.vue`：从「域面板」改成「纯导航列表」

**删掉（连同对应 script 状态、emit、样式）**：

| 删除 | 为什么 |
|---|---|
| 汇总条 `df-summary` 四个统计（受影响的交易 / 已找到可挂回的持仓 / 缺标的代码 / 缺交易日期） | 它描述的是**全域**，而阶段面板只承载**一个阶段**；组数与条数已在面板标题、组卡上各出现一次 |
| 覆盖率提示 `df-hint`（「还有 N 条暂时不能自动处理…先补全信息，再回来批量挂回。」） | 跨阶段指路句（结构 spec §3.6）+ 机制旁白；「缺标的代码 / 持仓已删除」的原因已写在各组的 `block_reason` 与队列卡 `stateReason` 上 |
| 导入批次筛选 `df-filter`（label「来自哪次导入」+ select） | 纯导航列表不做第二层筛选；批次信息保留在组卡 meta 的 `reconBatchLabel` 一处 |
| 两个弹窗（`DanglingRefRemediationDialog` / `DanglingRefRebuildDialog`）及其全部状态（`activeMode` / `activeGroup` / `dialogVisible` / `rebuildVisible` / `rebuildGroup` / `onEnrichRequestRebuild` / `onRebuildVisibleChange`） | 写动作唯一入口在执行区（§5）；面板只导航（design.md「清单只做导航，不做第二套动作」） |
| emits `fix` / `enrich` / `remove` | 同上 |

**保留 / 改成**：

- props 收窄为 `groups: DanglingRefGroup[]`、`loading: boolean`、`error?: string`（不再收 `data: DanglingRefList`——组列表由 `ReconQueueDetail` 用 `bucketByStage` 过滤后传入，组件内不再自己筛批次/阶段）；
- emits 收窄为 `retry: []`、`openItem: [group: DanglingRefGroup]`（`openItem` 由组卡的「处理」按钮上抛，见 §4）；
- `ReconStatusState` 的 loading / error / retry 与空态（`?domain=F` 直达且无组时 `暂无数据缺失`）保留；
- 组列表容器 `df-groups`（纵向 flex、gap 12px）不变。

### 3.4 `ReconQueueDetail.vue` 的接线（视觉侧要点）

- `activeStage` 非空 ⇒ 用 `bucketByStage(ctx.danglingRefs?.groups ?? [])` 取该阶段组数组传给 `DomainFDanglingRefs`，并传 `stageLabel`；`activeDetailId` 保持清空（结构 spec §3.4 的 `openStage` 已定义）。
- 组卡「处理」点击 ⇒ 打开该组的执行区（复用既有 `item` 渲染路径，让抽屉从「阶段导航」切到「单组执行区」）。**视觉上必须有一条可见的返回路径**：执行区顶部（`ReconItemAction` 上方）渲染一行返回入口——一个 `text` 型小按钮「返回阶段列表」，点击回到阶段面板（清 `item`、保留 `activeStage`）。不要用抽屉头部加第二个关闭按钮的方式（× 是唯一关闭入口，此前已刻意收敛）。
- 处理动作区的 `SectionHeader`：标题 `处理动作` 保留，**`info`（「下面的操作会写回账本；有二次确认的会先弹确认。」）删掉**——机制旁白（反 AI 味 ③）。

### 3.5 验收

- 点队列聚合项：抽屉只出现一个阶段的面板，标题形如 `重建持仓 · 2 组 6 条`，无 info、无汇总条、无批次筛选、无指路句；
- 空阶段不产生任何 DOM；`?domain=F` 直达时按 fill → reattach → rebuild 顺序只渲染有组的段；
- 组卡上点「处理」能到达执行区，且执行区有可见的「返回阶段列表」；
- `DomainFDanglingRefs.vue` 行数大幅下降（删掉汇总条/筛选/两个弹窗后应 < 120 行）。

---

## 4. 组卡（`DanglingRefGroupCard.vue`）

### 4.1 现状 → 最终形态

**删掉**：

- 头部四个动作按钮与 `fix` / `enrich` / `remove` / `rebuild` 四个 emit（含 `canRebuild` / `canFill` / `step` 这组互斥判断与 `danglingNextStep` / `inspectGroupNeeds` import——阶段归属已由上游 `bucketByStage` 决定，组卡不再自己算第二遍）；
- flags 区的空态占位 **「没有附加异常」**（`df-group__noflag`）——「这里没事」不是一个待展示的标签（design.md「空阶段不渲染」同理由）；无 flags 时整个 `df-group__flags` 容器不渲染。

**保留**：

- 标题行：`reconGroupTitle`（名称优先）+ 副标题 `reconBatchLabel`；
- meta 行：`{txn_count} 条 · 净额 {net_units}` + `现存持仓 …（…）` 或 `对应持仓记录已删除`；
- `block_reason` 警示条（`df-group__block`）——它回答「这组为什么卡在这个阶段」，是行动信息；
- 有 flags 时的 flag 徽标；
- 折叠明细 `查看 {N} 条交易明细`（`el-collapse`，标题文案不变）。

**新增（唯一动作）**：

- 头部右侧一个按钮：文案 **「处理」**，`size="small"`、`type="primary"`、`plain`，`@click="emit('openItem', group)"`。
- 每张组卡在阶段面板内必然属于同一阶段 ⇒ 按钮不需要按组算条件，无 disabled 态；阶段动作名（回补关联 / 补全信息 / 重建持仓）由面板标题说一次，按钮只叫「处理」，不再在每张卡上复述动作名。

### 4.2 最终排版（DOM 顺序）

```html
<article class="df-group">
  <header>  ← title(key+subtitle) 左 · 「处理」按钮右，space-between
  <p class="df-group__block">（block_reason，仅有则渲染）
  <p class="df-group__meta">（条数 · 净额 · 现存持仓/已删除）
  <div class="df-group__flags">（仅有 flags 时渲染）
  <el-collapse>（查看 N 条交易明细）
</article>
```

样式类沿用现有，不新增视觉块；`df-group__actions` 从多按钮 flex 简化为单按钮（规则可保留）。

### 4.3 验收

- 组卡上**不存在**任何「回补关联 / 补全信息 / 重建持仓 / 删除 / 去处理」按钮；「删除」入口在整个导航层（队列卡、分诊卡、阶段面板、组卡）均为 0 个；
- 无 flags 的组卡不出现「没有附加异常」；
- 点「处理」必达执行区（§5），无第二层中间页；
- 组件不再 import `danglingRefEnrichScope`。

---

## 5. 执行区唯一动作面（`ReconItemAction.vue`）

### 5.1 域 F 的按钮映射（取代现有 `danglingIncomplete` 分支的散装判断）

按队列项 `payload.stage`（结构 spec §3.2 的 `danglingStageItem`）：

| 阶段 | 主按钮（第一顺位） | 次按钮（第二顺位） |
|---|---|---|
| `reattach` | 回补关联 → 走既有 `emit('fixDangling', group)`（`index.vue` 的 `DanglingRefFixDialog`） | 删除 → 打开 `DanglingRefRemediationDialog` `mode="delete"` |
| `fill` | 补全信息 → 打开 `DanglingRefRemediationDialog` `mode="enrich"` | 删除 → 同上 |
| `rebuild` | 重建持仓 → 打开 `DanglingRefRebuildDialog` | 删除 → 同上（delete 模式） |

### 5.2 视觉规格

- **一行排布**（`recon-item-action__buttons` flex 不变，`gap: var(--space-2)`）：主按钮在左、删除在右。
- **主按钮**：`type="primary"` + `plain`（沿用现有主按钮样式），文案 = 阶段动作名（与队列卡 `actionLabel` 同源，不另造词）。
- **删除按钮**：`type="danger"` + `plain`，`size` 与主按钮一致。**危险色的用法即语义**：执行区内 danger 令牌只允许出现在删除按钮与删除确认弹窗；主按钮绝不共享危险红。
- 两个按钮**都先经过各自的确认弹窗**（删除确认走 `mode="delete"` 既有弹窗，含确认词 + 预览；回补 / 补全 / 重建各有既有弹窗），执行区本身不做内联确认。
- 领句 `recon-item-action__lead` 显示队列项 summary（阶段聚合项的 summary 由 lane B 在 `reconQueue.ts` 产出；建议口径：reattach=「已找到可挂回的现存持仓」、fill=「缺标的代码，补齐后才能挂回」、rebuild=「持仓行被删了，要按流水重建才能找回」，均复用 `DANGLING_STATE_REASON` 的既有措辞，不写新句子）。
- **「处理」后进入单组执行区时**（§3.4 的返回路径），summary 换成该组的组级文案（沿用现 `danglingItem` 的 summary 构造），不要把阶段级的「共 N 条」带进单组视图——一个值只说一次。

### 5.3 「删除只在这里出现」如何被看懂（不靠文案解释）

1. **结构性排除**：删除入口在整个对账中心域 F 的渲染树里只有一个——执行区的删除按钮。队列卡、分诊卡、阶段面板标题、组卡、折叠明细里没有任何删除字样的按钮（§4 已删组卡按钮；队列卡本来就没有）。
2. **色彩即地图**：danger 红在域 F 界面上唯一的出现点是删除按钮（和它打开的确认弹窗）。用户学会一次「红 = 删除」，之后每屏都成立。
3. **不做说明句**：不在执行区写「删除功能只能在这里使用」之类的话——旁白是给删不掉的歧义兜底的，这里没有歧义。

### 5.4 顺带清理（`ReconItemAction.vue`）

- 删 `onRequestRebuild()` 与 `@request-rebuild` 监听（lane A 已从弹窗移除该 emit）；
- `DanglingRefRemediationDialog` 实例保留一份，`mode` 按 stage 动态给（`"enrich"` 或 `"delete"`），不再挂 `@request-rebuild`；
- `DanglingRefRebuildDialog` 实例只在 `rebuild` 阶段渲染路径中使用；
- `danglingStep` / `danglingNextStep` 的本地重算删除——阶段已在 `payload.stage` 里，组件不再调判据函数（判据只有一份原则）。

### 5.5 验收

- 三个阶段的主按钮名与 `DANGLING_ACTION_LABEL` 逐字一致；
- 执行区 always 恰好两个按钮（主 + 删除），无第三动作；`reattach`/`fill`/`rebuild` 三态切换只换主按钮文案与打开的弹窗；
- `grep -r "danger" frontend/src/views/asset/investment/reconcile-workbench` 中域 F 相关命中仅限删除按钮与其确认弹窗；
- 「删除」文案在导航层文件（`WorkbenchTaskCards` / `ReconQueueCard` / `DomainFDanglingRefs` / `DanglingRefGroupCard`）中出现次数为 0。

---

## 6. 跨文件文案清理清单（结构 spec §3.6 的落地）

以下句子**全部删除**（都是机制承诺或跨阶段指路句）：

| 文件 | 句子 | 类型 |
|---|---|---|
| `index.vue` | `按「现在能不能动手」排序。点一条待办，右侧会打开这条的来龙去脉、投资轨迹和处理动作。` | 旁白（§2） |
| `ReconQueueDetail.vue` | `下面的操作会写回账本；有二次确认的会先弹确认。` | 机制承诺 |
| `ReconQueueDetail.vue` | `对照上面的记录再决定怎么处理`（兜底 sub） | 旁白 |
| `DomainFDanglingRefs.vue` | `还有 N 条暂时不能自动处理：缺标的代码，或对应持仓已删除。先补全信息，再回来批量挂回。` | 跨阶段指路句 |
| `utils/enrichSteps.ts` | `这组流水的标的代码与交易日期都已齐全，没有可补的字段；要继续处理，可按流水重建持仓。`（`GUIDE_BY_REASON["这组没有可补的字段"]`） | 跨阶段指路句——漏斗后本弹窗内已无该按钮（lane A 已删），design.md 1264 明令「不得指向界面上不存在的按钮」。改为：`这组流水的标的代码与交易日期都已齐全，没有可补的字段。` |
| `constants/reconTasks.ts` | `repair.next` 中 `每次回补、补全、删除都记日志，可凭日志编号撤销` → 改为 `每次回补、补全都记日志` | `删除` 已不属于 repair 任务（归 rebuild 卡 / 执行区），别在修正数据卡上替别的任务代言 |

> ⚠️ `utils/enrichSteps.ts` 与 `constants/reconTasks.ts` 属 lane B 范围（utils/* / constants/*），由 lane B 一并处理；lane A 未动它们。

---

## 7. 整体验收清单

1. `pnpm typecheck` 零错误；
2. `node scripts/check_vue_size.mjs --mode fail --baseline` 无回涨（`index.vue` 基线 406；其余涉改文件 <400）；
3. `npx eslint` / `npx prettier --check` / `npx stylelint` 对每个改动文件通过；
4. 「先删，再重排」验收口径：上述每个区块**同一屏用户可见文本行数比改前少**（§2 队列头、§3 阶段面板、§4 组卡、§5 执行区逐块自查三问：换个人会这么说吗 / 标题后半段能删吗 / 行数降了吗）;
5. 结构 spec §4 的单测（`bucketByStage` / `danglingStageOf` / 和式不变量 / 删除只在执行区）全部落地并绿。
