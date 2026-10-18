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
    - valueColor: 主数字颜色覆盖（可选，默认 --text-primary；见 props JSDoc 的取舍说明）
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
      <span
        class="metric-card__value"
        :style="valueColor ? { color: valueColor } : undefined"
        >{{ displayValue }}</span
      >
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
    /**
     * 主数字颜色，默认 `--text-primary`（中性暖黑）。
     *
     * ⚠️ 不改默认值是刻意的：MetricCard 是跨页共用组件，直接把默认色换成品牌色
     * 会一次性改写全部调用方的观感，属于「改一个组件、动整站」的连坐式变更。
     * 需要品牌色（如智能分析页的主数字）的调用方显式传 `var(--brand-ink)` 即可——
     * 该令牌是**文字级**品牌色（白底 5.86:1，达 WCAG AA），而 `--brand-700`
     * 作文字仅 3.73:1，不要用后者。
     */
    valueColor?: string;
  }>(),
  {
    title: "",
    value: null,
    unit: "",
    level: "",
    caption: "",
    featured: false,
    valueColor: ""
  }
);

const displayValue = computed(() => {
  const v = props.value;
  return v !== null && v !== undefined && v !== "" ? v : "--";
});
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

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
    font-size: var(--text-label);
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
    font-size: var(--text-display);
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1.05;
    color: var(--text-primary);
    letter-spacing: -0.5px;
  }

  &__unit {
    font-size: var(--text-num-strong);
    font-weight: 500;
    color: var(--text-tertiary-ink);
  }

  &__badge {
    flex-shrink: 0;
  }

  &__caption {
    font-size: var(--text-label);
    line-height: 1.4;
    color: var(--text-tertiary-ink);
  }

  /* featured：核心指标放大 */
  &--featured {
    min-height: 128px;
    padding: 22px 24px;

    .metric-card__value {
      font-size: var(--text-display-lg);
    }

    .metric-card__unit {
      font-size: var(--text-num-strong);
    }
  }
}

/* ============================================================
   MetricCard 样式 · 单一来源：frontend/design.md
   卡片：--bg-card / --radius-lg / --shadow-raised / --border-light
   结构：标题行(标题 + 等级标签) → 大数字 + 小单位 → 副文案
   数字：30px(默认) / 40px(featured)，单位 15px
   ============================================================ */

/* 窄屏缩小数字字号（原块**排在基础声明之前**，被后面同选择器的 30px / 40px 压掉、
   **从未生效**；2026-09-18 修复，见 #1576 同类登记）。

   ⚠️ 阈值**刻意保留 480px**（不给 Tailwind 档）：这是**卡片内数字字号**的阈值，与页面布局
   断点不同轴；而本页网格在窄视口下常常变成**单列**（卡片反而更宽），此时把数字缩到 26px
   与「窄屏收紧」的直觉相反。故按内容级阈值处理，用 `（阈值说明）` 显式豁免。 */
@media (width <= 480px) /* breakpoint-allow: 卡片内字号阈值（内容级） */ {
  /* 说明（已上移到 @media 同行）：卡片内字号阈值（内容级），非页面布局断点 */
  .metric-card__value {
    font-size: var(--text-num-hero);
  }

  .metric-card--featured .metric-card__value {
    font-size: var(--text-display);
  }
}
</style>
