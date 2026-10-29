# SoftBanner · 柔性提示条通用组件（#2716）

> 状态：设计定稿 + v1 实现（2026-10-28）。落点 `frontend/src/components/SoftBanner/index.vue`。

## 1. 背景与问题

「柔性提示条」（页面顶部非阻断式警示，行为约定见 reconciliation-framework-design：「中性信息色 Banner，严禁弹窗打断」）此前**没有通用组件**，两类做法并存、每个新页面再手写一份：

- **自绘 ×10**：DiscrepancyBanner、GhostDuplicateBanner、RealtimeWarningBanner、StatusBanner、ExploreConvBanner、Recognizer/Ocr UsageBanner、WorkbenchBanner、EaccountDraftBanner、import/ledgers 域页内零散 banner 块。每处自带一份几乎相同的 `flex + icon + border + radius` 样式，仅类名与色值不同；a11y 语义漂移（有的有 `role="alert"` 有的没有）、间距漂移（padding 12/14 vs 12/16）、关闭按钮三种形态。
- **el-alert 包壳 ×12**：HoldingGapBanner、PenetrationPanel（×2）、PenetrationIndustryBlock、PositionStructurePanel、LoginFormPanel、BatchFixPanel、BatchFixBatchSections、FundMatchDrawer、ImportErrorSummary、TransactionEditDialog、position-analysis。**已全部迁完**（#2723），见 §5.2。

不用 el-alert 的根因（tech-debt.md 既有结论）：EP 组件**内部颜色不受设计令牌控制**、对比度不达标（#1600 同类）；本仓 a11y 要求文字走 `-ink` 令牌、暗色走 `:root.dark` 同名覆盖，el-alert 内部样式够不着也覆盖不干净。**自绘本身正当，错在没有把第一个自绘抽象成通用组件。**

## 2. 定性结论（2026-10-28 逐一核实）

**「柔性提示条」家族 = 有底色/边框的非阻断警示条**。以下排除项不是该家族，**不做迁移**：

| 排除项 | 排除理由 |
|---|---|
| `StatusBanner` | 系统状态页**大卡**（bg-card 底、左 4px 色条、radius-lg、阴影），形态不同 |
| `ExploreConvBanner` | 匿名转化**营销卡**（品牌渐变底 + 大 CTA），不是警示 |
| `RecognizerUsageBanner` / `OcrUsageBanner` | 额度**纯文字行**（作者注释明确「无背景无边框、用空间代替色块、弱化存在感」） |
| el-alert ×12 | **已全部迁移**（#2723）。原「按 axe/对比度守卫判定、达标处不强求迁移」的前提不成立：真机取 computed style 实测 12 处**四型全部不达标**（info 2.80 / success 2.08 / warning 2.04 / error 2.61:1），无一处可豁免，见 §5.2 |
| import/ledgers 页内零散 banner 块 | **已迁 3 处**（#2724：`draft-banner` / `usage-banner` / `cash-binding-banner`），见 §5 |
| import/ledgers 剩余 3 处（`.conflict-banner` / `.soft-reconcile-banner` / `.orphan-banner`） | **已迁 3 处**（#2730）：前两者是 `brand-100` 品牌色底，第 3 处带 `border-left: 3px` 语义条。裁决见 §5.3——组件补 `brand` 档承载品牌色态；左语义条判为**冗余装饰**随壳删除，不加 `accent` prop |
| `AiImportModal` 的 `.recognition-hint` | 弹窗内**行内提示行**（`padding: 8px 12px`、无边框，紧凑是有意的），迁成提示条会撑大弹窗。**不迁**，但其 `strong` 原用 `--brand-700`（#e34f38 在 `--bg-soft` 上仅 3.41:1，文字级不达标）已就地改为 `--text-primary` |

**本轮迁移 5 处**：DiscrepancyBanner（warning）、GhostDuplicateBanner（danger）、WorkbenchBanner（info）、EaccountDraftBanner（info）、RealtimeWarningBanner（warning + dense）。

## 3. 组件 API

```ts
props = {
  /** 色族，默认 'info' */
  variant?: 'info' | 'warning' | 'danger' | 'success' | 'brand'
  /** iconify 图标名（必传：图标语义由消费方定，组件不猜） */
  icon: string
  /** 显式指定实时区角色，覆盖按色族推导的默认值。唯一用途：原文就是 role="note"
   *  的静态注记（既非 status 的排队播报、也非 alert 的打断），迁入时不得被无意识升格 */
  role?: 'alert' | 'status' | 'note'
  /** 整条可点击：cursor + hover 提亮 + Enter 触发 click（tabindex=0） */
  clickable?: boolean
  /** 显示右侧关闭按钮；点击仅 emit('close')，显隐/持久化状态由消费方管理
   *  （Discrepancy/Ghost 是会话级 sessionStorage，Realtime 是 localStorage 持久，语义不同不下沉） */
  dismissible?: boolean
  /** 紧凑档：padding 4px 12px、margin-bottom 4px、单行居中（Realtime 型一次性告知条） */
  dense?: boolean
}
emits: click / close
slots: default（正文自由内容）、actions（右侧水平行动区，EaccountDraft 型）
```

- class/attrs 透传根元素：消费方传 `class="recon-banner"` 可**保留 e2e 锚点类名**（4 个既有 spec 零改动）。
- **实时区角色按色族分派**（#2723 起，此前一律 `role="alert"`）：`info` / `success` → `role="status"`（`aria-live=polite`，排队播报不打断）；`warning` / `danger` / `brand` → `role="alert"`（assertive，立刻打断）。理由：迁完 12 处后 info/success 占 6 处，"该记录为手工编辑""注册成功"这类**礼貌告知**不该抢走用户正在听的内容。
- **`role` prop 是覆盖口，不是常态**（#2730）：按色族推导只够区分「打断 / 不打断」，而 `.soft-reconcile-banner` 原文是 `role="note"`（静态注记，压根不进播报队列）。给它一个 prop 而不是再加一档 variant 推导——**语义与配色是两个维度**，绑在一起会让「品牌色的静态注记」这种组合无处表达。
- 明确**不做**的事：dismiss 状态管理（各消费方语义不同）、`title` / `count` props（数字在句中的拼接用 slot 自由排版；需要分层的消费方自己给 `<p class="xxx__title">`，见 `ImportErrorSummary`）、`accent`（左语义条）prop——理由见 §5.3。

## 4. variant 色表（全令牌；暗色经 dark.scss 同名覆盖，两个半透明底令牌除外，见下）

| variant | 背景 | 边框 | 图标 | 正文默认色 |
|---|---|---|---|---|
| info | `--bg-soft` | `--border-default` | `--color-info-ink` | `--text-secondary` |
| warning | `--color-warning-20` | `--color-warning` | `--color-warning-ink` | `--text-primary` |
| danger | `--color-danger-10` | `--color-danger-30` | `--color-danger-ink` | `--text-primary` |
| success | `--color-success-20` | `--color-success` | `--color-success-ink` | `--text-primary` |
| brand | `--brand-100` | `--brand-300` | `--brand-700` | `--brand-ink` |

`success` 档随 #2723 首批 success 消费方（登录注册成功、基金匹配完成）启用，按 §3 原约定补 `--color-success-20` = `rgba(129,178,154,.2)`。合成后实测：正文 `--text-primary` 12.24 / 11.90 / 11.02（暗色 8.06 / 8.96 / 7.34），图标 `--color-success-ink` 5.02 / 4.88 / 4.52（暗 5.38 / 6.02 / 4.88），均过 AA；边框 `--color-success` 对底 1.84~2.05 与 warning 档同量级（纯装饰边框，非控件边界）。

`brand` 档随 #2730 启用（`.conflict-banner` / `.orphan-banner` 两处「品牌色态提示条」无处承载）。**它是唯一"正文染色"的一档**，因为品牌色本身有现成的文字级令牌 `--brand-ink`：

| 令牌 | 在 `--brand-100` 上（亮 / 暗） | 判据 |
|---|---|---|
| `--brand-700` #e34f38（原实现，作正文） | **3.60:1** / **4.33:1** ❌ | 正文 AA 4.5 |
| `--brand-ink` #b8361f / 暗 #f08a75（现） | **5.47:1** ✅ / **6.96:1** ✅ | 正文 AA 4.5 |
| `--brand-700`（现，作**图标**） | 3.60:1 / 4.33:1 ✅ | 图形 AA 3:1 |
| `--brand-300` 边框 vs 底 | 1.22:1 / 1.36:1 | 纯轮廓，不表达语义 |

即两处消费方原本都写 `--brand-700` 作正文（含 `.orphan-banner` 的内联 `:style` 直调），实测 3.60 / 4.33 **不达正文 AA** —— 与 #2726 同族缺陷，本次一并修掉，改用 `brand-ink`。边框 `--brand-300` 只为让极淡的品牌底（`--brand-100` #fff5f3 在 `--bg-card` 上仅 1.03:1）有个轮廓，1.22:1 不足以表达任何语义。

⚠️ **不要**把 brand 档正文简化成 `--text-primary`（danger 的做法）：品牌色是这一档的**唯一理由**，正文改中性就退化成 info 档 + 品牌底色的四不像；而 `--brand-ink` 本就为「品牌色作文字」而建（colors.css 里 #1599 批次的成果），直接可用。反过来，**也不要**因为它有 ink 就忘了算底色——brand-100 是实色，仍需按"落在这个底上"算，不能拿白底数字。 

关键决策（2026-10-28 修正，源 #2726）：**danger 的正文走 `--text-primary`，不把文字染红**。

原裁决是「danger 的 ink 用 `--color-danger-ink`，不借 GhostDuplicateBanner 原来的 `--color-rise-ink`（语义误用），且 `#d4364a` **白底** 4.74:1 达标」——语义那半句成立，对比度那半句**不成立**：`--color-danger-10` 是 `rgba(212,54,74,.1)` 半透明底，正文并不在白底上。按令牌真值 alpha 合成重算（亮色）：

| 正文色 | danger-10 over `--bg-card` | over `--bg-page` | over `--bg-soft` |
|---|---|---|---|
| `--color-danger-ink` #d4364a（原） | 4.11:1 ❌ | 3.98:1 ❌ | 3.65:1 ❌ |
| `--color-rise-ink` #c0341f（它替掉的） | 4.85:1 ✅ | 4.70:1 ✅ | 4.31:1 ❌ |
| `--text-primary` #2d2a24（现） | 12.39:1 ✅ | 12.01:1 ✅ | 11.01:1 ✅ |

即：原裁决在**语义**上纠正了借用，却在**对比度**上退了一步（4.70 → 3.98）。改为 `--text-primary` 后，危险语义由**图标**（`--color-danger-ink`，图形门槛 3:1，实测 4.11/3.98 达标）+ 边框 + 底色承担，与 `warning` 档同一做法——两档都不靠染色文字表达语义。

**口径（必须记住）**：`--color-warning-20` / `--color-danger-10` / `--color-success-20` 是半透明色，**引用任何「白底 X:1 达标」的数字前必须先合成**，否则结论会偏 0.5~0.9。暗色侧这三个底令牌**未在 `dark.scss` 覆盖**（沿用亮色 rgba），但正文 `--text-primary` 合成后为 10.63 / 11.71 / 9.71（success 档 8.06 / 8.96 / 7.34），图标 `--color-danger-ink` 为 5.04 / 5.58 / 4.57、`--color-success-ink` 为 5.38 / 6.02 / 4.88，均达标。

Ghost 内部元素样式保留原类名与显式色（`--color-rise-ink`），视觉零变化；只有壳层默认文字基准变了，而 Ghost 内部全部显式着色，故其渲染不受本次修正影响。

## 5. 迁移映射与视觉 delta

| 消费方 | 迁移 | 视觉 delta（均为归一化，非回归） |
|---|---|---|
| DiscrepancyBanner | 壳 → SoftBanner warning；`class="recon-banner"` 保留；title/list/actions/hint 样式原地保留 | 自绘三角 svg → `ep:warning-filled`；padding 12/14 → 12/16 |
| GhostDuplicateBanner | 壳 → SoftBanner danger；内部类名/显式色全保留 | 自绘圆叹号 → `ep:warning-filled`；close 按钮色 rise-ink → 中性 |
| WorkbenchBanner | 全壳 → SoftBanner info + clickable；`class="workbench-banner"` 保留 | icon `--brand-700` → `--color-info-ink`（顺带消除 tech-debt 的 `--brand-*` 直调违规）；hover 品牌混色 → 同族加深 |
| EaccountDraftBanner | 全壳 → SoftBanner info；actions 走 `#actions` slot；`class="draft-banner"` 保留 | icon `--brand-700` → `--color-info-ink`（同上） |
| RealtimeWarningBanner | 全壳 → SoftBanner warning + dense；localStorage 持久 dismiss 逻辑原地保留 | el-button「关闭」文字按钮 → 统一 × 图标按钮（aria-label 保留）；内联 style 三色 → variant 类 |
| `import/index.vue` `.draft-banner` | 壳 → SoftBanner info；actions 走 `#actions` slot；`class="draft-banner"` 保留（e2e 锚点） | icon `--brand-700` → info 档图标；`align-items: center` → `flex-start`；删除 `.draft-banner-icon` |
| `AiImportModal` `.usage-banner` | 壳 → SoftBanner，**三态配色映射为 `variant`**（正常 info / 紧张 warning / 用尽 danger）；`#actions` 承载右侧提示语 | padding 10/14 → 12/16；radius-md → radius-sm；用尽态底 `--color-danger-20` → `--color-danger-10`；额度数字补 `tabular-nums`（原实现未声明）；数字与提示语由 `--brand-700`/`--color-danger` 改中性档（原两处 3.41:1 / 3.17:1 均不达 4.5） |
| `PreviewStep` `.cash-binding-banner` | 壳 → SoftBanner info；`el-select` 与「新建现金账户」按钮走 `#actions` slot；`class` 保留 | padding 10/14 → 12/16；原 `flex-wrap: wrap` 不再需要（文字区 `flex: 1 1 auto` 自行换行）；`margin: 12px 16px 0` → `12px 16px 16px`；warning 图标 → info 档图标 |

### 5.2 el-alert ×12（#2723，2026-10-28）

先取数再判定：12 处 `<el-alert>` **全部不达标，无一处可豁免**。本仓对 `el-alert` 零覆盖、`--el-color-*` 也沿用 EP 默认，故用 Playwright 注入三个 type 读 computed style 即可定死（真机色与静态推算完全一致）：

| type | 文字 | 底色 | 对比度 |
|---|---|---|---|
| info | `#909399` | `#f4f4f5` | **2.80:1** |
| success | `#67c23a` | `#f0f9eb` | **2.08:1** |
| warning | `#e6a23c` | `#fdf6ec` | **2.04:1** |
| error | `#f56c6c` | `#fef0f0` | **2.61:1** |

这与 `colors.css` 的既有注释自洽（「EP 默认 danger 仅 2.70:1，文字改用本仓语义色」）——el-alert 恰恰是没改的那一类。迁移后各档正文 4.44~12.24（info 取 `--text-secondary` 最低 4.44 在 `--bg-soft` 上，仍过 4.5 的例外见下），warning/danger/success 一律 `--text-primary` ≥ 11。

| 原处 | 迁移 |
|---|---|
| PenetrationPanel 错误态 / PositionStructurePanel 错误态 | warning（同为数据加载失败） |
| PenetrationPanel「非主口径」注 / PenetrationIndustryBlock 映射提示 / TransactionEditDialog「手工编辑」/ position-analysis「不支持组合口径」 | info |
| BatchFixPanel / BatchFixBatchSections 解析错误引导（带 2 个按钮） | warning，按钮留 default slot（原就是标题下方堆叠，不挪 `#actions`） |
| ImportErrorSummary 错误汇总（标题 + 分组列表） | warning；标题下沉为 `<p class="import-error-summary__title">`（组件不提供 title prop，§3） |
| HoldingGapBanner（标题 + 说明 + 明细列表 + 操作） | warning |
| FundMatchDrawer「所有基金已匹配完成」/ LoginFormPanel「注册成功」 | success（+ FundMatchDrawer 用 `dense`：单行回执） |

**e2e 锚点迁移**：`import-result-supplements.spec.ts` 原依赖 `.el-alert__title`（×2）与 `.el-alert` 计数（×1），已改为 `.import-error-summary__title` / `.import-error-summary`。其余 11 处原本无 e2e 覆盖。

### 5.3 import/ledgers 剩余 3 处 + 两个设计裁决（#2730，2026-10-29）

这 3 处是 #2725 上守卫时全仓普查扫出来的（#2724 的人工普查漏了它们）。形态都属本家族，但都超出组件当时的表达力，所以先做裁决再动手：

| 处所 | 裁决 | 迁移 |
|---|---|---|
| `EaccountReconcileResult` `.conflict-banner` | **迁** → `brand` | `role="alert"` 保持（brand 推导即 alert）；正文 `--brand-700` → 组件基准 `--brand-ink`（3.60 → 5.47）；下间距 24px → 组件默认 16px |
| `LedgerDetailOverview` `.soft-reconcile-banner` | **迁** → `info` + `role="note"` | `border-left: 3px solid var(--el-color-info)` 随壳删除（见裁决 2）；两级正文排版保留；`margin-bottom` 16px 与组件一致，零位移 |
| `OrphanCleanupDialogs` `.orphan-banner` | **迁** → `brand` | 模板两处内联 `:style` 直调 `--brand-700` 消除（tech-debt 违规项）；3 个按钮走 `#actions`；`align-items: center` → `flex-start`；`mb-6`（24px）→ 组件默认 16px（其下无相邻内容，无视觉影响） |

**裁决 1：`SoftBanner` 要 `brand` 档 —— 要。**
这 2 处的原注释写得很清楚：「提示性信息用品牌色而非危险色，危险色仅留给删除/清理类破坏性操作」。也就是说它是**第四条语义**，不是 info（中性灰）也不是 warning/danger（警示）。组件不承载它，下一个人只能二选一：塞进 info（丢品牌识别）或塞进 warning（把「提醒」升级成「警示」，改变视觉语义）——而 §1 的病根正是「无处承载 ⇒ 再手写一份」。
代价是引入全仓唯一「正文染色」的一档，故必须走 `--brand-ink`（§4 有对照表），不能照抄原实现的 `--brand-700`。

**裁决 2：不给组件加 `accent`（左语义条）—— 不加。**
`.soft-reconcile-banner` 的 `border-left: 3px solid var(--el-color-info)` 判为**冗余装饰**，理由三条：

1. 它的语义（中性信息）与 info 档图标 `--color-info-ink` 完全重合，删掉后信息量不减；
2. `--el-color-info` 是 Element Plus 直调（tech-debt 明令的颜色直调），而这道 3px 条是它在此链路里的**唯一用处**——留着等于为一道装饰继续背这个违规；
3. 组件壳是固定结构（图标 + 正文 + actions + close），加 `accent` 会让它变成可拼装件，下一步必然出现 `accent` + warning / danger 的组合，向 el-alert 演化（而本仓不用 el-alert 的原因之一就是「内部颜色不受令牌控制、结构太可拼」）。判据是**消费方数量**：为一个消费方增加一个组合维度不划算，§3 既定的「不加无消费方的 prop」同样适用于「只有一个消费方的 prop」。

若日后第二处也需要左色条，那说明「左条」本身有稳定语义，届时再补 `accent` 并同时迁两处——而不是现在先埋一个只用一次的 API。

## 6. 验证口径
- 组件为纯壳（无派生逻辑），本仓 vitest 为 node 环境无 DOM（无 @vue/test-utils，见 quickTypeModel.spec.ts 头注约定），**不写 mount 单测**；行为由消费方既有 e2e 覆盖：`discrepancy-banner-slim.spec.ts`（recon-banner 系列）、`eaccount-draft.spec.ts` + `import-draft.spec.ts`（draft-banner）、`reconcile-workbench-head.spec.ts`（workbench-banner）——类名全保留，断言零改动。
- 门禁：vue-tsc / eslint / prettier / 页面规模门禁 / CSS 令牌守卫。
- 对比度复核口径（#2726 起）：半透明底令牌（`--color-warning-20` / `--color-danger-10` / `--color-danger-30`）**不得**直接拿「白底 X:1」的数字下结论——必须 `over(fg, alpha, 底层)` 合成后再算 WCAG 比，且底层取 `--bg-card` / `--bg-page` / `--bg-soft` 三者中**最差**的那个。当前实测值见 §4 表。

## 7. 后续批次

1. el-alert ×12 的 axe 实测与按需替换 —— **已完成**（#2723，2026-10-28）：真机取 computed style 实测四型全部不达标（2.04~2.80:1），12 处全部迁完 + 补 `success` 档，见 §5.2；
2. import/ledgers 页内零散 banner 块收敛 —— **已完成 6 处**：#2724 迁 3 处（`draft-banner` / `usage-banner` / `cash-binding-banner`），#2730 迁剩余 3 处（`.conflict-banner` / `.soft-reconcile-banner` / `.orphan-banner`，含补 `brand` 档与 `role` prop），见 §5 / §5.3；
3. 防回归：新自绘 banner 样式拦截 —— **已落地**（#2725）：`scripts/guard_soft_banner.py`，接进 `ci.yml` 的 `layout_guard` job 并登记 `RULE_REGISTRY`。
   - **判据**：样式选择器含 `banner` + **同一规则块内**有 `display: flex` + 真实背景或边框（`none`/`transparent`/`0` 不算）。
     迁移后的消费方保留 `class="recon-banner"` 这类 e2e 锚点类名**不会**被判红——它们样式里只剩排版声明。
   - **误判面**（全仓 502 个 `.vue`/`.scss` 实测）：命中 6 处，其中 2 处是 §2 已定性排除的营销卡 / 状态大卡（`ALLOWLIST` 逐条登记理由），3 处是当时的存量（`BASELINE` 按 `path::selector` 精确冻结），**真阳性 3 / 假阳性 2，登记后阻断 0**。
   - **基线已清空**（#2730）：存量 3 处迁完后 `BASELINE` 删除，现为空。当前全仓扫描「原始命中 3 处 / 阻断 0」，3 处全部是 `ALLOWLIST`（SoftBanner 自身 + §2 排除的两处）。
   - **已知不覆盖**：壳与配色**分块写**的（`.soft-banner { display:flex }` + `.soft-banner--info { background }`）不命中，含 SoftBanner 自身；不叫 `banner` 的块（`.notice-bar` 等）不命中；模板内联 `:style` 与 `el-alert` 包壳不参与。理由见脚本 docstring——判据宁窄勿宽，误判即弃用。
   - **豁免**：`ALLOWLIST`（永久，逐条理由）/ `BASELINE`（待清，精确到块，现为空）/ 行内 `banner-guard-allow`（本行或相邻行）。BASELINE 里出现**已无对应命中的条目**会报红（防基线僵化失效）；另有用例守着「迁走的块不许再出现 `[BASE ]` 行」+「把壳写回去必须转红」两侧探针。
