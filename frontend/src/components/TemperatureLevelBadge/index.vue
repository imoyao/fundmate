<!-- ============================================================
  TemperatureLevelBadge.vue
  温度等级徽标组件 · 多倍贝设计语言 v2.3.3

  用途：
  - 将温度等级文本（偏低 / 适中 / 偏高 / 低估 / 高估 等）映射为统一的
    视觉徽标，颜色严格复用全局 token：--temp-low / --temp-mid / --temp-high
    及相关背景变量（见 src/style/colors.css），保证两页面视觉一致、单一来源。

  温度语义与涨跌色相互独立：
  - 低温 = 机会区（绿）  --temp-low
  - 适中 = 平稳（暖沙金） --temp-mid
  - 高温 = 谨慎区（红）  --temp-high  （独立于品牌涨色 --color-rise）

  使用示例：
  <TemperatureLevelBadge level="偏低" />
  <TemperatureLevelBadge level="高估" size="sm" />
  <TemperatureLevelBadge tone="high" label="谨慎" />
  ============================================================ -->

<template>
  <span class="temperature-level-badge" :class="[toneClass, sizeClass]">
    {{ displayLabel }}
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue";

type TemperatureTone = "low" | "mid" | "high";

export interface TemperatureLevelBadgeProps {
  /** 温度等级文本，如「偏低」「适中」「偏高」「低估」「高估」等 */
  level?: string;

  /** 显式指定色调，优先级高于 level 文本推断 */
  tone?: TemperatureTone;

  /** 自定义显示文本，缺省时回退到 level */
  label?: string;

  /** 尺寸：'sm' | 'md'，默认 'md' */
  size?: "sm" | "md";
}

const props = withDefaults(defineProps<TemperatureLevelBadgeProps>(), {
  level: "",
  tone: "" as TemperatureTone,
  label: "",
  size: "md"
});

/** 根据等级文本推断色调（低温=机会绿，高温=谨慎红，其余=适中） */
const inferredTone = computed<TemperatureTone>(() => {
  const level = (props.level || "").trim();
  if (level === "偏低" || level === "低估") return "low";
  if (level === "偏高" || level === "高估") return "high";
  return "mid";
});

const toneClass = computed(() => {
  const tone = props.tone || inferredTone.value;
  return `tone-${tone}`;
});

const displayLabel = computed(() => {
  return props.label || props.level || "适中";
});

const sizeClass = computed(() => `size-${props.size}`);
</script>

<style scoped>
.temperature-level-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
  font-weight: 500;
  border-radius: var(--radius-pill, 9999px);
  line-height: 1.4;
  transition: background-color 150ms ease, color 150ms ease;
}

/* ===== 尺寸 ===== */
.temperature-level-badge.size-md {
  font-size: 13px;
  padding: 2px 10px;
}

.temperature-level-badge.size-sm {
  font-size: 12px;
  padding: 1px 8px;
}

/* ===== 低温·机会区（绿） ===== */
.temperature-level-badge.tone-low {
  background: var(--temp-low-bg);
  color: var(--temp-low);
}

/* ===== 适中·平稳（暖沙金） ===== */
.temperature-level-badge.tone-mid {
  background: var(--temp-mid-bg);
  color: var(--temp-mid);
}

/* ===== 高温·谨慎区（红，独立于品牌涨色） ===== */
.temperature-level-badge.tone-high {
  background: var(--temp-high-bg);
  color: var(--temp-high);
}
</style>
