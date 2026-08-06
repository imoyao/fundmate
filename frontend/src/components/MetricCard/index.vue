<!--
  MetricCard · 指标卡（组件级设计约束，详见 frontend/design.md）
  - 统一「标题 / 大数字+小单位+等级标签 / 副文案」结构
  - 数字大、单位小的层级由组件保证，调用方只传数据
  props:
    - title: 指标名（如「股债性价比」）
    - value: 主数字（number | string | null）
    - unit:  单位/符号（如 "%"、"亿"、"°"），默认小字，与大数字同行
    - level: 等级文案，传给 TemperatureLevelBadge（如 "偏低"/"正常"）
    - caption: 副文案（如更新时间、说明）
    - featured: 放大主数字（用于核心指标）
    - loading/empty 状态由调用方控制，这里只负责空值展示 "--"
-->
<template>
  <div class="metric-card" :class="{ 'metric-card--featured': featured }">
    <div class="metric-card__title-row">
      <span class="metric-card__title">{{ title }}</span>
      <TemperatureLevelBadge
        v-if="level"
        :level="level"
        :size="featured ? 'md' : 'sm'"
        class="metric-card__badge"
      />
    </div>

    <div class="metric-card__body">
      <span class="metric-card__value">{{ displayValue }}</span>
      <span v-if="unit" class="metric-card__unit">{{ unit }}</span>
    </div>

    <div v-if="caption" class="metric-card__caption">{{ caption }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import TemperatureLevelBadge from "@/components/TemperatureLevelBadge/index.vue";

const props = withDefaults(
  defineProps<{
    title?: string;
    value?: number | string | null;
    unit?: string;
    level?: string;
    caption?: string;
    featured?: boolean;
  }>(),
  {
    title: "",
    value: null,
    unit: "",
    level: "",
    caption: "",
    featured: false
  }
);

const displayValue = computed(() => {
  const v = props.value;
  return v !== null && v !== undefined && v !== "" ? v : "--";
});
</script>

<style lang="scss" scoped>
@media (width <= 480px) {
  .metric-card__value {
    font-size: 26px;
  }

  .metric-card--featured .metric-card__value {
    font-size: 34px;
  }
}

.metric-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 104px;
  padding: 18px 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease;

  &:hover {
    box-shadow: var(--shadow-float);
    transform: translateY(-3px);
  }

  /* 标题行：标题 + 等级标签 横排 */
  &__title-row {
    display: flex;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
  }

  &__title {
    font-size: 13px;
    font-weight: 500;
    line-height: 1.4;
    color: var(--text-secondary);
  }

  &__body {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: baseline;
    margin-top: auto;
  }

  &__value {
    font-family: var(--font-mono);
    font-size: 30px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1.05;
    color: var(--text-primary);
    letter-spacing: -0.5px;
  }

  &__unit {
    font-size: 15px;
    font-weight: 500;
    color: var(--text-tertiary);
  }

  &__badge {
    flex-shrink: 0;
  }

  &__caption {
    font-size: 12px;
    line-height: 1.4;
    color: var(--text-tertiary);
  }

  /* featured：核心指标放大 */
  &--featured {
    min-height: 128px;
    padding: 22px 24px;

    .metric-card__value {
      font-size: 40px;
    }

    .metric-card__unit {
      font-size: 17px;
    }
  }
}

/* ============================================================
   MetricCard 样式 · 单一来源：frontend/design.md
   卡片：--bg-card / --radius-lg / --shadow-raised / --border-light
   结构：标题行(标题 + 等级标签) → 大数字 + 小单位 → 副文案
   数字：30px(默认) / 40px(featured)，单位 15px
   ============================================================ */
</style>
