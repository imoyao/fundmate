# 自选页重新设计方案（2026-08-14）

> 性质：内部备忘（`docs/working-notes/` 屏蔽出构建，不对外）
> 触发：用户对自选页整体评价「样式很奇怪，太粗糙，不像一个产品」，要求对齐参考产品（基估宝 jigu）的精致感，重新设计
> 范围：**只出方案与线框，不改任何业务代码**。实施须经用户确认后另行进行
> 基线：`frontend/design.md`（亮色 v2.3.3）、`frontend/design.dark.md`（暗色 v1.5）、全站 `el-table` 基线 `src/style/el-table.css`
> 关联：`watchlist-table-redesign-2026-08-13.md`（列信息密度，本方案不重复其列集合讨论，只做布局与视觉）

---

## 0. 结论先行

1. **「粗糙感」的三个硬根因**（均有 file:line 证据）：① 左右分栏布局把表格压到 ~570px 宽，而固定列宽合计 1065px，表格必然横向滚动、第一列被挤爆；② 第一列在 ProductDisplay 之外还塞了标签 chips / +N / 加标签按钮，产品名称观感与其他页面不一致；③ 页面存在**三套「全部/场内/场外」筛选**（顶部 el-segmented、表格上方 venue 胶囊、左侧系统分组），语义重复、形态各异的控件堆在一起。
2. **推荐布局**：放弃「左侧分组栏 + 右侧表格」横排，改为**「顶部横向分组 tab + 全宽表格」**（方案 B，见 §3.2）。表格获得完整宽度，分组切换仍是高频操作的一键直达，且与基估宝「列表为主、分组为附属」的产品形态对齐。
3. **保留备选**：若用户希望保守，可先做「左侧窄栏」（方案 A，纯 CSS 低风险）过渡，但只能缓解、不能根治横向占用问题。
4. **合规问题**：现状存在 4 处硬编码色值 / 直接调用 `--brand-*` 的写法（§2.6），本次重设计一并修正。

---

## 1. 现状诊断（带证据）

### 1.1 布局：左右分栏挤压表格（用户反馈 2 的根因）

`index.vue:118` 主区域为 `<div class="flex gap-6 flex-wrap">`：

- 左侧分组卡片 `:120-127`：`w-56 shrink-0 rounded-2xl p-6` → **固定 224px 宽 + 24px 内边距**，内容区实际只有 176px；
- 右侧表格卡片 `:239`：`flex-1 min-w-[600px] rounded-2xl p-6`。

列宽需求核算（`index.vue:429-709`）：

| 列 | 行号 | 宽度 |
|---|---|---|
| 标记列（置顶/关注） | :435 | 50 |
| 代码/名称 | :457 | min 200 |
| 添加自选日 | :505 | 115 |
| 最新价 | :516 | 110 |
| 涨跌幅 | :542 | 100 |
| 持有数量 | :562 | 110 |
| 持仓市值 | :584 | 120 |
| 添加后涨幅 | :601 | 120 |
| 持仓收益 | :622 | 120 |
| 收益比 | :636 | 100 |
| 操作（fixed right） | :648 | 120 |

固定列合计 **1065px**（不含第一列）。可用宽度：lg（961px）断点下 ≈ 961 − 96（页面边距 p-6×2）− 224（左栏）− 24（gap）− 48（表格卡 padding）= **~569px**；即使 2xl（1400px）全宽也只有 ~976px。**任何断点下表格都放不下全部列 → 必然横向滚动，第一列被压缩到名存实亡**。这就是用户说的「表格宽度特别窄、有效信息显示空间不足」，也是「第一列宽度明显不对」（反馈 1b）的直接原因。

### 1.2 产品名称显示与其他页面不一致（反馈 1a）

`ProductDisplay` 组件本身全站一致（watchlist / explore / inventory / ledgers 均引用同一组件），差异出在**使用方式**：

- 自选页 `index.vue:459-499`：第一列 = `ProductDisplay` + `AssetTypeBadge`（场外）+ 标签 chips（最多 2 个）+ `+N` 计数 + 加标签按钮，全部挤在 200px 列里，名称被换行/截断；
- 探市页 `explore/index.vue:330-338`：`min-width="180"`，**只有干净的 ProductDisplay**；
- 资产明细页 `inventory/index.vue:245-256`：`min-width="150"` + `show-overflow-tooltip`，也是纯 ProductDisplay。

结论：不是组件不同，而是**自选页把「名称 + 标签 + 操作」全堆进一列且列宽不足**，导致名称呈现与其他页面明显不同。

### 1.3 顶部筛选 tab 与分组卡片不对齐（反馈 1c）

- 顶部 `el-segmented`（`index.vue:9-13`，全部/场内/场外）宽度由内容撑开（约 200px），而左侧分组卡片固定 224px（`:121`），两者同处页面左上但右边缘不齐；
- 更根本的是**三套「全部/场内/场外」并存**：
  1. 顶部 el-segmented 视图切换（`:9-13`，`currentView`，`:1442-1443` 会强制 venue）；
  2. 表格上方 venue 筛选胶囊「全部/股票/基金」（`:344-372`，`VENUE_FILTER_OPTIONS` `:1373-1377`）；
  3. 左侧系统分组「全部 / 场内资产 / 场外基金」（`:1133-1166` 的 `exchange` / `otc` 两项）。

同一语义三个入口、三种形态（分段控制器 / 胶囊 / 列表项），是「不像一个产品」的重要来源。

### 1.4 分组名称无长度保护（反馈 3b）

- 后端约束：`models.py:46` `name = Column(String(50))`、`schemas.py:66` `max_length=50` → 分组名最长 50 字符（约 25 个汉字）；
- 前端 `index.vue:187` 直接渲染 `{{ group.label }}`，**无 ellipsis / title 截断**；分组项 `:140` 在 176px 内容区内还要放色点 + 名称 + 数量 + hover 编辑/删除按钮，长名称直接撑破换行。
- 分组栏整体 `w-56`（224px）对「导航型」列表过宽，且 `p-6`（`--space-standard` 24px）用于窄栏浪费横向空间（反馈 3a）。

### 1.5 其他粗糙点

- 分组卡片与表格卡片都是 `rounded-2xl`（`--radius-lg` 16px）+ `--shadow-raised` + `--border-light`，两个大卡片并排造成「两张纸叠放」的割裂感，而非一个整体工作区；
- 分组项选中态 `:144-147` 用 `--brand-100` 底 + `--brand-700` 字（合规范），但**无 hover 过渡背景**（`:148-151` 未选中态 hover 无样式），点击感生硬；
- 表格行 hover 基线在 `el-table.css`（`--bg-soft`），但操作列按钮 `:2262-2269` 用 `opacity 0 → 1` 浮现，与分组栏 hover 按钮（`:213` 用 `w-0 → w-auto` 撑开）是**两套不同的浮现机制**，观感不统一。

### 1.6 与 design.md 的冲突点（本次必须修正）

| 位置 | 问题 | 规范依据 |
|---|---|---|
| `index.vue:440` `text-yellow-500`、`:447` `text-purple-400` | 置顶/特别关注图标硬编码 Tailwind 色，绕过设计令牌 | design.md「禁止硬编码 hex 色值」 |
| `index.vue:963` `color: '#333333'` | 标签编辑弹窗硬编码 hex | 同上 |
| `index.vue:63/:406/:816/:997` `'#C5C9B8'` / `'#B6B09C'` | 分组/标签色 fallback 硬编码 hex（数据色可保留，但 fallback 应改用 `--text-tertiary` 或注释说明） | 同上（数据色属例外，需显式注释） |
| `index.vue:351` `bg-[var(--brand-100)]` 等 | venue 筛选选中态直接调用 `--brand-*` 系列 | design.md「业务代码禁止直接调用 `--brand-*`，涨跌必须走 `--color-rise/--color-fall`」。注：选中态非涨跌语义，可保留软按钮写法，但应收敛为统一类名 |
| `index.vue:341` `border-[var(--border-light)]` | arbitrary value 写法 | 非违规，但建议统一为 token 类 |

---

## 2. 重新设计方案

### 2.1 设计目标（对齐基估宝质感）

- **信息密度优先**：表格是主角，占据 ≥ 90% 横向空间；分组是附属导航，不抢表格宽度；
- **一套筛选**：全部/场内/场外只保留一个入口，消除三套并存；
- **一致的名称呈现**：产品名称全站同构（两行式：名称 + 代码/类型），标签与操作从名称列剥离或降权；
- **克制的卡片语言**：页面主体用「一个工作区卡片」，内部用分割线分区，替代「两张并列大卡片」；
- 所有视觉一律走 design token（亮/暗自动适配）。

### 2.2 候选布局（3 选 1）

#### 方案 A：左侧窄栏（低风险，缓解不根治）

- 左栏 `w-56`（224px）→ `w-40`（160px）或内容自适应 `min-w-[120px] max-w-[180px]`；内边距 `p-6` → `p-3`（`--space-3`）；
- 分组项名称 `ellipsis` + `title`；数量徽章与 hover 按钮压缩为单图标；
- 表格获得 ~64px 增量，**仍不足以放下 1065px 固定列**。

| 优点 | 缺点 |
|---|---|
| 纯 CSS 改动，零模板风险 | 只缓解 ~64px，治标不治本 |
| 保留「分组 + 表格」既有心智 | 两张卡片并排的割裂感仍在 |

#### 方案 B：顶部横向分组 tab + 全宽表格（**推荐**）

- 删除左侧分组卡片，分组改为表格卡片**顶部的横向胶囊 tab 行**（可横向滚动，`overflow-x-auto`）；
- 系统分组 7 项 + 自定义分组全部进 tab 行；tab 高度 32px（`--text-label` 13px），选中态 `--brand-100` 底 + `--brand-700` 字 + `--brand-400` 边框（软按钮规范），未选中 `--text-secondary` + hover `--bg-hover`；
- 「全部/场内/场外」视图切换收敛为**表格卡片右上角的 el-segmented**（与分组 tab 不再追求同宽，改为「tab 行左对齐、segmented 右对齐」的清晰分工）；
- 表格获得 lg 下 ~817px、2xl 下 ~1224px 可用宽度，配合列宽微调（§2.3）在 2xl 下可完整放下全部列，lg 下仅少量次要列折叠；
- 分组编辑/删除按钮：tab 项 hover 浮现（统一用 opacity 机制，与操作列一致），弹窗/下拉承载。

| 优点 | 缺点 |
|---|---|
| 表格宽度最大化，信息密度对齐基估宝 | 模板结构调整（中等风险） |
| 消除左右分栏的割裂感，页面变「一个工作区」 | 分组多时 tab 行需横向滚动（可接受，滚动条细化为 `--border-light` 色） |
| 与探市/资产页「列表为主」的产品形态统一 | 分组拖拽排序（未来）需重新设计入口 |

#### 方案 C：分组下拉/弹出选择器（交互重设计，需进一步确认）

- 分组收进表格左上角的下拉选择器（el-select 或 popover），表格全宽；
- 适合「分组数量多、切换频率低」的用户，但对高频切换是负优化。

| 优点 | 缺点 |
|---|---|
| 表格最宽、最简洁 | 分组切换多一步操作，高频场景体验下降 |
| 自定义分组再多也不占横向空间 | 分组体系被「藏」起来，发现性差 |

> **推荐 B**；若用户顾虑模板改动，可先落 A 的窄栏 + 名称截断（低风险），再评估是否升级 B。

### 2.3 表格列宽与对齐（方案 B 语境）

| 列 | 建议宽度 | 对齐 | 说明 |
|---|---|---|---|
| 标记列（置顶/关注） | 44 | center | 收窄 6px；图标用 `--text-tertiary` 或语义 token（见 §2.6 修正） |
| 代码/名称 | **min-width 240** | left | 唯一弹性列，`show-overflow-tooltip` + 名称 `ellipsis`；标签 chips 移出本列（见 §2.4） |
| 添加自选日 | 100 | left | 日期非数字，左对齐更易扫读；字号 `--text-label` 13px，色 `--text-secondary` |
| 最新价 | 110 | right | 等宽数字（`tabular-nums`，MoneyDisplay 已保证） |
| 涨跌幅 | 100 | right | RiseFallText |
| 持有数量 | 110 | right | 数字 + 单位（份/股），单位 11px `--text-tertiary` |
| 持仓市值 | 120 | right | — |
| 添加后涨幅 | 110 | right | 双行（百分比 + 金额），行高 tight |
| 持仓收益 | 110 | right | — |
| 收益比 | 96 | right | — |
| 操作 | 108 | center | fixed right，按钮 hover 浮现 |

固定列合计（不含第一列）≈ **1008px**，加第一列 240 = 1248px → 2xl（1224px 可用）下**基本放下**，lg 下仍滚动但仅溢出次要列；配合 `watchlist-table-redesign-2026-08-13.md` 的 P2 列显隐（默认折叠「添加后涨幅/收益比」等低价值列），lg 下也可完整放下。

**对齐规范**：数字列一律 right + `tabular-nums`；文本列 left；标记/操作列 center。与探市页（`explore/index.vue:340-375` 数字列右对齐）保持全站一致。

### 2.4 产品名称显示统一（反馈 1a）

- 第一列**只放 `ProductDisplay`**（名称 14px `--text-primary` / 代码 12px `--text-tertiary`，沿用组件现状），列上加 `show-overflow-tooltip`；
- **标签 chips 保留在名称列第二行**（用户自维护的语义数据，可见性重要；最多显示 2 个 + `+N`，`el-tag` 用 `getTagColor + '20'` 底 + 1px 边框，现状写法保留；`show-overflow-tooltip` 看全量）；
- **移除行内场外 `AssetTypeBadge` 徽标**——「场内/场外」已由顶部 el-segmented 统一承担（§2.7），行内徽标冗余，腾出空间给标签；
- 加标签按钮：维持 hover 浮现（`index.vue:2035-2041` 已有 opacity 机制），但按钮尺寸统一 20px、图标 `--text-tertiary`。

### 2.5 分组名称长度限制与折叠（反馈 3b）

- 名称渲染统一为：`max-width: 100%` + `overflow: hidden` + `text-overflow: ellipsis` + `white-space: nowrap`，并加 `title` 全名提示（`index.vue:187` 处）；
- 展示截断阈值建议：**8 个汉字（16 字符）**，与后端 50 字符上限解耦——后端管存储，前端管展示；
- 数量徽章（`:199-208`）保持 `--text-tertiary` 等宽数字，与名称之间 `gap-2`；
- 分组「全部」等系统分组名短，不受影响。

### 2.6 视觉精致化清单（全部走 design token）

| 维度 | 现状 | 目标 |
|---|---|---|
| 页面结构 | 两张并列大卡片（`rounded-2xl` + `--shadow-raised`） | **一个工作区卡片**：表格卡片 `--radius-lg`，内部「分组 tab 行 + 筛选行 + 表格」用 `--border-subtle` 分割线分区；分组不再独立成卡 |
| 分组 tab 项 | 列表项 `px-3 py-1.5 rounded-lg` | 胶囊 tab：`px-3 h-8`（32px）、`--radius-pill`、选中 `--brand-100`/`--brand-700`/`--brand-400`、未选中 `--text-secondary` + hover `--bg-hover`；名称 ellipsis |
| 间距 | 卡片 `p-6`（`--space-standard`） | 工作区卡片 `p-6`；分组 tab 行 `mb-4`；筛选行 `pb-3 mb-4 border-b`（`--border-subtle`，现状 `--border-light` 偏重） |
| 字号层级 | 分组标题 `font-bold` 无字号 token | 「分组」标题 13px `--text-label` `--text-secondary`；tab 项 13px `--text-label`；表头已由 `el-table.css` 基线统一 |
| 悬停态 | 分组项无 hover 背景；操作/编辑按钮两套浮现机制 | 统一：hover 背景 `--bg-hover`；所有 hover 浮现按钮统一 opacity 机制（150ms `ease`，design.md Motion） |
| 圆角 | 分组卡 `--radius-lg`、列表项 `--radius-lg` | tab `--radius-pill`；标签 `--radius-pill`（Badge/Tag 规范） |
| 阴影 | 双卡 `--shadow-raised` | 仅工作区卡片 `--shadow-raised`；tab/筛选行无阴影 |
| 硬编码色 | `text-yellow-500` / `text-purple-400` / `#333333` / hex fallback | 置顶/关注图标改为 `--text-tertiary`（hover 提亮 `--text-secondary`），语义靠 icon 形状区分；`#333333` → `--text-primary`；数据色 fallback → `--text-tertiary` 并注释「数据色例外」 |

### 2.7 顶部筛选 tab 与分组卡片的对齐关系（反馈 1c）

- 方案 B 下不再有「分组卡片」与 segmented 对齐问题：**分组 tab 行左对齐**（占满整行），**el-segmented 右对齐**（与「标签筛选」下拉同组，`justify-between`）；
- 语义收敛：**删除左侧系统分组里的「场内资产/场外基金」两项**（`:1154-1159`），「场内/场外」只保留顶部 el-segmented 一个入口（它已能强制 venue 过滤，`:1442-1443`）；表格上方 venue 筛选胶囊（`:344-372`）与 segmented 功能重复，**二选一**——建议保留 segmented（页面级视图），删除表格上方胶囊，减少一层控件；
- 若用户希望保留胶囊式 venue 筛选，则删除顶部 segmented，二者不可并存。

---

## 3. 风险分级与实施顺序

### 3.1 纯 CSS / 布局调整（低风险，可立即做）

1. 分组名称 ellipsis + title（§2.5）；
2. 分组栏收窄 `w-56 → w-44`、内边距 `p-6 → p-3`（方案 A 的第一步，即使最终走 B 也值得先做）；
3. 第一列 `min-width 200 → 240` + `show-overflow-tooltip`；
4. 数字列对齐核查（含日期列改左对齐）；
5. 硬编码色修正（§2.6 最后一行，5 处）；
6. 分组项 hover 背景、统一按钮浮现机制。

### 3.2 模板结构调整（中等风险，需确认）

7. 方案 B：删除左侧分组卡片 → 顶部横向分组 tab（§2.2 B）；
8. 「场内/场外」三套入口收敛为一套（§2.7）；
9. 标签 chips 移出名称列（§2.4，或降级为「名称列加宽 + 名称优先 ellipsis」）。

### 3.3 交互重设计（需进一步确认）

10. 方案 C（分组下拉/弹出选择器）；
11. 分组 tab 的编辑/删除/新建入口布局（hover 浮现 vs 固定「+」按钮 + 管理抽屉）；
12. 列显隐与默认折叠列（联动 `watchlist-table-redesign-2026-08-13.md` P2）。

### 3.4 建议实施顺序

**第一步（纯 CSS，半天）**：1→2→3→5→6，先消除「粗糙感」最刺眼的点（名称截断、列宽、硬编码色）。
**第二步（方案确认后）**：7→8→9 模板重构，观察 2xl/lg 下的表格宽度收益。
**第三步（远期）**：10→11→12 交互增强，与列信息密度提案的 P1/P2 合并排期。

---

## 4. 待用户确认的问题（2026-08-14 已确认，见下）

1. 布局选 **B（顶部 tab + 全宽表格）** 还是先做 **A（窄栏）** 过渡？
2. 「场内/场外」入口保留 **el-segmented（页面级）** 还是 **胶囊筛选（表格级）**？（二选一，§2.7）
3. 标签 chips 是否同意移出名称列？（§2.4，影响第一列观感最大的一项）
4. 名称列 `min-width 240` 是否可接受？（当前 200，其他页面 150-180）

### 4.1 用户决策记录（2026-08-14）

| # | 问题 | 决策 |
|---|---|---|
| 1 | 布局方案 | **B：顶部横向分组 tab + 全宽表格** |
| 2 | 场内/场外入口 | **统一为顶部 el-segmented**（删除表格上方 venue 胶囊与左侧系统分组入口） |
| 3 | 标签 chips | **保留在名称列第二行**（用户自维护语义数据，可见性重要）；**移除行内场外徽标**（由顶部 segmented 承担）；最多 2 个 + `+N` 折叠 |
| 4 | 名称列宽度 | **min-width 240 可接受** |

> 实施范围：§3.2 第 7/8/9 项 + §3.1 低风险项，按 §3.4 顺序执行。标签方案按 §2.4 修订版（保留名称列、移除徽标）。

### 4.2 实施完成记录（2026-08-14）

已按 §4.1 决策落地（`frontend/src/views/asset/watchlist/index.vue`，纯模板/样式重构 + 死代码清理，接口与后端未动）：

- **布局**：左侧分组卡片与双卡并排结构删除，收敛为单个工作区卡片（`rounded-2xl p-6` + `--shadow-raised`）；内部「分组胶囊 tab 行 + 筛选行 + 表格」以 `--border-subtle` 分割线分区。
- **分组 tab**：32px 胶囊（`--radius-pill`），选中 `--brand-100` 底 / `--brand-700` 字 / `--brand-400` 边框（软按钮语义），未选中 `--text-secondary` + hover `--bg-hover`；名称 `max-width: 8em` ellipsis + `title`；数量徽章等宽数字；编辑/删除 hover 浮现（opacity 机制，与操作列统一）；横向滚动细滚动条。
- **venue 收敛**：删除表格上方 venue 胶囊（含 `venueStats`/`VENUE_FILTER_OPTIONS`/`currentVenueFilter`/`setVenueFilter` 死代码）；`systemGroups` 移除「场内资产/场外基金」两项；`fetchGroups` 前端过滤后端仍返回的 exchange/otc；`handleViewChange` 与分组解耦（venue 过滤由 `fetchParams` 依 `currentView` 独立承担）。
- **名称列**：`min-width 240` + `show-overflow-tooltip`；两行式（ProductDisplay + 标签 chips 最多 2 个 + `+N`）；移除行内场外徽标；加标签按钮 20px hover 浮现。
- **列宽/对齐**：标记 44 / 添加自选日 100 左对齐 / 添加后涨幅·持仓收益 110 / 收益比 96 / 操作 108；数字列 `tabular-nums`。
- **硬编码色 5 处**：置顶/关注 → `--text-tertiary`（hover `--text-secondary`）；标签弹窗 `#333333` → `--text-primary`；4 处数据色 fallback → `var(--text-tertiary)`（「数据色例外」注释）。
- **文档**：`frontend/design.md` 新增「分组胶囊 Tab」小节 + 行内图标规范；`design.dark.md` 补暗色适配说明；`docs/spec/changelog.md` 记 v4.8.4。

**验证**：`pnpm typecheck` 零错误；`eslint`/`prettier`/`stylelint` 对 index.vue 单独校验全部通过（全量 stylelint 仍有 18 个**既有**错误，位于 7 个未触碰文件，非本次引入，另行排期）。

---

## 参考

1. `frontend/src/views/asset/watchlist/index.vue`（2270 行，现状全部证据）
2. `frontend/src/components/WatchlistWidget.vue`（首页小组件，产品名称/数字列对齐参考）
3. `frontend/src/components/Watchlist/SettingsDrawer.vue`（管理抽屉，本次不动）
4. `frontend/src/components/ProductDisplay/index.vue`（名称组件，全站同源）
5. `frontend/src/views/explore/index.vue`（探市表格：名称列干净呈现的对照）
6. `frontend/src/views/asset/inventory/index.vue`（资产明细：`show-overflow-tooltip` 对照）
7. `frontend/design.md` / `design.dark.md`（设计令牌，全部视觉依据）
8. `frontend/src/style/el-table.css`（表格视觉基线）
9. `docs/working-notes/watchlist-table-redesign-2026-08-13.md`（列信息密度提案，P0/P1/P2）
10. `docs/working-notes/explore-watchlist-replan-2026-08-08.md` / `explore-watchlist-enhancement-2026-08-12.md`（历史决策墙）
