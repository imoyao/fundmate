---
title: 组件使用规范（设计语言实现层）
---

# 组件使用规范（设计语言实现层）

> 本文件是 `frontend/design.md` 的**实现层补充**，承载「具体组件怎么用」的细节。
> `design.md` 只保留设计令牌、设计原则与全局规范（颜色/字体/间距/形状/阴影/文案基调等）。
> 组件级的 props、阈值、栅格类名、页面级约束均下沉于此，避免污染「设计语言唯一标准」。

## 强制复用清单

页面级 UI **必须复用**以下组件，禁止在各页面重新手写同类结构：

- `SectionHeader` — 区块统一标题行
- `MetricCard` / `MetricGrid` — 指标卡 / 指标网格
- 数值与状态展示（设计令牌强制统一，见下节）：
  - `MoneyDisplay` — 金额展示（千分位 + 涨红跌绿 + 等宽数字）
  - `RiseFallText` — 涨跌幅文本（正负号 + 涨红跌绿 + 等宽数字）
  - `ProductDisplay` — 产品信息单元格（名称 + 代码 + 类型标签，表格产品列统一）
  - `AssetTypeBadge` — 资产 / 账本类型胶囊（统一账本配色）
- `CardBlock` — 区块卡片容器（统一 token 卡片，禁各页手写 `bg-white rounded-2xl` 等重复样式）
- `PortfolioEditDialog` — 组合编辑对话框（编辑组合 + 关联账户，自 portfolio 详情页拆出）
- `TagManagerDialog` / `TagFormDialog` / `TagEditorDialog` — 自选标签管理（GitHub Labels 风格列表）/ 标签新建编辑轻量弹窗 / 行内标签编辑弹窗（自 watchlist 页拆出，见「自选标签弹窗」章节）
- `TemperatureGaugeCard` — 温度环形卡（探市 / 温度计 / 达报三页复用）
- `TemperatureContextCard` — 温度上下文解读卡
- `PageHeaderBar` — 页面统一页头
- `PageFooter` / `MarketFooter` — 探市 / 温度计页脚
- `Superellipse` — 品牌 n=3 超椭圆容器（logo / 头像 / 卡片普适轮廓，禁各处手写圆角或 polygon 轮廓）
- 全站页脚：`frontend/src/layout/components/lay-footer/index.vue`
- 共享基建（composables / utils 非 UI 层）：`useEchartsLifecycle` / `getCssVar` / `useFundTradeDate` / 币种工具，见文末「共享基建」章节

组件路径位于 `frontend/src/components/{组件名}/index.vue`。

## 元素层级与标签位置（强制统一）

所有带颜色的等级 / 状态标签（`TemperatureLevelBadge`）必须固定在**卡片标题行右侧**，禁止出现在卡片中部、左下角、数字下方等位置。

- `MetricCard`：标题行右侧。
- `TemperatureGaugeCard`：标题行右侧（通过 `level` prop）。
- `TemperatureContextCard`：标题行右侧（根据 `temperature` 自动推导）。
- 任何新增指标卡：标题行右侧。

## SectionHeader · 区块统一标题行（强制复用）

- 用途：所有页面区块的标题行统一收口到本组件，**禁止各页面再手写 `<h2>/<h3>` + 分散的提示图标 / 操作按钮**。
- 结构：左侧「标题 + 可选信息图标（hover / 焦点 tooltip）」+ 右侧「操作槽（具名插槽 `#action`）」。
- props：`title`（区块标题）、`info`（信息图标 tooltip 文案，缺省则不显示图标）、`icon`（信息图标名，默认 `ep:info-filled`）。
- 与 `MetricCard` / `TemperatureGaugeCard` 标题行视觉一致（16px / 600 / `--text-primary`，右侧操作槽垂直居中）。

## 设置页 · 单栏居中布局（D13）

面向「个人中心 / 设置」类**账户管理页**，采用 Vercel / Trae 风格的单栏居中设置页，**禁止双栏多卡散乱平铺**：

- 页外层 `max-width: 680px`（D13 原定 680 → D15 覆写 960 → **D17 回覆写 680px 定稿**，以 D17 为准）+ `margin: 0 auto`，顶部用 `PageHeaderBar` 统一页头。
- 纵向区块（如 个人资料 / 账号安全 / 退出登录）用「卡片（`settings-card`）+ `SectionHeader` + 设置行」组织；卡片间 `gap: var(--space-5)`。
- **设置行（`setting-row`）**：一行为一个独立设置项，结构 = 左侧 `label + desc`（`flex-basis:160px`，desc 用 `--text-tertiary`）+ 右侧主操作区（`justify-content:flex-end`）。行内分割线用 `--border-subtle`，行高 ≥ 48px 保证热区。
- 响应式：≤640px 时行内改为上下堆叠（label 在上、控制在下方）。
- 参考实现：`frontend/src/views/profile/index.vue`。

## 果冻胶囊按钮组（D13）

用于**多选一、且选项数量少（2–6）**的紧凑选择（如头像画风选择、手动录入的买/卖类型）。具弹性回弹的胶囊按钮，是"温暖极简主义"的交互签名。

- 形状：胶囊（`border-radius: var(--radius-pill)`），透明底 + 1px `--border-default` 边框。
- 未选中：`color: var(--text-tertiary)`，hover 提到 `--text-primary`、边框 `--brand-400`。
- 选中：`color: var(--brand-700)` + `background: var(--brand-100)` + 边框 `--brand-400` + `box-shadow: 0 1px 3px rgb(0 0 0 / 6%)`。
- **弹性动画**：选中态触发 `style-pop` 关键帧（`scale 1→0.92→1.05→0.97→1`），`:active` 收缩 `scale(0.92)`；缓动统一 `cubic-bezier(0.34, 1.56, 0.64, 1)`；`transform-origin:center` + `will-change:transform`，加 `transform: translateZ(0)` 避免模糊。
- `:focus-visible` 必须有 `--focus-ring`。
- 参考实现：`frontend/src/views/profile/index.vue` 的 `.style-capsule`、`frontend/src/views/asset/investment/manual/index.vue` 的 `:deep(.el-radio-button__inner)`。

## Superellipse · 品牌超椭圆容器（D15，强制复用）

logo、头像、卡片等需要品牌轮廓的容器，**必须复用** `Superellipse` 组件，禁止各处手写 `border-radius` 圆角或 SVG polygon 轮廓（品牌 n=3 超椭圆在「直线→曲线」过渡点是连续曲率，视觉比圆形圆弧更柔和，是设计语言「温暖极简」的形状签名）。

- 名称：`Superellipse`（`frontend/src/components/Superellipse/index.vue`）。
- props：`power`（超椭圆指数 n，默认 3；越大越接近直角方形，`2` 即标准圆）、`points`（采样点数，默认 128，越多越平滑、SVG 字符串越长）。
- slot：被裁剪成超椭圆的内容（不限定单元素）。
- 实现方式：**SVG `<polygon>` 黑底超椭圆 → `mask-image`（data-URI SVG）**，全浏览器（含旧 Webkit，带 `-webkit-` 前缀）、像素级、可响应尺寸、无 DOM 剪裁 id 冲突。原理调研见组件头注释（弃用 CSS Houdini Paint worklet / 非 Web 的 smooth-corner-rect）。
- 尺寸由使用方通过 class 控制（如 profile 头像 `.avatar-frame` 88px），组件本身不预设尺寸。
- 参考实现：`frontend/src/views/profile/index.vue` 头像容器（`<Superellipse :power="3">` 包裹 `avatar-frame`）。

## 12 列栅格与容器层级（布局强制统一）

页面区块统一采用「区块卡外套 + 卡内指标块」两级容器，列宽仅允许以下组合：

- **8 + 4**：左侧主内容（如温度仪表 / 机会清单 / 概览 4 宫格）占 8 列，右侧辅助（如可转债温度 / 心理账户 / 操作卡）占 4 列。
- **4 + 4 + 4**：三类并列指标的窄列布局（如市场宽度 / 大类资产 / 资产与持仓每组 4 象限）。
- **12**：单一整块（极少见）。

实现约束（单一来源）：

- 页面外层用 `.block-shell` 包裹 `SectionHeader` + 内容区；块与块之间 `gap: var(--space-5)`（24px，注意：原文档曾误写为 `--space-7`，该 token 在 Spacing 章节未定义，已统一为 `--space-5`）。
- 内容区用 `.grid-12`（`display:grid; grid-template-columns: repeat(12, 1fr); gap: var(--space-5)`），子项用 `.col-4` / `.col-8`（`grid-column: span N`）。
- 每层 `MetricGrid` 内部 **必须 `:columns="12"`**，由父级 `.col-4/.col-8` 决定其实际占宽；禁止在 `.col-*` 内写 `:columns="4"`（会造成 4+4+4 与 8+4 视觉错位）。
- 响应式：≤960px 时所有 `.col-4 / .col-8` 退化为 `grid-column: span 12`。
- **心理账户**等次级区块必须补充「区块卡外套」（`SectionHeader` + 卡片容器），与「财务晴雨表」等主区块视觉对齐，禁止裸列表直接铺在页面上。

## MetricCard · 指标卡（统一数字排布）

结构：`标题（小字 secondary）` → `大数字 + 小单位 + 等级标签` → `副文案（可选）`

| 元素 | 字号 | 字重 | 颜色 | 说明 |
|------|------|------|------|------|
| 标题 | 13px | 500 | `--text-secondary` | 指标名 |
| 数字 | 28px（featured 36px） | 700 | `--text-primary` | 等宽字体 `--font-mono` |
| 单位/符号 | 14px（featured 16px） | 500 | `--text-tertiary` | 与数字**同行**基线对齐，禁止换行 |
| 等级标签 | —— | —— | 复用 `TemperatureLevelBadge` | 固定于标题行右侧 |
| 副文案 | 12px | —— | `--text-tertiary` | 使用客观、专业的金融术语，禁止口语化 |

- 卡片：`--bg-card` + `--border-light` + `--radius-lg` + `--shadow-raised`，padding 16–18px。
- 禁止各页面单独定义 `.mini-card` / `.primary-value` 等同类样式。

## MetricGrid · 指标网格

- `display: flex; flex-wrap: wrap; gap: var(--space-compact)`。
- 子项默认 `flex: 1 1 200px`，featured 子项 `flex: 2 1 400px`。
- 行内剩余空间由 flex 自动均分，避免出现右侧大片空白。
- 响应式：≤960px → 最小宽度 160px；≤520px → 1 列。

## CardBlock · 区块卡片容器（强制复用）

- 用途：区块卡（`SectionHeader` + 内容区）的统一容器，**禁止各页面手写 `bg-white rounded-2xl p-6 shadow-sm border` 等重复样式**。
- 结构：纯容器 `<section class="card-block">` + 默认插槽；与 `SectionHeader`、`MetricCard` 卡片视觉一致（`--bg-card` + `--radius-lg` + `--border-light` + `--shadow-raised` + `--space-standard` 内边距）。
- 间距由使用方通过 class 控制（如 `class="mb-6"`），组件不预设外边距。

## PortfolioEditDialog · 组合编辑对话框（强制复用）

- 用途：编辑组合基本信息（名称 / 目的 / 描述 / 目标收益率 / 目标金额 / 目标日期 / 基准指数）+ 关联账户（未关联排前、组合名映射、保存时 diff 出 unlink/link）。
- props：`modelValue`(v-model 显隐)、`portfolio`(`PortfolioDetail | null`，须为完整详情)、`linkedLedgerIds`(`number[]`，当前已关联账户 id)。
- emits：`update:modelValue`、`saved`（保存成功后触发，**由父页面负责重新拉取详情**）。
- 说明：账户关联 diff（unlink/link 逐个调接口）当前仍在前端实现，已记技术债务（后端应提供原子化更新接口），见对应 issue。
- 参考实现：`frontend/src/views/asset/portfolio/detail.vue`。

## 自选标签弹窗（业务共有组件）

### TagManagerDialog · 标签管理弹窗（GitHub Labels 风格）

- 用途：自选标签的「列表管理」（展示 + 删除 + 调起新建/编辑），自 `watchlist/index.vue` 拆出的共有组件。
  交互参考 GitHub Labels，但套用多多贝设计语言：**白底卡片列表 + 顶部搜索/新建，与「表单填写」彻底解耦**。
- 路径：`src/components/Watchlist/TagManagerDialog.vue`。
- 视觉框架（强制统一，禁止偏离 design.md）：
  - 容器：白底（`--bg-card`）卡片，圆角 `--radius-lg`(16px)，列表行间用 `--border-light` 浅色分割线。
  - 顶部：左侧 `el-input`（胶囊 `--radius-pill`）+ 右侧 `--brand-700` 实心「新建标签」主按钮（替代原底部操作区）。
  - 列表行高：`min-height: 46px`（约 44–48px），hover 行底色变深（`--bg-soft`）。
  - 名称列：用 `--radius-pill` 胶囊底色展示标签色 + 名称（`tag-pill`，底色为标签色 + 低透明度、文字用原色）。
  - 统计列：展示「N 个资产」（父组件传入每个标签被多少资产引用）。
- props：`modelValue`(v-model 显隐)、`allTags`(全部标签)、`tagUsage`(标签 id → 使用计数 `Map<number, number>`，`>0` 表示被资产使用、禁止删除，父组件基于当前列表计算)。
- emits：`update:modelValue`、`tags-changed`(增删改标签后触发，父组件刷新标签列表)。
- 新建/编辑**不在列表内嵌表单**，统一调起 `TagFormDialog` 轻量弹窗（行内操作默认隐藏、hover 显现：编辑=次级色、删除=`--color-danger` 幽灵态）。

### TagFormDialog · 标签新建/编辑轻量弹窗

- 用途：单个标签的「名称 + 颜色」编辑，与列表管理彻底解耦（GitHub Labels 思路）。由 `TagManagerDialog` 在点击「新建标签」或某行「编辑」时调起，回填原 name/color。
- 路径：`src/components/Watchlist/TagFormDialog.vue`。
- 内容：一个 `el-input`（名称，带字数上限/计数）+ 预设色圆点（复用 `PRESET_TAG_COLORS`）+ 底部「取消 / 保存」。
- props：`modelValue`(v-model 显隐)、`tag`(待编辑标签，`null` 表示新建)。
- emits：`update:modelValue`、`saved`(保存成功后触发，父组件刷新标签列表)。
- 内部按 status `409` 提示「该标签已存在」。
- 颜色域（强制统一）：预设色来自 `constants/watchlist.ts` 的 `PRESET_TAG_COLORS`（莫兰迪色系：低饱和、灰调柔和、区分度高，共 12 色），默认色 `DEFAULT_TAG_COLOR` 取色板第一项（珊瑚红 `#e07a6b`）。
  - 表单内除「点选色板」外，提供一个「随机」圆点按钮：调用 `randomMorandiColor(usedColors)`，**不是纯随机**，而是先从色板中排除已用色、再从剩余候选里随机挑一个，保证范围可控 + 用户可读性 + 界面区分度。
  - 后端 `color` 字段仍接受任意合法 hex（不强制色板），色板仅作「可选 / 默认 / 受控随机」来源。

### GroupManagerDialog / GroupFormDialog · 分组管理（与标签同构）

- 分组与标签功能基本同构（都只是「名称 + 颜色」的命名实体），因此分组管理**完全沿用标签的 GitHub Labels 风格组件**，保持设计语言统一，禁止在 `watchlist/index.vue` 内联分组管理 UI。
- `GroupManagerDialog.vue`：路径同 `TagManagerDialog`。白底卡片列表 + 顶部搜索/新建，`allGroups` 含系统分组（`is_system=true`），系统分组行**隐藏编辑/删除**（用「系统分组」标识替代统计列），自定义分组 hover 显现编辑/删除。
- `GroupFormDialog.vue`：路径同 `TagFormDialog`。名称输入 + 预设莫兰迪色板点选 + 受控随机取色（复用 `PRESET_TAG_COLORS` / `randomMorandiColor`），无 description 字段（后端分组模型无该字段，与标签保持一致取舍）。
- 父组件（`watchlist/index.vue`）通过 `@groups-changed` 刷新 `allGroups`；分组 tab 行仅做展示与切换，增删改一律收口到这两个组件。

### TagEditorDialog · 行内标签编辑弹窗（资产维度）

- 用途：为单个自选资产**添加 / 移除**标签（资产维度的标签归属），自 `watchlist/index.vue` 拆出的共有组件。注意与 `TagFormDialog`（标签维度的新建/编辑）职责不同，二者不可混淆。
- 路径：`src/components/Watchlist/TagEditorDialog.vue`。
- props：`modelValue`(v-model 显隐)、`item`(当前自选资产 `WatchlistItem`)、`allTags`(全部标签)。
- emits：`update:modelValue`、`saved`(保存成功后触发，父组件负责刷新列表与标签)。
- 内部按 `item.tag_ids` 排除已选，`availableTags` computed 提供可添加的标签。

> 自选 × 探市边界结论：探市页（/explore）是引流沙盒（未登录 localStorage 草稿，仅「看 + 轻收藏」），
> 自选页是权威管理（后端 API + 标签/分组/批量/OCR）。两者表格**刻意不共用**（产品边界不同）；
> 共享的是底层 composable（`useAssetSearch` / `useRealtimeQuotes` / `useAuthState`）。
> 标签相关能力集中在本组组件，未来若探市页或其它页面需要标签管理，直接复用本组组件。

## 数值与状态展示组件（设计令牌强制统一）

金额、涨跌幅、资产类型等「带色彩的敏感数值」是设计语言最易串味的区域。**必须复用以下组件，禁止各页面手写 `+ / -` 拼接、`style="color:red"` 或裸 `<span>` 拼数字**。

### 涨红跌绿（强制规则）

- 涨 = 红（`--color-rise`），跌 = 绿（`--color-fall`），零 = 灰（`--text-secondary`）。
- 数字一律等宽（`font-variant-numeric: tabular-nums` + `--font-mono`），保证列对齐与位数稳定。
- 该语义仅由下方组件承载，页面不得自行定义涨跌色。

### MoneyDisplay · 金额展示

- 用途：货币金额（市值、收益、成本等）。自动千分位、`¥` 符号、正负号、零值统一 `¥0.00`。
- props：`value`、`currency`(默认 ¥)、`showSign`(默认 true)、`showCurrency`(默认 true)、`precision`(默认 2)、`autoColor`(默认 true)、`customColor`、`suffix`、`size`(xs | sm | md | lg | xl | hero)。
- 尺寸严格映射设计令牌：hero→`--text-hero`(48px)、xl→`--text-display`(32px)、lg→`--text-title`(24px)、md→`--text-body`(16px)、sm→`--text-small`(14px)、xs→`--text-label`(13px)。

### RiseFallText · 涨跌幅文本

- 用途：百分比 / 比率类涨跌（涨跌幅、偏离度等）。默认后缀 `%`，自动正负号与涨红跌绿。
- props：`value`、`suffix`(默认 %)、`showSign`(默认 true)、`precision`(默认 2)、`autoColor`(默认 true)、`customColor`、`size`(sm | md | lg)。

### MoneyWithRatio · 金额(主) + 比例(辅) 组合展示

- 用途：金额与对应比例的「主次双行」展示，避免页面手写「数字 + 比例」堆叠导致主次颠倒。典型场景：自选页「持仓市值 / 持仓收益 / 添加后涨幅」等列（金额为主、比例为例，金额在上、比例在下）。
- 设计约束（强制）：主数字明显大于辅比例，且辅比例弱化透明度（`opacity: 0.72`），形成清晰主次；涨跌配色沿用 `--color-rise` / `--color-fall` 语义变量，禁止页面硬编码颜色。
- props：
  - `value`：主金额（元）；`ratio` 为 null / undefined 时仅显示金额（如无总市值、市值为 0）。
  - `ratio`：辅比例（百分比数值，如 `3.21` 表示 `+3.21%`）；缺省时不渲染比例行。
  - `showSign`(默认 true)、`showCurrency`(默认 true)、`moneySize`(默认 `md`，即 16px 主数字)。
  - `ratioPrecision`(默认 2)、`ratioSuffix`(默认 `%`)、`showRatioSign`(默认 true)。
  - `ratioAutoColor`(默认 true，按正负涨跌着色；占比等非涨跌语义请传 `false`，比例走中性 `--color-info`)。
  - `alignRight`(默认 true，表格列右对齐)、`emptyText`(默认 `--`)。
- 调用示例（自选页持仓收益列，金额上 + 收益率下）：

  ```vue
  <MoneyWithRatio
    :value="holdingPnl"
    :ratio="holdingPnlPercent"
    :show-currency="false"
    :show-sign="true"
    :auto-color="true"
  />
  ```

- 注意：比例行尺寸固定 `sm`(13px)，**不要**用 `size` 把它调得比主数字大；非涨跌语义（如持仓市值占比）务必 `:ratio-auto-color="false"`，避免把占比误染成涨红。

### AssetTypeBadge · 资产 / 账本类型胶囊

- 用途：资产 / 账本类型标签（股票、基金、可转债等），统一账本配色 `getLedgerColor`，禁止页面自定类型色。
- props：`type`(账本类型 key)、`label`(可选覆盖文案)、`variant`(`light` 浅底胶囊 / `tag` el-tag)。

### ProductDisplay · 产品信息单元格

- 用途：表格「产品信息」列的统一样式（名称 + `# 代码` + 类型标签），与导入预览页保持一致，禁止各页面手写 `.product-cell` / `.type-tag-inline` 结构。
- props：`name`(产品名称)、`symbol`(资产代码)、`typeLabel`(类型中文标签)；`name || symbol || "--"` 兜底展示。
- 注意：`typeLabel` 为**后端类型文案**（如 `row.type_label`），非账本类型 key；按账本类型配色请用 `AssetTypeBadge`。
- **列宽规范（统一三档，禁止各页再手写 min-width 200+）**：
  - `min-width: 160` — 标准持仓 / 流水表（inventory、ledgers 交易、portfolio 持仓）
  - `min-width: 200` — 含类型标签且列多需要呼吸感的表（watchlist 自选）
  - `min-width: 120` — 纯名称紧凑场景（TransactionList 交易流水，无代码标签）
- **截断与 hover 提示**：组件内 `product-name` 已单行截断（`overflow: hidden; text-overflow: ellipsis`），
  使用方在表格列上加 `show-overflow-tooltip` 即可在名称溢出时 hover 出完整名称（ElTooltip 原生，仅在溢出时出现，无视觉干扰）。

## PageSkeleton · 页面骨架屏（强制复用）

- 用途：页面加载骨架屏，模拟真实页面结构（概览指标卡 / 图表卡 / 表格行），作为内容占位容器防布局偏移（CLS）。
- props：`cards`(概览卡数，默认 3)、`chartCols`(图表卡列数，默认 2)、`tableRows`(表格行数，默认 6)。
- 实现铁律（业界最佳实践）：
  1. **结构一致**：形状 / 数量 / 宽度与真实内容布局高度一致（真实 DOM + 灰底圆角，非装饰条条）；
  2. **轻量化**：纯 CSS `linear-gradient` 流光（background-size 动画，GPU 合成，不占 JS 主线程），1.8s 慢速；
  3. **A11y**：根节点 `aria-hidden="true"`；
  4. **阈值控制（使用方负责）**：请求 ≤200ms 返回时跳过骨架屏避免闪屏——`loading` 开始后 `setTimeout(200ms)` 才置 `showSkeleton = true`，加载结束清除计时器并复位。

示例（`ledgers/detail.vue`）：

```html
<PageSkeleton v-if="loading && showSkeleton" :cards="3" :chart-cols="2" :table-rows="6" />
```

## AssetAllocationDonut · 资产配置环形图（强制复用）

- 用途：资产配置分布图的统一组件（环形 + 底部图例：分类名 + 占比），替代各页手写 pie option。
  **此前 `ledgers/index.vue` 与 `ledgers/detail.vue` 各写一套、图例风格不一致，统一收敛到本组件。**
- 基于 `useEchartsLifecycle`：自动 render / window resize / 卸载 dispose / keepAlive 重绘（传新 data 引用自动重绘）。
- props：`data`(`{ name, value }[]`)、`colorMap`(name → CSS 变量名，如 `{ 股票: "--invest-stock" }`)、`emptyText`(空态文案)、`showLegend`(默认 true)。
- 颜色红线：必须经 CSS 语义变量（`colorMap` 传变量名，组件内 `getCssVar` 读取）；不传或缺失回退 `--chart-01~08` 循环。
- 参考实现：`frontend/src/views/asset/ledgers/detail.vue`（`typeColorMap` + `allocationData`）。

## TemperatureGaugeCard · 温度环形卡（三页复用）

- 供「探市 / 温度计 / 达报」使用，纯 SVG 圆环（与现有温度计页一致，不引入 echarts）。
- 标题默认「综合市场温度」，可转债温度等通过 `title` prop 覆盖（如 `title="可转债温度"`）。
- 颜色语义分两类，单一来源见 `src/style/colors.css` 的 `--temp-*` token：
  - **综合市场温度**（`title === "综合市场温度"`）：取档位语义色 `<40 → --temp-low`，`40–60 → --temp-mid`，`>60 → --temp-high`。
  - **其它温度（如可转债）**：按数值取温度带色，与档位阈值对齐：`≤15 → --temp-cold`，`≤35 → --temp-cool`，`≤65 → --temp-neutral`，`≤85 → --temp-warm`，`>85 → --temp-hot`。保证颜色语义与数值区间严格对应，避免与涨跌红绿混淆。
- 档位文案：偏低·偏冷 / 正常·温和 / 偏高·偏热（由 `level` prop 透传，对应温度档位文案）。
- **职责单一**：本组件只渲染圆环与标题、caption，不再内嵌恐惧贪婪或短中长期。相关上下文由 `TemperatureContextCard` 承载。

## TemperatureContextCard · 温度上下文解读卡

- 承载从 `TemperatureGaugeCard` 拆出的文字信息：温度等级标签、恐惧贪婪指数、短 / 中 / 长期温度。
- 等级标签固定于标题行右侧，与 MetricCard 统一。
- 恐惧贪婪指数用「数值 + 分 + 情绪描述」三件套展示。
- 短中长期用胶囊行排列，每个胶囊包含色点、周期名、温度值。

## PageHeaderBar · 页面统一页头

| 元素 | 字号 | 字重 | 颜色 |
|------|------|------|------|
| 标题 | `var(--text-display)`（32px） | 300 | `--text-primary` |
| 副标题 | 14px | —— | `--text-secondary` |
| 更新时间胶囊 | 12px | —— | `--text-tertiary`，`--bg-soft` 底 + `--border-light` |

> 副标题风格：专业、客观，避免过度口语化。

## PageFooter / MarketFooter · 探市 / 温度计页脚（复用）

- 结构：左侧「复盘」引导 + 右侧公众号引导卡片。
- **背景同色收尾**：页脚容器与各区块卡背景一致，使用页面底色 `--bg-page`（不再用卡片底 `--bg-soft`），避免页脚在页面底部出现色块割裂。
- **公众号引导**：右侧卡片内含二维码占位块（`.footer-card__qr`，96×96，虚线边框 + `QR` 字样占位），文案改为「扫码获取更多市场温度解读」。上线时替换为真实二维码图片。
- **禁止复制粘贴串味**：
  - `revisitText`（复盘首句）和 `revisitItems`（复盘列表）都必须与页面语义一致。
  - 温度计页可用「体温」「市场温度解读」等表达；探市页不得出现此类专属词汇。
- `revisitText` / `revisitItems` 使用专业、克制的表达，避免鸡汤式文案。

## AppFooter · 全站统一页脚（布局级）

- 三栏：品牌 / 导航 / 公众号 + 底部风险免责声明 + 版权。
- 接入 `layout/index.vue`，登录 / 注册页通过 `route.meta.hiddenFooter` 隐藏。
- 免责声明固定文案：「市场有风险，投资需谨慎。本平台内容仅供参考，不构成任何投资建议。」

## 共享基建（composables / utils 层，强制复用）

> 本层为**非 UI 的共享逻辑**（图表生命周期 / 图表取色 / 币种换算），与页面级 UI 组件同属「强制复用」范围。
> 各页面**禁止**重新手写 `echarts.init` + `getComputedStyle` 读色 + `window.addEventListener("resize")` + `onBeforeUnmount dispose` 这类逻辑，统一收口到以下入口。

| 基建 | 路径 | 职责 |
|------|------|------|
| `useEchartsLifecycle` | `src/composables/echarts/useEchartsLifecycle.ts` | 统一 ECharts 生命周期：render / resize / 卸载 dispose / keepAlive 重绘 |
| `getCssVar` / `CHART_TOKENS` / `getChartPalette` | `src/composables/echarts/theme.ts` | 图表读色唯一入口（读 CSS 语义变量，禁止硬编码 hex） |
| 汇率 / 币种常量 | `src/constants/exchangeRates.ts` | 币种 / 汇率 / 符号单一来源（实时汇率以后端 CNY 下发为准，本文件仅前端兜底） |
| 货币工具 | `src/utils/currency.ts` | `toBaseCurrency` / `fromBaseCurrency` / `getCurrencySymbol` / `formatAmount` |
| `usePageRefresh` | `src/composables/usePageRefresh.ts` | 全局刷新事件订阅（防抖计时器每实例私有） |
| `useFundTradeDate` | `src/composables/useFundTradeDate.ts` | 基金交易日期联动（calcFundConfirmDate + fetchFundNav），BuyForm / SellForm / TransactionEditDialog 三处共用 |

### useEchartsLifecycle · 图表生命周期

- 用途：取代各页手写 `echarts.init` / `window resize` 监听 / `onBeforeUnmount dispose`，统一收口，杜绝内存泄漏与 keepAlive 缓存页图表空白。
- 入参：
  - `specs: ChartSpec[]`，每个 `{ ref: 容器模板 ref, build: (el) => EChartsInstance }`；`build` 内部 `echarts.init(el)` + `setOption` 后返回实例。
  - `options: { keepAlive?: boolean; autoRenderOnMount?: boolean }`。
- 返回：`{ render, resize, charts }`。
- 用法：
  - 异步数据页设 `autoRenderOnMount: false`，数据就绪后调 `render()`；同步数据（渲染时即有数据）可省略，挂载后自动渲染。
  - keepAlive 页务必传 `keepAlive: true`（`onActivated` 自动 resize，修复缓存回来图表空白 / 尺寸错乱）。
  - `render()` 每次先 dispose 旧实例再重建，重复调用安全（无重复 init 警告）。

  ```ts
  import { ref } from "vue";
  import echarts from "@/plugins/echarts";
  import { useEchartsLifecycle } from "@/composables/echarts/useEchartsLifecycle";

  const pieRef = ref<HTMLElement | null>(null);
  const { render } = useEchartsLifecycle(
    [
      {
        ref: pieRef,
        build: (el) => {
          const c = echarts.init(el);
          c.setOption({ series: [{ type: "pie", data: [] }] });
          return c;
        }
      }
    ],
    { keepAlive: true, autoRenderOnMount: false }
  );
  // 异步数据就绪后：render();
  ```

### theme.ts · 图表取色

- 图表颜色一律 `getCssVar(CHART_TOKENS.rise)` / `getChartPalette()`，**禁止硬编码 hex**（design.md「Data Visualization」红线）。
- `getCssVar(name, fallback?)`：读取 CSS 语义变量（含前导 `--`），带 fallback（SSR 安全，`window` 不存在时返回 fallback）。
- `CHART_TOKENS`：集中维护图表常用语义色 token（`rise` / `fall` / `brand700` / `info` / `neutral` / `warning` / `success` / `accent` / 各级文字 / 边框 / 卡片底）。
- `getChartPalette()`：实时读取 `--chart-01`~`--chart-08` 8 色分类配色板（函数式调用，避免模块加载时主题未就绪读到空值）。
- 暗色模式由 CSS 变量自动切换，图表代码不判断主题。

### exchangeRates / currency · 币种换算

- 生产环境实时汇率由后端 enrich 计算并以 CNY 下发（`distributions.total_assets_cny` / `positions_total_mv`），前端一般无需自行换算；本组文件作为「前端按币种展示 / 换算时的唯一来源」，避免各页内联魔法数字。
- `constants/exchangeRates.ts`：`CurrencyCode`（CNY / USD / HKD / JPY）、`BASE_CURRENCY`、`EXCHANGE_RATES`（1 外币 = ? CNY，静态参考值）、`CURRENCY_SYMBOLS`。接入实时汇率时只改此文件，调用方不变。
- `utils/currency.ts`：`toBaseCurrency(amount, currency)` / `fromBaseCurrency` / `getCurrencySymbol` / `formatAmount(value, precision)`。
  - `formatAmount` 仅用于图表 tooltip / label 等**非 DOM** 字符串场景；DOM 着色展示仍用 `MoneyDisplay` / `MoneyWithRatio`。

### usePageRefresh · 刷新事件订阅

- 订阅全局 `refresh-ledger-data` 事件（`src/utils/mitt.ts` emitter），带防抖，卸载自动清理。
- 2026-08-15 修复：防抖 `timeoutId` 由模块级改为**每实例私有**。此前多个页面同时订阅时会互相 `clearTimeout` 对方定时器，导致先触发的回调永不执行。

### useFundTradeDate · 基金交易日期联动（强制复用）

- 用途：统一封装「交易日期 → `calcFundConfirmDate` → 确认日期 + 实际净值日 → `fetchFundNav`」调用链。**BuyForm / SellForm / TransactionEditDialog 三处共用**，此前各自重复实现同一套 `calcFundConfirmDate` 调用 + 响应解析 + `fetchFundNav` 拉取，现已收敛到本 composable。
- 路径：`src/composables/useFundTradeDate.ts`。
- 返回：`{ navLoading, actualNavDate, confirmDate, calcConfirmAndNav, reset }`。
- `calcConfirmAndNav(options)` 入参：
  - `tradeDate`（必填）：交易日期 `YYYY-MM-DD`。
  - `symbol`（可选）：基金代码。传入则自动用 `actualNavDate` 拉净值，返回 `nav` 字段。
  - `isAfter15`（可选，默认 `false`）：是否 15:00 后下单（影响确认日计算）。
- 返回 `CalcResult | null`：`{ actualNavDate, confirmDate, nav? }`。
- **调用方自行判断是否基金**（非基金不要调本 composable，股票/可转债确认日 = 交易日）。
- 用法示例：

  ```ts
  import { useFundTradeDate } from '@/composables/useFundTradeDate';

  const { navLoading, confirmDate, calcConfirmAndNav, reset: resetTradeDate } =
    useFundTradeDate();

  // watch 交易日期变化
  watch([() => form.value.trade_date, () => isAfter15.value], async ([newDate]) => {
    if (!newDate || !isFund.value) return;
    const result = await calcConfirmAndNav({
      tradeDate: newDate,
      symbol: form.value.symbol, // 传入则自动拉净值
      isAfter15: isAfter15.value,
    });
    if (result) {
      form.value.confirm_date = result.confirmDate;
      if (result.nav != null) form.value.price = result.nav;
    }
  });
  ```

- 已接入组件：
  - `QuickEntry/BuyForm.vue` — 传 `symbol`，自动回填净值到 `form.price`。
  - `QuickEntry/SellForm.vue` — 不传 `symbol`，仅算确认日用于展示 + 估算赎回费。
  - `ledgers/components/TransactionEditDialog.vue` — 传 `symbol`，自动回填净值 + 确认日。
- **禁止**在上述组件或新增的交易录入页面中重新手写 `calcFundConfirmDate` + `fetchFundNav` 调用链，统一走本 composable。

## 文案基调（页面级落地示例）

页面文案应保持**专业、客观、克制**，优先使用金融术语与结构化表达，避免过度口语化、场景化或鸡汤式表达。

| 场景 | 推荐表达 | 避免表达 |
|------|----------|----------|
| 指标说明 | 权益资产相对固收资产的预期收益优势 | 股票相对债券的便宜程度 |
| 指标说明 | 全市场当日成交金额，反映资金活跃度 | 全市场每日成交总量 |
| 页头副标题 | 聚合多源市场数据，构建全景估值与情绪监测体系 | 把全市场摊开来看哪里冷清哪里火热 |
| 复盘引导 | 建议结合估值、情绪与资金面综合判断，避免单一指标驱动交易决策 | 投资是场马拉松，不是百米冲刺 |
