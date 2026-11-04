<script setup lang="ts">
/**
 * 四态计数指标卡（#980 拆分）。
 *
 * 均分排布、待处理 featured 放大作锚点。四个口径全部来自后端 `summary`，
 * 前端不做任何二次计算——「共 N 条」用的是筛选后的列表长度，两者不是一回事。
 */
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";

defineProps<{
  /** 后端汇总；未加载时为 null，四张卡显示占位 */
  summary: {
    pending_count?: number;
    attributed_count?: number;
    ignored_count?: number;
    verified_count?: number;
  } | null;
}>();
</script>

<template>
  <MetricGrid class="summary-grid">
    <MetricCard
      title="待处理"
      :value="summary?.pending_count ?? null"
      featured
      caption="需要归因覆盖或忽略，优先处理"
    />
    <!-- 「已处理」而非「已归因」：attribution 是内部术语（2026-10-28 用户反馈），与筛选器同口径 -->
    <MetricCard
      title="已处理"
      :value="summary?.attributed_count ?? null"
      caption="快照已覆盖至对应渠道"
    />
    <MetricCard
      title="已忽略"
      :value="summary?.ignored_count ?? null"
      caption="导入时自动跳过，可重新对账恢复"
    />
    <MetricCard
      title="已核对"
      :value="summary?.verified_count ?? null"
      caption="与系统份额一致，无需处理"
    />
  </MetricGrid>
</template>

<style scoped>
/* ===== 指标卡区 ===== */
.summary-grid {
  margin-bottom: var(--space-standard);
}
</style>
