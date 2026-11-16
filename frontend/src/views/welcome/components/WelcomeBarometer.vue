<!-- src/views/welcome/components/WelcomeBarometer.vue -->
<template>
  <CardBlock class="flex-1 card-hover">
    <!-- 加载中：骨架，不摆占位数字 -->
    <div
      v-if="loading && !view"
      class="grid grid-cols-2 gap-4"
      aria-busy="true"
    >
      <div
        v-for="n in 4"
        :key="n"
        class="h-16 rounded animate-pulse"
        :style="{ backgroundColor: 'var(--bg-soft)' }"
      />
    </div>
    <!-- 有数据：2×2 四格 -->
    <div
      v-else-if="view"
      class="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4"
    >
      <div
        v-for="metric in view.metrics"
        :key="metric.key"
        class="health-metric"
      >
        <div class="health-metric__head">
          <span class="health-metric__title">{{ metric.title }}</span>
          <span
            class="health-metric__ratio"
            :style="{
              color:
                metric.ratio != null
                  ? 'var(--brand-ink)'
                  : 'var(--text-tertiary-ink)'
            }"
            >{{ ratioText(metric.ratio) }}</span
          >
        </div>
        <MoneyDisplay
          class="health-metric__amount"
          :value="metric.amount"
          size="sm"
          :show-sign="false"
          :show-currency="true"
        />
        <span class="health-metric__basis">{{ metric.basis }}</span>
        <span class="health-metric__note">{{ metric.amountNote }}</span>
      </div>
    </div>
    <!-- 失败且一格都没加载出来：与资产卡同一处置，明确失败可重试 -->
    <div
      v-else
      class="flex flex-col items-center justify-center gap-2 text-center py-6"
    >
      <span class="text-sm" :style="{ color: 'var(--text-secondary)' }"
        >财务晴雨表加载失败</span
      >
      <button
        type="button"
        class="text-xs underline bg-transparent border-0 cursor-pointer"
        :style="{ color: 'var(--brand-ink)' }"
        @click="emit('retry')"
      >
        重试
      </button>
    </div>
    <p v-if="view && error" class="health-metric__warn">
      部分指标暂不可用（显示「—」），可
      <button
        type="button"
        class="underline bg-transparent border-0 cursor-pointer p-0"
        :style="{ color: 'var(--brand-ink)' }"
        @click="emit('retry')"
      >
        重试
      </button>
    </p>
  </CardBlock>
</template>

<script setup lang="ts">
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import type { FinancialHealthView } from "../composables/financialHealth";

defineOptions({ name: "WelcomeBarometer" });

defineProps<{
  view: FinancialHealthView | null;
  loading?: boolean;
  error?: boolean;
}>();

const emit = defineEmits<{ retry: [] }>();

/** 比率文案：null → 「—」（算不了，不是 0%）；≥10 取整、否则 1 位小数 */
const ratioText = (ratio: number | null): string => {
  if (ratio == null || !Number.isFinite(ratio)) return "—";
  return `${ratio >= 10 ? Math.round(ratio) : Math.round(ratio * 10) / 10}%`;
};
</script>

<style lang="scss" scoped>
/* 四项是健康度观察值，不是当日涨跌：比率用品牌色，禁止混用涨跌语义色。 */
.health-metric {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.health-metric__head {
  display: flex;
  gap: 8px;
  align-items: baseline;
  justify-content: space-between;
}

.health-metric__title {
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.health-metric__ratio {
  font-size: var(--text-body);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.health-metric__amount {
  font-variant-numeric: tabular-nums;
}

.health-metric__basis,
.health-metric__note,
.health-metric__warn {
  font-size: var(--text-label);
  line-height: 1.4;
  color: var(--text-tertiary-ink);
}

.health-metric__note {
  opacity: 0.85;
}

.health-metric__warn {
  margin: 12px 0 0;
}
</style>
