# 资产透视区块（Issue #1014）实现设计

> 关联需求：<https://github.com/imoyao/fundmate/issues/1014>
> 设计规范：<https://github.com/imoyao/fundmate/blob/dev/frontend/design.md>

## 1. 可行性评估

**可以做，且无需新增后端接口。**

数据全部来自现有聚合出口 `getDistributions()`（`/api/summary/distributions/`），该接口已返回多维分布：
`type_distribution` / `allocation_distribution` / `market_distribution` / `account_distribution` / `category_distribution` / `liability_distribution`。

后端 `summary_service.build_distributions()` 已按 `TYPE_LABELS`、`ALLOCATION_LABELS` 等映射为中文标签（股票/基金/可转债/ETF/虚拟货币/银行存款、长期/短期/战术/其他），前端直接渲染即可。

## 2. 数据维度映射

| 环形图 | 数据维度 | 说明 |
|--------|----------|------|
| 资产分布 | `type_distribution` | 资产大类市值占比：股票/基金/可转债/ETF/虚拟货币/银行存款/其他 |
| 基金类型分布 | `allocation_distribution` | 配置目标市值占比：长期/短期/战术/其他 |

> **偏差说明（已评估）**：后端 `distributions` 当前**没有独立的 `fund_type` 维度**（基金子类：货币型/股票型/混合型/债券型/QDII）。
> 严格意义的"基金类型分布"需要新增 `fund_type_distribution` 聚合维度，属于新接口范畴。
> 本 issue 明确"数据来自 positions 聚合，无需新后端接口（或复用现有聚合）"，因此以最接近且现成的
> **配置目标（allocation）** 维度呈现"基金类型分布"视角。若后续需要严格的基金子类分布，再单独开 issue 在 `summary_service` 增加 `fund_type_distribution`。

## 3. 设计规范遵循（frontend/design.md）

- **区块标题**：复用 `SectionHeader`（设计系统强制复用，禁止手写 `<h2>/<h3>`）。
- **卡片容器**：复用 `CardBlock`（统一 `--bg-card / --radius-lg / --border-light / --shadow-raised / --space-standard`，禁止手写卡片样式）。
- **环形图**：复用 `AssetAllocationDonut.vue`，内部配色走 `--chart-01~08` 语义变量、带空持仓友好态。
- **禁止硬编码颜色/样式**：所有视觉走设计系统 CSS 变量与强制复用组件。

## 4. 组件结构

- 新增 `frontend/src/components/AssetInsight/AssetInsightPanel.vue`（资产透视区块）
  - 自包含：内部调用 `getDistributions()`，含 `loading` / 空态。
  - 内联两张 `AssetAllocationDonut`：`资产分布`、`基金类型分布`，响应式两列（移动端单列）。
- 接入点：`frontend/src/views/asset/AssetPanorama.vue`（资产总览）在桑基图区块之后新增该区块。

## 5. 验收标准

- [x] 两张环形图正常渲染（type / allocation 维度自动取色）。
- [x] 配色与 design.md 图表配色板（`--chart-01~08`）一致。
- [x] 空持仓 / 加载中有友好态（`AssetAllocationDonut` 内置）。
- [x] 全程未硬编码颜色与样式，复用设计系统组件。
