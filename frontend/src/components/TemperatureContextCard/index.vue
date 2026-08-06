<!-- ============================================================
  TemperatureContextCard.vue
  温度上下文解读卡 · 多倍贝设计语言 v2.3.3

  用途：
  - 承接 TemperatureGaugeCard 拆出的文字信息：温度等级、恐惧贪婪指数、
    短/中/长期温度。
  - 与圆环卡并排使用，避免单卡内右侧留白；同时保证所有 tag 位置统一。

  设计约束：
  - 等级标签固定于标题行右侧，与 MetricCard / TemperatureGaugeCard 统一。
  - 不展示圆环，只做文本与数字的层级排列。
  ============================================================ -->

<template>
  <div class="context-card">
    <div class="context-card__title-row">
      <span class="context-card__title">温度解读</span>
      <TemperatureLevelBadge v-if="levelLabel" :level="levelLabel" size="sm" />
    </div>

    <div class="context-card__body">
      <div v-if="fgValue != null" class="context-item">
        <span class="context-item__label">恐贪指数</span>
        <div class="context-item__value-row">
          <span class="context-item__value">{{ fgValue }}</span>
          <span class="context-item__unit">分</span>
          <span class="context-item__hint">{{
            fearGreedLabel || fearGreedText
          }}</span>
        </div>
      </div>

      <div v-if="periodList.length" class="context-periods">
        <div v-for="p in periodList" :key="p.label" class="context-period">
          <span
            class="context-period__dot"
            :style="{ background: tempColor(p.value) }"
          />
          <span class="context-period__label">{{ p.label }}</span>
          <span class="context-period__value">{{ formatTemp(p.value) }}</span>
        </div>
      </div>
    </div>

    <div v-if="caption" class="context-card__caption">{{ caption }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import TemperatureLevelBadge from "@/components/TemperatureLevelBadge/index.vue";

export interface TemperatureContextCardProps {
  /** 综合温度，用于自动推断等级标签；不传则隐藏标签 */
  temperature?: number | null;

  /** 恐惧贪婪指数 */
  fearGreed?: number | null;

  /** 恐惧贪婪指数文字，如「极度恐惧」 */
  fearGreedLabel?: string;

  /** 短中长期温度数组 */
  periods?: Array<{ label: string; value: number | null }>;

  /** 卡片底部说明 */
  caption?: string;
}

const props = withDefaults(defineProps<TemperatureContextCardProps>(), {
  temperature: null,
  fearGreed: null,
  fearGreedLabel: "",
  periods: () => [],
  caption: ""
});

const levelLabel = computed(() => {
  const v = props.temperature;
  if (v === null || v === undefined || Number.isNaN(v)) return "";
  if (v < 40) return "偏低·偏冷";
  if (v > 60) return "偏高·偏热";
  return "正常·温和";
});

const fgValue = computed(() => {
  const v = props.fearGreed;
  if (v === null || v === undefined || Number.isNaN(v)) return null;
  return Math.round(v);
});

const fearGreedText = computed(() => {
  const v = fgValue.value;
  if (v === null) return "";
  if (v <= 20) return "极度恐惧";
  if (v <= 40) return "恐惧";
  if (v <= 60) return "中性";
  if (v <= 80) return "贪婪";
  return "极度贪婪";
});

const periodList = computed(() =>
  (props.periods || []).filter(p => p.value !== null && p.value !== undefined)
);

function formatTemp(v: number | null) {
  if (v === null || v === undefined || Number.isNaN(v)) return "--";
  return `${Number(v).toFixed(1)}°`;
}

function tempColor(v: number | null) {
  const num = v ?? 50;
  if (num < 40) return "var(--temp-low)";
  if (num > 60) return "var(--temp-high)";
  return "var(--temp-mid)";
}
</script>

<style scoped>
.context-card {
  display: flex;
  flex-direction: column;
  padding: 18px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
  transition:
    transform 150ms ease,
    box-shadow 150ms ease;
}

.context-card:hover {
  box-shadow: var(--shadow-float);
  transform: translateY(-3px);
}

.context-card__title-row {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.context-card__title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.context-card__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 18px;
  justify-content: center;
}

.context-item__label {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.context-item__value-row {
  display: flex;
  gap: 6px;
  align-items: baseline;
}

.context-item__value {
  font-family: var(--font-mono, "SF Mono", "JetBrains Mono", monospace);
  font-size: 28px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.context-item__unit {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-tertiary);
}

.context-item__hint {
  margin-left: 4px;
  font-size: 13px;
  color: var(--text-secondary);
}

.context-periods {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.context-period {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  padding: 6px 10px;
  background: var(--bg-soft);
  border-radius: var(--radius-pill);
}

.context-period__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.context-period__label {
  font-size: 12px;
  color: var(--text-secondary);
}

.context-period__value {
  font-family: var(--font-mono, "SF Mono", "JetBrains Mono", monospace);
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.context-card__caption {
  margin-top: 14px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-tertiary);
}
</style>
