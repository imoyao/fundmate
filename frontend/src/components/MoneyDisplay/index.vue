<!-- ============================================================
  MoneyDisplay.vue
  金额展示组件 · 设计语言 v2.3.2

  功能：
  - 自动格式化千分位（如 ¥12,345.67）
  - 根据正负自动着色（涨红跌绿）
  - 等宽字体（font-variant-numeric: tabular-nums）
  - 可选正负号显示
  - 可选货币符号显示
  - 零值统一显示为 ¥0.00
  - 支持尺寸层级：xs / sm / md / lg / xl / hero
  ============================================================ -->

<template>
  <span
    class="money-display"
    :class="[
      `size-${size}`,
      isRise ? 'is-rise' : '',
      isFall ? 'is-fall' : '',
      isZero ? 'is-zero' : '',
      hideColor ? 'no-color' : ''
    ]"
    :style="{ color: customColor }"
  >
    <!-- 正负号 -->
    <span v-if="showSign && !isZero" class="sign">
      {{ isRise ? "+" : "-" }}
    </span>

    <!-- 货币符号 -->
    <span v-if="showCurrency" class="currency">{{ currencySymbol }}</span>

    <!-- 金额数字（等宽 + 千分位） -->
    <span class="number">{{ formattedValue }}</span>

    <!-- 后缀（可选） -->
    <span v-if="suffix" class="suffix">{{ suffix }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue";

export interface MoneyDisplayProps {
  /** 金额数值 */
  value: number | string;

  /** 货币符号，默认 ¥ */
  currency?: string;

  /** 是否显示正负号，默认 true */
  showSign?: boolean;

  /** 是否显示货币符号，默认 true */
  showCurrency?: boolean;

  /** 小数位数，默认 2 */
  precision?: number;

  /** 是否根据正负自动着色，默认 true */
  autoColor?: boolean;

  /** 自定义颜色（覆盖 autoColor） */
  customColor?: string;

  /** 后缀文本（如 "万"、"%"） */
  suffix?: string;

  /** 尺寸：xs | sm | md | lg | xl | hero */
  size?: "xs" | "sm" | "md" | "lg" | "xl" | "hero";
}

const props = withDefaults(defineProps<MoneyDisplayProps>(), {
  currency: "¥",
  showSign: true,
  showCurrency: true,
  precision: 2,
  autoColor: true,
  customColor: "",
  suffix: "",
  size: "md"
});

/** 数值转换为数字 */
const numericValue = computed(() => {
  const val =
    typeof props.value === "string" ? parseFloat(props.value) : props.value;
  return isNaN(val) ? 0 : val;
});

/** 是否为正数（涨） */
const isRise = computed(() => numericValue.value > 0);

/** 是否为负数（跌） */
const isFall = computed(() => numericValue.value < 0);

/** 是否为零 */
const isZero = computed(() => numericValue.value === 0);

/** 是否隐藏颜色（自定义颜色时） */
const hideColor = computed(() => !!props.customColor);

/** 格式化金额（千分位 + 固定小数位） */
const formattedValue = computed(() => {
  const num = numericValue.value;
  const abs = Math.abs(num);
  const fixed = abs.toFixed(props.precision);
  const parts = fixed.split(".");
  const intPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return props.precision > 0 ? `${intPart}.${parts[1]}` : intPart;
});

/** 货币符号（不带空格，通过 CSS 间距控制） */
const currencySymbol = computed(() => {
  return props.currency || "";
});
</script>

<style scoped>
.money-display {
  display: inline-flex;
  align-items: baseline;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

/* ===== 数字字体（等宽） ===== */
.money-display .number {
  font-family: var(--font-mono, "SF Mono", "JetBrains Mono", monospace);
  font-weight: 500;
}

/* ===== 货币符号 ===== */
.money-display .currency {
  margin-right: 1px;
  font-family: var(--font-sans, Inter, -apple-system, sans-serif);
  font-weight: 400;
  color: inherit;
  opacity: 0.7;
}

/* ===== 正负号 ===== */
.money-display .sign {
  margin-right: 1px;
  font-family: var(--font-sans, Inter, -apple-system, sans-serif);
  font-size: 0.9em;
  font-weight: 500;
}

/* ===== 后缀 ===== */
.money-display .suffix {
  margin-left: 2px;
  font-family: var(--font-sans, Inter, -apple-system, sans-serif);
  font-size: 0.75em;
  opacity: 0.7;
}

/* ============================================================
   尺寸映射（严格匹配设计令牌）
   ============================================================ */

/* ✅ Hero 尺寸 - 对应 --text-hero (48px, 衬线体, 字重 600) */
.money-display.size-hero .number {
  font-family: var(--font-sans, Inter, -apple-system, sans-serif);
  font-size: var(--text-hero, 48px);
  font-weight: 600;
  letter-spacing: -0.5px;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.money-display.size-hero .currency,
.money-display.size-hero .sign {
  font-size: 0.7em; /* ✅ 微调，从 0.65em → 0.7em */
}

.money-display.size-hero .suffix {
  font-size: 0.5em;
}

/* ✅ XL 尺寸 - 对应 --text-display (32px, 衬线体, 字重 300) */
.money-display.size-xl .number {
  font-family: var(--font-sans, Inter, -apple-system, sans-serif);
  font-size: var(--text-display, 32px);
  font-weight: 300;
  letter-spacing: -0.3px;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.money-display.size-xl .currency,
.money-display.size-xl .sign {
  font-size: 0.75em;
}

/* LG 尺寸 - 对应 --text-title (24px) */
.money-display.size-lg .number {
  font-size: var(--text-title, 24px);
  font-weight: 500;
}

.money-display.size-lg .currency,
.money-display.size-lg .sign {
  font-size: 0.8em;
}

/* MD 尺寸 - 对应 --text-body (16px) */
.money-display.size-md .number {
  font-size: var(--text-body, 16px);
}

.money-display.size-md .currency,
.money-display.size-md .sign {
  font-size: 0.85em;
}

/* SM 尺寸 - 对应 --text-small (14px) */
.money-display.size-sm .number {
  font-size: var(--text-small, 14px);
}

.money-display.size-sm .currency,
.money-display.size-sm .sign {
  font-size: 0.85em;
}

/* XS 尺寸 - 对应 --text-label (13px) */
.money-display.size-xs .number {
  font-size: var(--text-label, 13px);
}

.money-display.size-xs .currency,
.money-display.size-xs .sign {
  font-size: 0.85em;
}

/* ===== 颜色语义 ===== */
.money-display.is-rise {
  color: var(--color-rise, #e34f38);
}

/* ===== 跌（绿） ===== */
.money-display.is-fall {
  color: var(--color-fall, #7bc49a);
}

/* ===== 零值 ===== */
.money-display.is-zero {
  color: var(--text-secondary, #6b655c);
}

/* ===== 自定义颜色（覆盖涨跌） ===== */
.money-display.no-color {
  color: var(--text-primary, #2d2a24);
}

/* ===== 暗色模式适配 ===== */
[data-theme="dark"] .money-display.is-rise {
  color: var(--color-rise, #d45a44);
}

[data-theme="dark"] .money-display.is-fall {
  color: var(--color-fall, #5daf85);
}
</style>
