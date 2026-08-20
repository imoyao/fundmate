<script setup lang="ts">
import { computed } from "vue";
import { ArrowDown, ArrowUp } from "@element-plus/icons-vue";
import type { RealtimeQuotesReturn } from "@/composables/useRealtimeQuotes";

/**
 * 自选实时估值汇总条（状态指示 + 刷新档位 + 估值卡），从 index.vue 抽出（2026-08-20）。
 * 仅展示用：realtime 实例由页面注入，本组件不发起任何请求。
 */
const props = defineProps<{
  realtime: RealtimeQuotesReturn;
  refreshing: boolean;
}>();

const emit = defineEmits<{
  (e: "interval-change", value: string | number | boolean): void;
  (e: "manual-refresh"): void;
}>();

const summary = computed(() => props.realtime.summary.value);
const hasValid = computed(
  () => !!summary.value && (summary.value.totalMarketValue ?? 0) > 0
);
const profitClass = computed(() => {
  const v = summary.value?.totalPnl ?? 0;
  if (v > 0) return "text-up";
  if (v < 0) return "text-down";
  return "text-flat";
});
const profitArrow = computed(() =>
  (summary.value?.totalPnl ?? 0) >= 0 ? ArrowUp : ArrowDown
);
const intervalOptions = [
  { label: "15s", value: 15 },
  { label: "30s", value: 30 },
  { label: "60s", value: 60 },
  { label: "90s", value: 90 }
];
</script>

<template>
  <div class="summary-bar">
    <div class="flex items-center gap-2 mb-2">
      <span class="status-dot" :class="`status-${realtime.status.value}`" />
      <span class="status-text">
        {{ realtime.status.value === "trading" ? "实时行情" : "休市/收盘" }}
      </span>
      <span v-if="realtime.lastUpdateTime.value" class="update-time">
        更新于 {{ realtime.lastUpdateTime.value }}
      </span>
      <el-segmented
        :model-value="realtime.refreshInterval.value"
        size="small"
        :options="intervalOptions"
        class="refresh-segmented"
        @change="emit('interval-change', $event)"
      />
      <el-button
        text
        :loading="refreshing"
        :style="{ color: 'var(--text-secondary)' }"
        @click="emit('manual-refresh')"
      >
        刷新
      </el-button>
    </div>

    <div v-if="hasValid" class="summary-cards flex gap-4">
      <div class="summary-card">
        <div class="label">总市值</div>
        <div class="value">{{ summary?.totalMarketValue?.toFixed(2) }}</div>
      </div>
      <div class="summary-card">
        <div class="label">总成本</div>
        <div class="value">{{ summary?.totalCost?.toFixed(2) }}</div>
      </div>
      <div class="summary-card">
        <div class="label">总盈亏</div>
        <div class="value" :class="profitClass">
          <el-icon><component :is="profitArrow" /></el-icon>
          {{ summary?.totalPnl?.toFixed(2) }}
          <span class="pct">({{ summary?.totalPnlPercent?.toFixed(2) }}%)</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.summary-bar {
  margin-bottom: 12px;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.status-trading {
  background: #16a34a;
}
.status-closed,
.status-idle {
  background: var(--text-secondary);
}
.status-error {
  background: #dc2626;
}
.status-text {
  font-weight: 600;
}
.update-time {
  font-size: 12px;
  color: var(--text-secondary);
}
.summary-card {
  background: var(--bg-elevated, #f8fafc);
  border-radius: 8px;
  padding: 8px 12px;
}
.summary-card .label {
  font-size: 12px;
  color: var(--text-secondary);
}
.summary-card .value {
  font-size: 16px;
  font-weight: 700;
}
.text-up {
  color: #dc2626;
}
.text-down {
  color: #16a34a;
}
.text-flat {
  color: var(--text-secondary);
}
.pct {
  font-size: 12px;
  opacity: 0.8;
}
</style>
