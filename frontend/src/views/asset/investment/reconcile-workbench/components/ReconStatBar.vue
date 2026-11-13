<template>
  <!-- 队列总览指标：统一走 MetricGrid / MetricCard（不再自绘统计条）。
       旧页面把 `level="待处理"` 传给温度档徽标、把「可撤销（P2 接入）」写进
       caption，都是把开发语义塞进用户界面的例子，这里一并去掉。 -->
  <div class="recon-stat">
    <MetricGrid>
      <MetricCard
        title="待办事项"
        :value="openItems"
        unit="项"
        :featured="true"
      />
      <MetricCard title="可直接处理" :value="readyItems" unit="项" />
      <MetricCard title="涉及流水" :value="openRecords" unit="条" />
    </MetricGrid>
  </div>
</template>

<script setup lang="ts">
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";

defineOptions({ name: "ReconStatBar" });

defineProps<{
  openItems: number;
  readyItems: number;
  openRecords: number;
}>();
</script>

<style scoped>
.recon-stat {
  margin-bottom: var(--space-standard);
}
</style>
