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

  使用示例：
  <MoneyDisplay :value="12345.67" />
  <MoneyDisplay :value="-1234.56" :show-sign="false" />
  <MoneyDisplay :value="0" />
  ============================================================ -->

<template>
  <span
    class="money-display"
    :class="[
      isRise ? 'is-rise' : '',
      isFall ? 'is-fall' : '',
      isZero ? 'is-zero' : '',
      hideColor ? 'no-color' : ''
    ]"
    :style="{ color: customColor }"
  >
    <!-- 正负号 -->
    <span v-if="showSign && !isZero" class="sign">
      {{ isRise ? '+' : '-' }}
    </span>

    <!-- 货币符号 -->
    <span v-if="showCurrency" class="currency">{{ currencySymbol }}</span>

    <!-- 金额数字（等宽 + 千分位） -->
    <span class="number font-mono">{{ formattedValue }}</span>

    <!-- 后缀（可选） -->
    <span v-if="suffix" class="suffix">{{ suffix }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue';

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
}

const props = withDefaults(defineProps<MoneyDisplayProps>(), {
  currency: '¥',
  showSign: true,
  showCurrency: true,
  precision: 2,
  autoColor: true,
  customColor: '',
  suffix: '',
});

/** 数值转换为数字 */
const numericValue = computed(() => {
  const val = typeof props.value === 'string' ? parseFloat(props.value) : props.value;
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
  const parts = fixed.split('.');
  const intPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return props.precision > 0 ? `${intPart}.${parts[1]}` : intPart;
});

/** 货币符号（带空格） */
const currencySymbol = computed(() => {
  return props.currency ? `${props.currency}` : '';
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
  font-family: var(--font-mono, 'SF Mono', 'JetBrains Mono', monospace);
  font-weight: 500;
}

/* ===== 货币符号 ===== */
.money-display .currency {
  font-family: var(--font-sans, Inter, -apple-system, sans-serif);
  font-weight: 400;
  font-size: 0.85em;
  margin-right: 1px;
  color: inherit;
  opacity: 0.7;
}

/* ===== 正负号 ===== */
.money-display .sign {
  font-family: var(--font-sans, Inter, -apple-system, sans-serif);
  font-weight: 500;
  font-size: 0.9em;
  margin-right: 1px;
}

/* ===== 后缀 ===== */
.money-display .suffix {
  font-family: var(--font-sans, Inter, -apple-system, sans-serif);
  font-size: 0.75em;
  margin-left: 2px;
  opacity: 0.7;
}

/* ===== 涨（红） ===== */
.money-display.is-rise {
  color: var(--color-rise, #E34F38);
}

/* ===== 跌（绿） ===== */
.money-display.is-fall {
  color: var(--color-fall, #7BC49A);
}

/* ===== 零值 ===== */
.money-display.is-zero {
  color: var(--text-secondary, #6B655C);
}

/* ===== 自定义颜色（覆盖涨跌） ===== */
.money-display.no-color {
  color: var(--text-primary, #2D2A24);
}

/* ===== 暗色模式适配 ===== */
[data-theme='dark'] .money-display.is-rise {
  color: var(--color-rise, #D45A44);
}

[data-theme='dark'] .money-display.is-fall {
  color: var(--color-fall, #5DAF85);
}
</style>
