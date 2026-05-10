<template>
  <div class="p-4">
    <!-- 资产总览卡片 -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      <AssetCard
        v-for="asset in assets"
        :key="asset.type"
        :type="asset.type"
        :value="asset.value"
        :change="asset.change"
      />
    </div>

    <!-- 图表区域 -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
      <AssetDistributionChart />
      <ProfitTrendChart />
    </div>

    <!-- 账户信息 -->
    <AccountInfoSection />

    <!-- 交易记录 -->
    <TransactionTable />
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import AssetCard from "./components/AssetCard.vue";
import AssetDistributionChart from "./components/AssetDistributionChart.vue";
import ProfitTrendChart from "./components/ProfitTrendChart.vue";
import AccountInfoSection from "./components/AccountInfoSection.vue";
import TransactionTable from "./components/TransactionTable.vue";

const assets = ref([
  { type: "股票", value: "¥ 120,000", change: 2.5 },
  { type: "基金", value: "¥ 80,000", change: -1.2 },
  { type: "房地产", value: "¥ 500,000", change: 0.8 },
  { type: "贵金属", value: "¥ 30,000", change: 1.5 }
]);
</script>
