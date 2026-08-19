---
title: 前端区域布局与组件交互规范（frontend-ui）
---

# 前端区域布局与组件交互规范（frontend-ui）

本文件收录前端通用业务组件规范（原 SPEC 3.11）与前端区域布局 / 组件交互规范（原 SPEC 第 14 章），属于**随前端演进**的硬约束。

> 视觉设计语言（色彩、字阶、间距、token）以 [`../../frontend/design.md`](../../frontend/design.md)（亮色 v2.3.2）与 [`../../frontend/design.dark.md`](../../frontend/design.dark.md)（暗色 v1.4）为权威入口，本文件不重复定义。

## 1. 通用业务组件规范（原 SPEC 3.11）

> 以下组件为 多多贝 设计语言体系中的核心业务组件，已封装为跨页面复用的通用组件，所有开发必须优先使用。

### 1.1 MoneyDisplay 金额展示组件

**组件路径**：`@/components/MoneyDisplay/index.vue`

**用途**：统一展示金额数据，自动处理千分位格式化、货币符号、正负号及涨跌色。

**Props 定义**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `value` | `number \| string` | **必填** | 金额数值 |
| `currency` | `string` | `'¥'` | 货币符号 |
| `showSign` | `boolean` | `true` | 是否显示正负号（`+`/`-`） |
| `showCurrency` | `boolean` | `true` | 是否显示货币符号 |
| `precision` | `number` | `2` | 小数位数 |
| `autoColor` | `boolean` | `true` | 是否根据正负自动着色（涨红跌绿） |
| `customColor` | `string` | `''` | 自定义颜色（覆盖自动着色） |
| `suffix` | `string` | `''` | 后缀文本（如 `'万'`、`'%'`） |

**使用示例**：

```vue
<MoneyDisplay :value="12345.67" />                 <!-- +¥12,345.67 (红色) -->
<MoneyDisplay :value="-1234.56" />                <!-- -¥1,234.56 (绿色) -->
<MoneyDisplay :value="0" />                       <!-- ¥0.00 (灰色) -->
<MoneyDisplay :value="123456789" :showSign="false" />  <!-- ¥123,456,789.00 -->
```

**编码红线**：

- 所有金额展示**必须**使用 `MoneyDisplay` 组件，禁止手写 &#123;&#123; amount.toLocaleString() &#125;&#125; 等格式化逻辑
- 金额数字**必须**通过 `value` prop 传入，禁止在组件内部自行计算

### 1.2 RiseFallText 涨跌文本组件

**组件路径**：`@/components/RiseFallText/index.vue`

**用途**：统一展示涨跌幅/收益率，自动处理正负号、百分比格式及涨跌色。

**Props 定义**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `value` | `number \| string` | **必填** | 数值（正数=涨，负数=跌） |
| `suffix` | `string` | `'%'` | 后缀文本 |
| `showSign` | `boolean` | `true` | 是否显示正负号（`+`/`-`） |
| `precision` | `number` | `2` | 小数位数 |
| `autoColor` | `boolean` | `true` | 是否根据正负自动着色（涨红跌绿） |
| `customColor` | `string` | `''` | 自定义颜色（覆盖自动着色） |
| `size` | `'sm' \| 'md' \| 'lg'` | `'md'` | 尺寸 |

**使用示例**：

```vue
<RiseFallText :value="12.34" />                  <!-- +12.34% (红色) -->
<RiseFallText :value="-5.67" />                  <!-- -5.67% (绿色) -->
<RiseFallText :value="0" />                      <!-- 0.00% (灰色) -->
<RiseFallText :value="12.34" size="lg" />        <!-- +12.34% (大号) -->
```

**编码红线**：

- 所有收益率/涨跌幅展示**必须**使用 `RiseFallText` 组件，禁止手写 `+12.34%` 等硬编码格式
- 数值**必须**通过 `value` prop 传入，禁止在组件内部自行计算

### 1.3 组件导入规范

所有通用业务组件统一从 `@/components` 目录导入：

```typescript
import MoneyDisplay from '@/components/MoneyDisplay/index.vue';
import RiseFallText from '@/components/RiseFallText/index.vue';
```

**禁止行为**：

- 禁止在业务页面中手写金额/涨跌的格式化逻辑
- 禁止使用 Emoji 或非 Iconify 图标替代组件符号
- 禁止在组件外部自行实现涨红跌绿的颜色判断逻辑

### 1.4 ProductDisplay 产品信息复合列组件

**组件路径**：`@/components/ProductDisplay/index.vue`

**用途**：统一展示各类资产/持仓的复合列信息（名称、代码、类型标签）。全站表格中**必须**使用此组件替换手写的 `div` 堆叠，确保 `SPEC 3.8` 规范落地。

**Props 定义**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | `string` | 资产/持仓名称 |
| `symbol` | `string` | 资产/持仓代码 |
| `typeLabel` | `string` | 资产类型中文标签 |

**编码红线**：

- 所有持仓或资产表格列表的"产品信息"列，**必须**使用 `ProductDisplay` 组件，禁止手写 HTML 排版。
- 组件本身仅负责展示，数据必须由父组件传入，**禁止在组件内部拉取数据**。

**使用示例**：`<ProductDisplay :name="row.name" :symbol="row.symbol" :type-label="row.type_label" />`

### 1.5 usePageRefresh 全局数据同步组合式函数

**文件路径**：`@/composables/usePageRefresh.ts`

**用途**：解决全局记账操作（如简记弹窗提交）后，当前页面（如账户详情页、全面盘点页）不刷新数据的核心痛点。

**编码红线**：

- 所有需要监听数据变更并自动刷新的页面，直接引入该 Hook 并传入回调即可，**严禁在各个页面手写 `emitter.on` 进行挂载和销毁**，避免内存泄漏。

**使用示例**：`usePageRefresh(async () => { await loadHoldings(); await loadTransactions(); });`

**核心策略**：采用 `mitt` 事件总线，在 `App.vue` 触发消息，由组合式函数在子组件销毁时自动清理监听器，完全符合"防错设计"原则。

## 2. 前端区域布局与组件交互规范（原 SPEC 第 14 章）

本章节规范专门用于约束 Vue 前端页面的**布局结构、组件渲染策略与交互反馈**，与 [`../../frontend/design.md`](../../frontend/design.md)（视觉风格）和本规范体系（docs/spec/，业务逻辑）互补，形成从"UI 样式"到"组件架构"的完整闭环。

### 2.1 仪表盘区块"外部标题"统一结构

所有仪表盘卡片区块，强制采用 **「外部独立标题行 + 下方独立内容卡片」** 的排布结构。

- **标题外置**：区块标题（`<h3>`）必须位于卡片容器的外部，与内容卡片构成 `flex-col` 的上下堆叠关系。
- **组件剥离**：包含内部标题的组件（如原 `WatchlistWidget`），必须在父组件中剥离其内部标题，将其重构为"纯渲染容器"。外部标题与操作按钮统一由父级页面掌控。
- **上沿强制对齐**：所有外部标题行的容器高度强制统一为 `h-8`，并使用 `items-center` 布局，确保相邻区块标题和操作按钮处于同一条绝对水平线上。

### 2.2 卡片等高与留白填充强制规则

为解决数据多寡导致卡片高度不一、底部出现"断崖留白"的问题：

- **等高强制拉伸**：左右双栏布局容器（如使用 `grid-cols-12`）**必须**使用默认的 `items-stretch` 属性，使左右两侧的卡片容器物理高度保持一致。
- **内部空间吸收**：右侧卡片内部必须使用 `h-full flex flex-col flex-1` 的结构组合。当外层被强制拉伸时，内部元素应利用 `flex-1` 吸收多余的高度空间，防止出现底部空白断层。
- **数据列表撑满**：列表/表格组件（如 `WatchlistWidget`）在最外层加入 `flex-1 min-h-[80px]`，确保即使只有 1 条数据，组件底部的空白也会被自动吸满，绝不出现露底。

### 2.3 图表防拉伸变形约束

为避免左侧列表加载大量数据导致右侧长条图表被拉成"细长条"：

- **高度封顶**：右侧长条/柱状图表（如风险热力图）内部容器必须设置 `max-h-[240px]` 硬性封顶，阻止无限拉伸。
- **垂直居中**：高度封顶的图表外层需使用 `flex-1 flex items-center justify-center` 容器包裹。这样在卡片被撑高时，图表会保持在规定高度范围内，并在卡片空间内**垂直居中**，上下留白均匀。

### 2.4 入场动画与"呼吸感"交互规范

- **入场级联动画**：核心卡片应添加 `fadeUp` 级联淡入动画。
  - 参数：`opacity: 0 → 1`, `transform: translateY(24px) → 0`, 时长为 `0.6s cubic-bezier(0.4, 0, 0.2, 1)`。
  - 延迟：多张卡片依次使用 `nth-child` 设置 `animation-delay: 0.05s` 至 `0.25s` 递增。
- **悬浮物理反馈**：所有卡片 `:hover` 时，使用 `transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1)` 丝滑过渡，执行 `transform: translateY(-3px)` 轻微上浮，并配合 `box-shadow: var(--shadow-float)` 加深阴影。
- **禁止内联重绘**：**禁止在 `<template>` 中使用 `@mouseenter` 和 `@mouseleave` 强行修改内联 `style.backgroundColor`**。所有交互反馈必须由纯 CSS 类（如 `:hover` 和 `transition`）驱动，避免强制重绘。

### 2.5 组件剥离与外部统管原则

当一个组件（如 `WatchlistWidget`）因为业务逻辑（如区分"置顶资产"和"持仓市值最大资产"）内部包含了动态标题时，**正确的架构是父组件剥离其标题，组件自身只保留内容区。**

- 父组件在外部统揽标题与按钮区的渲染，使其与页面其他区块的"外部标题"结构保持一致。
- 组件内部通过 `props` 接收父级传递的数据配置（如显示何种说明文案），保持自身作为"纯渲染容器"的高内聚。
