<script setup lang="ts">
import AggregationPage from "@/components/Aggregation/AggregationPage.vue";
import { getSecuritiesAggregation } from "@/api/ledger";

/**
 * 股票（含 ETF / 可转债）聚合下钻页（#1132 / #1133 / #1266）。
 *
 * 与 /funds 共用 AggregationPage（#1266 抽离），差异仅配置项：
 * 数据源 fetcher、标题/副标题、股票类型 Tab（按 股票/ETF/可转债 过滤）、空态文案。
 * 资产构成环形图由 AggregationPage 统一传入 fund_type_breakdown，
 * 后端按 asset_type 聚类（股票/ETF/可转债），与基金侧对齐（#1264）。
 */
defineOptions({ name: "AssetStocks" });
</script>

<template>
  <AggregationPage
    :fetcher="getSecuritiesAggregation"
    title="股票"
    subtitle="跨账本聚合的全部股票持仓，含 ETF 与可转债"
    :show-type-tab="true"
    type-tab-label="股票类型"
    :type-filter-field="'asset_type'"
    empty-title="还没有股票持仓"
    empty-hint="导入券商对账单或手动记一笔后，这里会展示全部股票、ETF 与可转债"
  />
</template>
