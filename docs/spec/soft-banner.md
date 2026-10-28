# SoftBanner · 柔性提示条通用组件（#2716）

> 状态：设计定稿 + v1 实现（2026-10-28）。落点 `frontend/src/components/SoftBanner/index.vue`。

## 1. 背景与问题

「柔性提示条」（页面顶部非阻断式警示，行为约定见 reconciliation-framework-design：「中性信息色 Banner，严禁弹窗打断」）此前**没有通用组件**，两类做法并存、每个新页面再手写一份：

- **自绘 ×10**：DiscrepancyBanner、GhostDuplicateBanner、RealtimeWarningBanner、StatusBanner、ExploreConvBanner、Recognizer/Ocr UsageBanner、WorkbenchBanner、EaccountDraftBanner、import/ledgers 域页内零散 banner 块。每处自带一份几乎相同的 `flex + icon + border + radius` 样式，仅类名与色值不同；a11y 语义漂移（有的有 `role="alert"` 有的没有）、间距漂移（padding 12/14 vs 12/16）、关闭按钮三种形态。
- **el-alert 包壳 ×11**：HoldingGapBanner、PenetrationPanel、PositionStructurePanel、LoginFormPanel、BatchFix*、FundMatchDrawer、ImportErrorSummary、TransactionEditDialog 等。

不用 el-alert 的根因（tech-debt.md 既有结论）：EP 组件**内部颜色不受设计令牌控制**、对比度不达标（#1600 同类）；本仓 a11y 要求文字走 `-ink` 令牌、暗色走 `:root.dark` 同名覆盖，el-alert 内部样式够不着也覆盖不干净。**自绘本身正当，错在没有把第一个自绘抽象成通用组件。**

## 2. 定性结论（2026-10-28 逐一核实）

**「柔性提示条」家族 = 有底色/边框的非阻断警示条**。以下排除项不是该家族，**不做迁移**：

| 排除项 | 排除理由 |
|---|---|
| `StatusBanner` | 系统状态页**大卡**（bg-card 底、左 4px 色条、radius-lg、阴影），形态不同 |
| `ExploreConvBanner` | 匿名转化**营销卡**（品牌渐变底 + 大 CTA），不是警示 |
| `RecognizerUsageBanner` / `OcrUsageBanner` | 额度**纯文字行**（作者注释明确「无背景无边框、用空间代替色块、弱化存在感」） |
| el-alert ×11 | 按 issue 约定由 axe/对比度守卫判定，达标处不强求迁移；本轮不动 |
| import/ledgers 页内零散 banner 块 | **已迁 3 处**（#2724：`draft-banner` / `usage-banner` / `cash-binding-banner`），见 §5 |
| import/ledgers 剩余 3 处（`.conflict-banner` / `.soft-reconcile-banner` / `.orphan-banner`） | **形态属本家族，但超出组件现有表达力**：前者是 `brand-100` 品牌色底、无边框；中间者还带 `border-left: 3px` 语义色条（组件结构里没有这个位）。归一是**组件能力缺口**而非「忘了迁」，需先补档位并做设计裁决 → #2730，守卫里按 `path::selector` 精确冻结 |
| `AiImportModal` 的 `.recognition-hint` | 弹窗内**行内提示行**（`padding: 8px 12px`、无边框，紧凑是有意的），迁成提示条会撑大弹窗。**不迁**，但其 `strong` 原用 `--brand-700`（#e34f38 在 `--bg-soft` 上仅 3.41:1，文字级不达标）已就地改为 `--text-primary` |

**本轮迁移 5 处**：DiscrepancyBanner（warning）、GhostDuplicateBanner（danger）、WorkbenchBanner（info）、EaccountDraftBanner（info）、RealtimeWarningBanner（warning + dense）。

## 3. 组件 API

```ts
props = {
  /** 色族，默认 'info' */
  variant?: 'info' | 'warning' | 'danger'
  /** iconify 图标名（必传：图标语义由消费方定，组件不猜） */
  icon: string
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
- 明确**不做**的事：dismiss 状态管理（各消费方语义不同）、`success` variant（暂无消费方，首个 success banner 出现时补 `--color-success-20` 类令牌再启用）、title/count props（数字在句中的拼接用 slot 自由排版，组件提供 slotted 样式类）。

## 4. variant 色表（全令牌；暗色经 dark.scss 同名覆盖，两个半透明底令牌除外，见下）

| variant | 背景 | 边框 | 图标 | 正文默认色 |
|---|---|---|---|---|
| info | `--bg-soft` | `--border-default` | `--color-info-ink` | `--text-secondary` |
| warning | `--color-warning-20` | `--color-warning` | `--color-warning-ink` | `--text-primary` |
| danger | `--color-danger-10` | `--color-danger-30` | `--color-danger-ink` | `--text-primary` |

关键决策（2026-10-28 修正，源 #2726）：**danger 的正文走 `--text-primary`，不把文字染红**。

原裁决是「danger 的 ink 用 `--color-danger-ink`，不借 GhostDuplicateBanner 原来的 `--color-rise-ink`（语义误用），且 `#d4364a` **白底** 4.74:1 达标」——语义那半句成立，对比度那半句**不成立**：`--color-danger-10` 是 `rgba(212,54,74,.1)` 半透明底，正文并不在白底上。按令牌真值 alpha 合成重算（亮色）：

| 正文色 | danger-10 over `--bg-card` | over `--bg-page` | over `--bg-soft` |
|---|---|---|---|
| `--color-danger-ink` #d4364a（原） | 4.11:1 ❌ | 3.98:1 ❌ | 3.65:1 ❌ |
| `--color-rise-ink` #c0341f（它替掉的） | 4.85:1 ✅ | 4.70:1 ✅ | 4.31:1 ❌ |
| `--text-primary` #2d2a24（现） | 12.39:1 ✅ | 12.01:1 ✅ | 11.01:1 ✅ |

即：原裁决在**语义**上纠正了借用，却在**对比度**上退了一步（4.70 → 3.98）。改为 `--text-primary` 后，危险语义由**图标**（`--color-danger-ink`，图形门槛 3:1，实测 4.11/3.98 达标）+ 边框 + 底色承担，与 `warning` 档同一做法——两档都不靠染色文字表达语义。

**口径（必须记住）**：`--color-warning-20` / `--color-danger-10` 是半透明色，**引用任何「白底 X:1 达标」的数字前必须先合成**，否则结论会偏 0.5~0.9。暗色侧这两个底令牌**未在 `dark.scss` 覆盖**（沿用亮色 rgba），但正文 `--text-primary` 合成后为 10.63 / 11.71 / 9.71，图标 `--color-danger-ink` 为 5.04 / 5.58 / 4.57，均达标。

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

## 6. 验证口径

- 组件为纯壳（无派生逻辑），本仓 vitest 为 node 环境无 DOM（无 @vue/test-utils，见 quickTypeModel.spec.ts 头注约定），**不写 mount 单测**；行为由消费方既有 e2e 覆盖：`discrepancy-banner-slim.spec.ts`（recon-banner 系列）、`eaccount-draft.spec.ts` + `import-draft.spec.ts`（draft-banner）、`reconcile-workbench-head.spec.ts`（workbench-banner）——类名全保留，断言零改动。
- 门禁：vue-tsc / eslint / prettier / 页面规模门禁 / CSS 令牌守卫。
- 对比度复核口径（#2726 起）：半透明底令牌（`--color-warning-20` / `--color-danger-10` / `--color-danger-30`）**不得**直接拿「白底 X:1」的数字下结论——必须 `over(fg, alpha, 底层)` 合成后再算 WCAG 比，且底层取 `--bg-card` / `--bg-page` / `--bg-soft` 三者中**最差**的那个。当前实测值见 §4 表。

## 7. 后续批次

1. el-alert ×11 的 axe 实测与按需替换 —— **已转 #2723**（未做：需 dev server + 会话注入跑 axe，且 `frontend` 无 axe 依赖）；
2. import/ledgers 页内零散 banner 块收敛 —— **已完成 3 处**（#2724，2026-10-28）：`draft-banner` / `usage-banner` / `cash-binding-banner` 全部改走 SoftBanner，本域不再有自绘 banner 壳；剩余 3 处（`.conflict-banner` / `.soft-reconcile-banner` / `.orphan-banner`）属**组件能力缺口**（brand 档 / 左语义条），转 #2730；
3. 防回归：新自绘 banner 样式拦截 —— **已落地**（#2725）：`scripts/guard_soft_banner.py`，接进 `ci.yml` 的 `layout_guard` job 并登记 `RULE_REGISTRY`。
   - **判据**：样式选择器含 `banner` + **同一规则块内**有 `display: flex` + 真实背景或边框（`none`/`transparent`/`0` 不算）。
     迁移后的消费方保留 `class="recon-banner"` 这类 e2e 锚点类名**不会**被判红——它们样式里只剩排版声明。
   - **误判面**（全仓 502 个 `.vue`/`.scss` 实测）：命中 6 处，其中 2 处是 §2 已定性排除的营销卡 / 状态大卡（`ALLOWLIST` 逐条登记理由），3 处是 #2730 的待归一块（`BASELINE` 按 `path::selector` 精确冻结），**真阳性 3 / 假阳性 2，登记后阻断 0**。
   - **已知不覆盖**：壳与配色**分块写**的（`.soft-banner { display:flex }` + `.soft-banner--info { background }`）不命中，含 SoftBanner 自身；不叫 `banner` 的块（`.notice-bar` 等）不命中；模板内联 `:style` 与 `el-alert` 包壳不参与。理由见脚本 docstring——判据宁窄勿宽，误判即弃用。
   - **豁免**：`ALLOWLIST`（永久，逐条理由）/ `BASELINE`（待清，精确到块）/ 行内 `banner-guard-allow`（本行或相邻行）。BASELINE 里出现**已无对应命中的条目**会报红（防基线僵化失效）。
