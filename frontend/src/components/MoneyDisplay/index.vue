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
      !isEmpty && isRise && !hideColor && autoColor ? 'is-rise' : '',
      !isEmpty && isFall && !hideColor && autoColor ? 'is-fall' : '',
      !isEmpty && isZero && !hideColor && autoColor ? 'is-zero' : '',
      hideColor ? 'no-color' : ''
    ]"
    :style="{ color: customColor }"
  >
    <!-- 空值占位（value 为 null/undefined/空串）：仅显示占位文本，不套涨跌色 -->
    <template v-if="isEmpty">
      <span class="number">{{ emptyText }}</span>
    </template>
    <template v-else>
      <!-- 正负号。⚠️ 换行只能落在 `{{ }}` **内部**（那是 JS 表达式源码，不产生
           文本节点）；`>` 与 `{{` 之间、`}}` 与 `<` 之间的换行/缩进则会被渲染成
           一个可见空格，"-" 与数字之间就多出一道 3px 的缝（数字是等宽字体，
           这道缝在百分比里尤其突兀）。本行超出行宽时 prettier 会把表达式折成
           多行 —— 那是安全的：@vue/compiler-sfc 实测两种写法的 render 代码逐字相同。 -->
      <span v-if="showSign && !isZero" class="sign">{{
        isRise ? "+" : "-"
      }}</span>

      <!-- 货币符号 -->
      <span v-if="showCurrency" class="currency">{{ currencySymbol }}</span>

      <!-- 金额数字（等宽 + 千分位） -->
      <span class="number">{{ formattedValue }}</span>

      <!-- 后缀（可选） -->
      <span v-if="suffix" class="suffix">{{ suffix }}</span>
    </template>
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue";

export interface MoneyDisplayProps {
  /** 金额数值，允许 null/undefined（无数据时渲染 emptyText 占位，不报 prop 校验告警） */
  value?: number | string | null;

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

  /** 无数据时的占位文本，默认 -- */
  emptyText?: string;
}

const props = withDefaults(defineProps<MoneyDisplayProps>(), {
  currency: "¥",
  showSign: true,
  showCurrency: true,
  precision: 2,
  autoColor: true,
  customColor: "",
  suffix: "",
  size: "md",
  emptyText: "--"
});

/** 是否为空（null / undefined / 空串）：渲染占位，不进入数值计算 */
const isEmpty = computed(() => props.value == null || props.value === "");

/** 数值转换为数字 */
const numericValue = computed(() => {
  if (isEmpty.value) return 0;
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

  /* 同 RiseFallText：关掉继承来的 tabular-nums。Inter 的 tnum 会把减号换成
     数字格宽的居中版本（"-" 6.02px → 8.44px），负号与数字之间于是多出一道缝。
     数字本身仍是 tabular-nums（小数点对齐），只有符号回到比例宽。 */
  font-variant-numeric: normal;
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

   ⚠️ 每个档位都把**数字字号**同时落在根节点上：`.currency / .sign / .suffix`
   用的是 em，而 em 参照**父元素**的字号。根节点原先没有字号 ⇒ 它们参照的是
   继承来的正文 16px —— hero 的 ¥ 只有 0.7×16 = 11.2px，却与 57px 的数字
   同基线，看上去就是「沉在左下角的一个小符号」（用户报的观感问题，
   根因在这里，不在颜色）。根节点拿到正确字号后，下面的 em 才是真正的
   「数字的几分之几」。

   两种情形请分开看：
   · md 档根字号恰是继承值 16px ⇒ 恒等变换，外观零变化；
   · hero / xl / lg 档符号**随之变大**（此前它们全按 16px 折算，¥ 反而比
     数字小得多），sm / xs 档符号**略变小**（此前略大于数字本身）。
     这是把「符号是数字的一部分」这条口径补齐，不是改动设计；若某页确实
     需要旧尺寸，应在该页覆写，不要在根节点去掉字号（那会让 hero 退回 bug）。
   ============================================================ */

.money-display.size-hero {
  font-size: var(--text-hero, 57px);
}

.money-display.size-xl {
  font-size: var(--text-display, 32px);
}

.money-display.size-lg {
  font-size: var(--text-title, 24px);
}

.money-display.size-md {
  font-size: var(--text-body, 16px);
}

.money-display.size-sm {
  font-size: var(--text-small, 14px);
}

.money-display.size-xs {
  font-size: var(--text-label, 13px);
}

/* ✅ Hero 尺寸 - 对应 --text-hero (57px, 字重 600) */
.money-display.size-hero .number {
  font-family: var(--font-sans, Inter, -apple-system, sans-serif);
  font-size: var(--text-hero, 57px);
  font-weight: 600;
  letter-spacing: -0.5px;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* ¥ 取数字的 0.4 倍（≈23px）：既能读出是货币符号，又不与 57px 数字抢视线。
   基线对齐（根节点 align-items: baseline）让 ¥ 的底边与数字底边齐平——
   这是账目式排版里「符号小一号、坐在数字左下」的常规做法；
   此前的突兀来自「太小」而不是「对齐方式」。 */
.money-display.size-hero .currency {
  margin-right: 2px;
  font-size: 0.4em;
  font-weight: 500;
  opacity: 0.8;
}

.money-display.size-hero .sign {
  font-size: 0.55em;
}

.money-display.size-hero .suffix {
  font-size: 0.5em;
}

/* ✅ XL 尺寸 - 对应 --text-display (32px, 字重 300) */
.money-display.size-xl .number {
  font-family: var(--font-sans, Inter, -apple-system, sans-serif);
  font-size: var(--text-display, 32px);
  font-weight: 300;
  letter-spacing: -0.3px;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.money-display.size-xl .currency {
  font-size: 0.5em;
}

.money-display.size-xl .sign {
  font-size: 0.7em;
}

.money-display.size-xl .suffix {
  font-size: 0.5em;
}

/* LG 尺寸 - 对应 --text-title (24px) */
.money-display.size-lg .number {
  font-size: var(--text-title, 24px);
  font-weight: 500;
}

.money-display.size-lg .currency {
  font-size: 0.62em;
}

.money-display.size-lg .sign {
  font-size: 0.75em;
}

.money-display.size-lg .suffix {
  font-size: 0.6em;
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
  font-size: 0.9em;
}

/* XS 尺寸 - 对应 --text-label (13px) */
.money-display.size-xs .number {
  font-size: var(--text-label, 13px);
}

.money-display.size-xs .currency,
.money-display.size-xs .sign {
  font-size: 0.9em;
}

/* ===== 颜色语义 ===== */
.money-display.is-rise {
  color: var(--color-rise-ink, #c0341f);
}

/* ===== 跌（绿） ===== */
.money-display.is-fall {
  color: var(--color-fall-ink, #287d51);
}

/* ===== 零值 ===== */
.money-display.is-zero {
  color: var(--text-secondary, #6b655c);
}

/* ===== 自定义颜色（覆盖涨跌） ===== */
.money-display.no-color {
  color: var(--text-primary, #2d2a24);
}

/* 暗色不需要单独分支：--color-rise-ink / --color-fall-ink 由 dark.scss 的
   `:root.dark` 覆盖同名变量，本组件只引用变量即可。
   历史上这里写过「把 data-theme 属性等于 dark 当暗色开关」的 CSS 选择器，
   但 data-theme 只承载配色主题名（light/default/.../showbuy），永远不会是 dark，
   那条选择器永不命中，已删除。防回潮判据：scripts/guard_no_data_theme_dark.mjs */
</style>
