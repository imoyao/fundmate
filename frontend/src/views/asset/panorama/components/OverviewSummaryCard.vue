<!--
  OverviewSummaryCard · 资产全景顶部两张并排卡（#980 批 B6）

  左：总资产 / 环比同比 / 负债·净资产·盈亏三列。右：资产大类构成图 ⇄ 收益日历原地切换。
  两张卡等高并排，卡片体锁死 280px（#2033）——所以外层 `el-col` 的 `h-full`
  与卡片自身的 `h-full` 都不能省。

  #980 批 B6 拆分后本文件只剩「两列排布」：
  - 左卡（hero / 三指标 / 全部对应样式）→ `OverviewAssetsCard`
  - 右卡（两态切换 / echarts 生命周期 / 280px 卡片体）→ `OverviewInsightCard`
  - 两卡共用的壳（底色 / 描边 / 阴影 / hover）→ `_summary-card.scss`
-->
<template>
  <el-row :gutter="16">
    <el-col :xs="24" :md="12" class="mb-4 md:mb-0">
      <OverviewAssetsCard
        :total-assets="totalAssets"
        :total-liabilities="totalLiabilities"
        :total-pnl="totalPnl"
        :latest-snapshot="latestSnapshot"
      />
    </el-col>

    <el-col :xs="24" :md="12">
      <OverviewInsightCard :distributions="distributions" />
    </el-col>
  </el-row>
</template>

<script setup lang="ts">
import type { AssetSnapshotItem, DistributionsData } from "@/api/summary";
import OverviewAssetsCard from "./OverviewAssetsCard.vue";
import OverviewInsightCard from "./OverviewInsightCard.vue";

defineOptions({ name: "OverviewSummaryCard" });

defineProps<{
  totalAssets: number;
  totalLiabilities: number;
  totalPnl: number;
  latestSnapshot: AssetSnapshotItem | null;
  distributions: DistributionsData | null;
}>();
</script>
