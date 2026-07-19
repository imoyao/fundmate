<!-- ============================================================
  RiseFallText.vue
  涨跌文本组件 · 设计语言 v2.3.2

  功能：
  - 根据正负自动着色（涨红跌绿）
  - 自动显示正负号（+ / -）
  - 可自定义后缀（默认 %）
  - 等宽字体（font-variant-numeric: tabular-nums）
  - 零值显示为 0.00% (灰色)

  使用示例：
  <RiseFallText :value="12.34" />            +12.34% (红色) -->
<!--  <RiseFallText :value="-5.67" />           &lt;!&ndash; -5.67% (绿色) &ndash;&gt;-->
<!--  <RiseFallText :value="0" />               &lt;!&ndash; 0.00% (灰色) &ndash;&gt;-->
<!--  <RiseFallText :value="12.34" suffix="%" :precision="1" />  &lt;!&ndash; +12.3% (红色) &ndash;&gt;-->
<!--  ============================================================ &ndash;&gt;-->

<template>
  <span
    class="rise-fall-text"
    :class="[
      isRise ? 'is-rise' : '',
      isFall ? 'is-fall' : '',
      isZero ? 'is-zero' : '',
      hideColor ? 'no-color' : '',
      sizeClass
    ]"
    :style="{ color: customColor }"
  >
    <!-- 正负号 -->
    <span v-if="showSign && !isZero" class="sign">
      {{ isRise ? "+" : "-" }}
    </span>

    <!-- 数值 -->
    <span class="number font-mono">{{ formattedValue }}</span>

    <!-- 后缀 -->
    <span v-if="suffix" class="suffix">{{ suffix }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue";

export interface RiseFallTextProps {
  /** 数值（正数=涨，负数=跌） */
  value: number | string;

  /** 后缀，默认 % */
  suffix?: string;

  /** 是否显示正负号，默认 true */
  showSign?: boolean;

  /** 小数位数，默认 2 */
  precision?: number;

  /** 是否根据正负自动着色，默认 true */
  autoColor?: boolean;

  /** 自定义颜色（覆盖 autoColor） */
  customColor?: string;

  /** 尺寸：'sm' | 'md' | 'lg'，默认 'md' */
  size?: "sm" | "md" | "lg";
}

const props = withDefaults(defineProps<RiseFallTextProps>(), {
  suffix: "%",
  showSign: true,
  precision: 2,
  autoColor: true,
  customColor: "",
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

/** 格式化数值（保留小数位） */
const formattedValue = computed(() => {
  const num = numericValue.value;
  const abs = Math.abs(num);
  return abs.toFixed(props.precision);
});

/** 尺寸类名 */
const sizeClass = computed(() => {
  const map = {
    sm: "text-sm",
    md: "text-base",
    lg: "text-lg font-semibold"
  };
  return map[props.size] || map.md;
});
</script>

<style scoped>
.rise-fall-text {
  display: inline-flex;
  align-items: baseline;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

/* ===== 数字字体（等宽） ===== */
.rise-fall-text .number {
  font-family: var(--font-mono, "SF Mono", "JetBrains Mono", monospace);
  font-weight: 500;
}

/* ===== 正负号 ===== */
.rise-fall-text .sign {
  font-family: var(--font-sans, Inter, -apple-system, sans-serif);
  font-weight: 500;
  font-size: 0.9em;
  margin-right: 1px;
}

/* ===== 后缀 ===== */
.rise-fall-text .suffix {
  font-family: var(--font-sans, Inter, -apple-system, sans-serif);
  font-weight: 400;
  font-size: 0.8em;
  margin-left: 1px;
  opacity: 0.7;
}

/* ===== 涨（红） ===== */
.rise-fall-text.is-rise {
  color: var(--color-rise, #e34f38);
}

/* ===== 跌（绿） ===== */
.rise-fall-text.is-fall {
  color: var(--color-fall, #7bc49a);
}

/* ===== 零值 ===== */
.rise-fall-text.is-zero {
  color: var(--text-secondary, #6b655c);
}

/* ===== 自定义颜色（覆盖涨跌） ===== */
.rise-fall-text.no-color {
  color: var(--text-primary, #2d2a24);
}

/* ===== 暗色模式适配 ===== */
[data-theme="dark"] .rise-fall-text.is-rise {
  color: var(--color-rise, #d45a44);
}

[data-theme="dark"] .rise-fall-text.is-fall {
  color: var(--color-fall, #5daf85);
}

/* ===== 尺寸变体 ===== */
.rise-fall-text.text-sm {
  font-size: 13px;
}

.rise-fall-text.text-sm .number {
  font-size: 13px;
}

.rise-fall-text.text-base {
  font-size: 16px;
}

.rise-fall-text.text-base .number {
  font-size: 16px;
}

.rise-fall-text.text-lg {
  font-size: 20px;
}

.rise-fall-text.text-lg .number {
  font-size: 20px;
}
</style>
