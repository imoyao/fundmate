# 前端接口整理方案（RESTful 聚合接口替换）

> 内部备忘（不进文档站）。日期：2026-08-09。
> 背景：用户指出前端分布饼图用 `per_page: 500` 全量拉取 + 前端聚合"肯定是不对的"（此前因无接口/接口不完善才如此实现），要求按 RESTful 经典方式实现接口，并整理前端"调用无用接口 / 高消耗接口"。
>
> **实况修正（2026-08-09 实证）**：线上「资产总览」路由 `/panorama` 实际组件是 **`AssetPanorama.vue`**（`frontend/src/router/modules/home.ts:47-56`）；`Overview.vue` 无路由、无任何 import 引用（`src/router/utils.ts` 的 glob 仅做组件映射、不为每个文件生成路由），是**历史遗留死文件**（旧版实现，含饼图/柱状图/自建桑基图/假数据瀑布图）。批次 2 目标页面以此为准修正。

## 1. 现状问题盘点

### 1.1 全量拉取 + 前端聚合（2 页 + 1 死文件，`per_page: 500`）

| 页面 | 状态 | 调用 | 前端聚合消费点 |
|---|---|---|---|
| **AssetPanorama.vue**（线上资产总览，路由 /panorama） | 在用 | `getPositions(500)` + `getAssets(500)` + `getSummary()` + `getSankeyData()` + `getLedgers()` | 大类构成 `assetBalanceRows`（L541 区）、负债明细 `liabilityBalanceRows`、type/account/allocation 分组（含 items 明细）、**瀑布图（L691-780 硬编码假数据）** |
| **Overview.vue**（资产概览） | **死文件** | `getPositions(500)` + `getAssets(500)` + `getSummary()` | 桑基图（L468-588）、配置目标分组 `allocationGroups`（L590-614）、维度分组列表 `dimensionGroups`（L620-655）、明细表格（L657-666）、**瀑布图（L687-700 假数据）**、饼图+柱状图 `updatePieChart`（L798-825）——全部无人消费 |
| **inventory/index.vue**（全面盘点） | 在用 | `getPositions(500)` + `getAssets(major_category, 500)` | **前端 slice 分页**（L748-752，后端已有分页却全量拉再切）、investment 分组（L754-789）、分类汇总 `getCategoryTotal`（L770 区） |

### 1.2 硬编码假数据（1 处在用 + 1 处死文件，用户可见）

- **AssetPanorama 瀑布图**：`initWaterfallChart`（L691-780）硬编码（上期末 280 万 → 流动资金 -233251 → … → 本期末），`allPositions.length === 0` 时直接不画。
- Overview 瀑布图（L687-700）同源硬编码，但所在文件为死文件，无用户可见影响。
- 性质等同 P0-2「热门卡片假盈亏」，属数据正确性问题。

### 1.3 汇率计算散落前端

- `EXCHANGE_RATES {CNY/USD/HKD}` 在 Overview / AssetPanorama / inventory 多处硬编码，前端算 `marketValue = quantity × price × rate`、`pnl`。
- 后端 `summary_service.py` 已有同款汇率表——前后端重复，口径漂移风险。

### 1.4 后端聚合能力缺口

已有：`/api/positions/`（分页 + `group_by=account`）、`/api/assets/`（分页）、`/api/summary/`（全家庭 total + `market_distribution`）、`/api/ledgers/overview/`、`/api/ledgers/<id>/summary/`（含新 `type_distribution`）。

缺口：家庭级**多维分布**（type/allocation/market/account）、**资产大类分类汇总**（含负债）、**瀑布图数据**。

## 2. 后端接口设计（RESTful）

新增 `GET /api/summary/distributions/`（家庭维度，一次返回全维度，避免多次请求）：

```json
{
  "type_distribution":       [{"name": "股票", "value": 12345.0}, ...],
  "allocation_distribution": [{"name": "活钱", "value": ...}, ...],
  "market_distribution":     [{"name": "A股", "value": ...}, ...],
  "account_distribution":    [{"name": "华泰证券", "value": ...}, ...],
  "category_distribution":   [{"name": "投资理财", "value": ...}, ...],
  "liability_distribution":  [{"name": "信用卡", "value": ...}, ...],
  "total_assets":       12345.0,
  "total_liabilities":  2345.0,
  "net_worth":          10000.0,
  "positions_total_mv": 8000.0
}
```

- 聚合全部在后端（沿用 cents 整数精度 + `Money` 换算，汇率统一后端 `summary_service.EXCHANGE_RATES`）。
- 明细表格 / 展开列表仍用现有**分页**接口（`getPositions`/`getAssets` 已支持 `page/per_page`），不再 500 全量。

### 维度分组后端化（批次 2b，需用户确认差异展示后实施）

- 现状：AssetPanorama `detailView` 的 type/account/allocation 分组卡片，items 明细由前端对 `per_page:500` 全量数据做 `groupBy` + 市值/盈亏换算（`EXCHANGE_RATES`）。
- 设计（纯新增、向后兼容）：`GET /api/summary/groups/?dimension=type|account|allocation`
  ```json
  [
    {"name": "股票", "total": 12345.0, "total_pnl": 234.0,
     "items": [{"id": 1, "name": "茅台", "symbol": "SH600519", "type_label": "股票",
                "allocation_label": "长期增值", "market_value": 8000.0, "pnl": 120.0, ...}]},
    ...
  ]
  ```
  - `type` / `allocation`：仅持仓，按 `TYPE_LABELS` / `ALLOCATION_LABELS` 分组；`account`：持仓 + 非负债通用资产混合分组（同现状 accountDetailGroups）。
  - 汇率换算、市值/盈亏全在后端（`Money` + `EXCHANGE_RATES`），前端不再保留 `EXCHANGE_RATES`（批次 5 随之完成）。
  - 前端：`detailView` 切换时拉对应 dimension，展示 items 明细；点击跳转逻辑（type→investment 页、account→ledgers）不变。
- 依赖关系：只有做完 2b 才能删 AssetPanorama 的 `EXCHANGE_RATES` 与 `per_page:500` positions/assets 拉取。

### 瀑布图真实化

- 现状无期初资产快照（真实"期间变化"依赖 P1-20 定时任务建历史表）。
- **本阶段方案**：改为「总资产构成瀑布」——从 0 起点 → 各大类现值（涨色）→ 负债（跌色）→ 净资产，数据真实、无需历史。
- **P1-20 之后**：真实"上期末→本期末"变化（需新增历史快照表）。

## 3. 前端替换分批计划

| 批次 | 内容 | 状态 |
|---|---|---|
| 1 | detail.vue 环形图 → 后端 `type_distribution` | ✅ 已完成（commit `7fda719`） |
| 2 | 后端 `GET /api/summary/distributions/`；AssetPanorama 大类构成/负债明细/瀑布图 → 消费该接口（去假数据）；api/summary.ts 增 `getDistributions` | ✅ 已完成（commit `4014daf`） |
| 2b | 后端 `GET /api/summary/groups/?dimension=type\|account\|allocation`（含 items 明细）；AssetPanorama 维度分组卡片消费该接口；删前端 `EXCHANGE_RATES` 与 positions/assets 全量拉取 | ✅ 已完成（后端 578 passed + typecheck 通过，待提交） |
| 3 | inventory 前端 slice 分页 → 后端真实分页；分组走后端 | 待核准 |
| 4 | Overview.vue 死文件处置（删除需备份 + 确认） | 待讨论 |
| 5 | 移除其余前端 `EXCHANGE_RATES` 散落（inventory，汇率收敛后端） | 待 2b 落地后 |

**新增发现（2026-08-09，批次 2b 实证）**：AssetPanorama 总览大卡片「总资产（本月）」下「较上月 / 较去年同期」为硬编码假数据 `12.3%` / `8.7%`（AssetPanorama.vue L50/L54），与瀑布图假数据同性质（用户可见）；真实同比需历史快照（P1-20），当前无数据源，**列入后续处理**（方案未定：无历史数据时改为隐藏或显示"—"）。

每批次独立提交、独立验证（后端 pytest + 前端 typecheck + build）。

## 4. 四象限分类

| 项 | 象限 | 说明 |
|---|---|---|
| 瀑布图假数据 | Ⅰ 重要且紧急 | 用户可见假数据，等同 P0-2 |
| detail.vue 环形图 | Ⅱ | ✅ 已完成 |
| 全量拉取整理 | Ⅱ 重要不紧急 | 性能 + 架构一致性 |
| 汇率散落 | Ⅱ | 前后端口径收敛 |

## 5. 风险与回滚

- 契约：`distributions` 为**纯新增**接口，旧接口与字段不动，向后兼容。
- 每批次独立可回滚（前端回退旧聚合逻辑 / 后端撤接口）。
- 视觉：图表形态不变，仅数据来源与正确性变化；批次 2/3 涉及成熟页面数据源切换，按「前端重构纪律」实施前已示差异。
