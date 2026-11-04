<script setup lang="ts">
import {
  fmtPct,
  riseFallClass,
  type ReturnMetric,
  type RiskMetric
} from "./advisorModel";

/**
 * 收益表现 + 风险指标（#980 拆分）。
 *
 * 两块排版同构但**着色规则不同**：收益走文字级涨跌色（涨红跌绿），
 * 风险指标一律中性色——回撤是负数，套绿会读成「亏得少」。
 */
defineProps<{
  returns: ReturnMetric[];
  risks: RiskMetric[];
}>();
</script>

<template>
  <div v-if="returns.length" class="advisor-section__metrics">
    <h4 class="advisor-section__metrics-title">收益表现</h4>
    <ul class="advisor-section__metrics-list">
      <li v-for="m in returns" :key="m.label" class="advisor-section__metric">
        <span class="advisor-section__metric-label">{{ m.label }}</span>
        <span
          class="advisor-section__metric-value"
          :class="riseFallClass(m.value)"
        >
          {{ fmtPct(m.value) }}
        </span>
      </li>
    </ul>
  </div>

  <div v-if="risks.length" class="advisor-section__metrics">
    <h4 class="advisor-section__metrics-title">风险指标</h4>
    <ul class="advisor-section__metrics-list">
      <li v-for="m in risks" :key="m.label" class="advisor-section__metric">
        <span class="advisor-section__metric-label">{{ m.label }}</span>
        <span class="advisor-section__metric-value">{{ m.text }}</span>
      </li>
    </ul>
  </div>
</template>

<style lang="scss" scoped>
@use "./advisor-base";

.advisor-section__metrics {
  margin-top: var(--space-3);
}

.advisor-section__metrics-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--space-3);
  padding: 0;
  margin: 0;
  list-style: none;
}

.advisor-section__metric {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.advisor-section__metric-label {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.advisor-section__metric-value {
  font-size: var(--text-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

/* 文字级涨跌色（仓库专为文字维护的 AA 对比度色，勿用图形级 --color-rise/fall） */
.advisor-section__metric-value.is-rise {
  color: var(--color-rise-ink);
}

.advisor-section__metric-value.is-fall {
  color: var(--color-fall-ink);
}
</style>
