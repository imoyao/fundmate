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
      // autoColor=false 时不渲染任何涨跌/零值色，走默认文字色
      // （此前 autoColor 从未被消费：仍按正负上红绿，导致 MoneyWithRatio
      //   ratioAutoColor=false 的「占比中性色」语义失效，2026-09-03 修复）
      isRise && autoColor ? 'is-rise' : '',
      isFall && autoColor ? 'is-fall' : '',
      isZero && autoColor ? 'is-zero' : '',
      hideColor ? 'no-color' : '',
      sizeClass
    ]"
    :style="{ color: customColor }"
  >
    <!-- 正负号。⚠️ 换行只能落在 `{{ }}` **内部**（那是 JS 表达式源码，不产生
         文本节点）；`>` 与 `{{` 之间、`}}` 与 `<` 之间的换行缩进则会被渲染成
         可见空格，"-" 与数字之间凭空多出 3px 的缝，看上去像「减号是单独一个东西」。
         超出行宽时 prettier 会把表达式折行 —— 安全：@vue/compiler-sfc 实测
         两种写法的 render 代码逐字相同。 -->
    <span v-if="showSign && !isZero" class="sign">{{
      isRise ? "+" : "-"
    }}</span>

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
  margin-right: 1px;
  font-family: var(--font-sans, Inter, -apple-system, sans-serif);

  /* 与数字同号（1em）：0.9em 时减号比数字小一号、笔画细，13px 的小字里
     会被读成「一个灰点」而不是数字的一部分（用户报的「符号像浅灰」）。
     符号本身照常继承 .is-rise / .is-fall 的颜色。 */
  font-size: 1em;
  font-weight: 500;

  /* ⚠️ 必须关掉 tabular-nums：它是继承来的（根节点给数字开的等宽对齐），
     而 Inter 的 tnum 特性能把连字符/减号换成**等宽数字格**里那个居中的版本
     ——实测 "-" 从 6.02px 变成 8.44px，减号因此离数字 2px 远、笔画也变淡，
     看上去像「一个单独的小横线」。数字仍保持 tabular-nums（小数点对齐），
     符号回到比例宽（此规则只作用于 .sign）。 */
  font-variant-numeric: normal;
}

/* ===== 后缀 ===== */
.rise-fall-text .suffix {
  margin-left: 1px;
  font-family: var(--font-sans, Inter, -apple-system, sans-serif);
  font-size: 0.8em;
  font-weight: 400;
  opacity: 0.7;
}

/* ===== 涨（红） ===== */
.rise-fall-text.is-rise {
  color: var(--color-rise-ink, #c0341f);
}

/* ===== 跌（绿） ===== */
.rise-fall-text.is-fall {
  color: var(--color-fall-ink, #287d51);
}

/* ===== 零值 ===== */
.rise-fall-text.is-zero {
  color: var(--text-secondary, #6b655c);
}

/* ===== 自定义颜色（覆盖涨跌） ===== */
.rise-fall-text.no-color {
  color: var(--text-primary, #2d2a24);
}

/* 暗色不需要单独分支：--color-rise-ink / --color-fall-ink 由 dark.scss 的
   `:root.dark` 覆盖同名变量，本组件只引用变量即可。
   历史上这里写过「把 data-theme 属性等于 dark 当暗色开关」的 CSS 选择器，
   但 data-theme 只承载配色主题名（light/default/.../showbuy），永远不会是 dark，
   那条选择器永不命中，已删除。防回潮判据：scripts/guard_no_data_theme_dark.mjs */

/* ===== 尺寸变体 ===== */
.rise-fall-text.text-sm {
  font-size: var(--text-label);
}

.rise-fall-text.text-sm .number {
  font-size: var(--text-label);
}

.rise-fall-text.text-base {
  font-size: var(--text-body);
}

.rise-fall-text.text-base .number {
  font-size: var(--text-body);
}

.rise-fall-text.text-lg {
  font-size: var(--text-heading);
}

.rise-fall-text.text-lg .number {
  font-size: var(--text-heading);
}
</style>
