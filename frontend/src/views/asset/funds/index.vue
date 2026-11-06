<script setup lang="ts">
import AggregationPage from "@/components/Aggregation/AggregationPage.vue";
import { getFundAggregation } from "@/api/ledger";

/**
 * 基金（含 E 账户、货币基金）聚合下钻页（#1101 / #1133 / #1266）。
 *
 * 主体逻辑已抽离到 AggregationPage，本文件只做编排配置：
 * 数据源 fetcher、标题/副标题、类型筛选 Tab、空态文案。
 */
defineOptions({ name: "AssetFunds" });
</script>

<template>
  <AggregationPage
    :fetcher="getFundAggregation"
    title="基金"
    subtitle="跨账本聚合的全部基金持仓，含货币基金与 E 账户份额"
    :show-type-tab="true"
    type-tab-label="基金类型"
    empty-title="还没有基金持仓"
    empty-hint="导入基金账户对账单或手动记一笔后，这里会展示全部基金"
  />
</template>
