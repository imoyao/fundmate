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
        v-for="n in 6"
        :key="n"
        class="h-16 rounded animate-pulse"
        :style="{ backgroundColor: 'var(--bg-soft)' }"
      />
    </div>
    <!-- 有数据：两组（资产健康度 4 格 + 财富自由度 2 格） -->
    <div v-else-if="view" class="barometer">
      <div class="barometer__group">
        <h4 class="barometer__group-title">资产健康度</h4>
        <div class="barometer__grid">
          <div
            v-for="metric in assetMetrics"
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
      </div>

      <div class="barometer__group">
        <h4 class="barometer__group-title">
          财富自由度
          <span class="barometer__group-tag">可投资资产 × 3% ÷ 年收支</span>
        </h4>
        <div class="barometer__grid barometer__grid--freedom">
          <div
            v-for="metric in freedomMetrics"
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
                >{{
                  metric.ratio != null ? ratioText(metric.ratio) : "—"
                }}</span
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
            <span
              v-if="metric.needsConfig"
              class="health-metric__config"
              :style="{ color: 'var(--brand-ink)' }"
            >
              在个人中心填入年支出/年收入后显示 →
            </span>
            <span class="health-metric__note">{{ metric.amountNote }}</span>
          </div>
        </div>
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
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import type { FinancialHealthView } from "../composables/financialHealth";

defineOptions({ name: "WelcomeBarometer" });

const props = defineProps<{
  view: FinancialHealthView | null;
  loading?: boolean;
  error?: boolean;
}>();

const emit = defineEmits<{ retry: [] }>();

const assetMetrics = computed(() =>
  (props.view?.metrics ?? []).filter(m => m.group === "asset")
);
const freedomMetrics = computed(() =>
  (props.view?.metrics ?? []).filter(m => m.group === "freedom")
);

/** 比率文案：null → 「—」（算不了，不是 0%）；≥10 取整、否则 1 位小数 */
const ratioText = (ratio: number | null): string => {
  if (ratio == null || !Number.isFinite(ratio)) return "—";
  return `${ratio >= 10 ? Math.round(ratio) : Math.round(ratio * 10) / 10}%`;
};
</script>

<style lang="scss" scoped>
/* 六项是健康度观察值，不是当日涨跌：比率用品牌色，禁止混用涨跌语义色。 */
.barometer {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.barometer__group-title {
  display: flex;
  gap: 8px;
  align-items: baseline;
  margin: 0 0 12px;
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-secondary);
}

.barometer__group-tag {
  font-size: var(--text-label);
  font-weight: 400;
  color: var(--text-tertiary-ink);
}

.barometer__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px 24px;
}

.barometer__grid--freedom {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

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
.health-metric__config,
.health-metric__warn {
  font-size: var(--text-label);
  line-height: 1.4;
  color: var(--text-tertiary-ink);
}

.health-metric__note {
  opacity: 0.85;
}

.health-metric__config {
  font-weight: 500;
}

.health-metric__warn {
  margin: 12px 0 0;
}
</style>
