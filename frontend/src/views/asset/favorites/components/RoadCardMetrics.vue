<!--
  RoadCardMetrics · 未竟之蹊卡片的对比数据条（#980 批 B6 从 `RoadCard.vue` 抽出）

  数据由 `../helpers.cardMetrics` 派生（自选以来 / 近 N 日 / 持仓收益），
  本组件只负责「有就横排、没有就说明句」两态。

  ⚠️ 缺数据不许补 0：`cardMetrics` 只返回能算出来的格子，算不出的直接不出现
  （不是显示 `0.00%`）。空态说明句由调用方给（经理与其它实体说法不同），
  见 `roadCardModel.emptyMetricsText`。
-->
<template>
  <div v-if="metrics.length" class="road-metrics">
    <div v-for="metric in metrics" :key="metric.label" class="road-metric">
      <span class="road-metric__label">{{ metric.label }}</span>
      <span
        class="road-metric__value"
        :style="{ color: pctColorVar(metric.value) }"
      >
        {{ pctText(metric.value) }}
      </span>
    </div>
  </div>
  <p v-else class="road-metrics road-metrics--empty">
    {{ emptyText }}
  </p>
</template>

<script setup lang="ts">
import { pctColorVar, pctText, type RoadMetric } from "../helpers";

defineOptions({ name: "RoadCardMetrics" });

defineProps<{
  metrics: RoadMetric[];
  /** 空态说明句（经理 / 其它实体口径不同，由调用方决定） */
  emptyText: string;
}>();
</script>

<style scoped>
/* 对比数据条 */
.road-metrics {
  display: flex;
  gap: 14px;
  margin-top: 12px;
}

.road-metrics--empty {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.road-metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.road-metric__label {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.road-metric__value {
  font-family: var(--font-mono, monospace);
  font-size: var(--text-label);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
</style>
