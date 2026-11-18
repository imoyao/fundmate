// src/components/MoneyDisplay/useMoneyDisplay.ts
/**
 * MoneyDisplay 的 props 契约 + 派生状态（**从 SFC 抽出的那一半**）。
 *
 * 为什么拆：组件本身已顶到页面规模门禁（400 行，#980），而里面真正会变的
 * 只有「数值怎么解析、遮不遮、染什么色」，渲染模板几乎不再改动。
 * 把「算」与「画」分开后，本文件可被单测直接调用（不必挂载组件），
 * SFC 只剩模板与样式。
 */

import { computed } from "vue";
import { usePrivacyMode } from "@/composables/usePrivacyMode";

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

  /** 后缀文本（如 "万"、"%") */
  suffix?: string;

  /** 尺寸：xs | sm | md | lg | xl | hero */
  size?: "xs" | "sm" | "md" | "lg" | "xl" | "hero";

  /** 无数据时的占位文本，默认 -- */
  emptyText?: string;

  /**
   * 永远显示真值，不参与隐私遮罩。
   *
   * 只给两类场景用：
   * 1. **表单 / 输入回显**（用户在核对刚填的数字，遮住等于让他没法确认）；
   * 2. **单位 / 汇率说明**里的示例数（不是个人资产）。
   * 展示型金额一律**不要**传——遮罩靠「默认全覆盖」才不漏。
   */
  noMask?: boolean;
}

/** 千分位 + 固定小数位（`12345.6` → `12,345.60`）；负数只取绝对值，符号单独渲染 */
export function formatAmount(value: number, precision: number): string {
  const fixed = Math.abs(value).toFixed(precision);
  const parts = fixed.split(".");
  const intPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return precision > 0 ? `${intPart}.${parts[1]}` : intPart;
}

/**
 * 把 props 映射成渲染所需的派生状态。
 *
 * @param props `defineProps` 返回的响应式对象（**不要解构**，解构会丢响应性）
 */
export function useMoneyDisplay(props: MoneyDisplayProps) {
  const { visible } = usePrivacyMode();

  /** 是否为空（null / undefined / 空串）：渲染占位，不进入数值计算 */
  const isEmpty = computed(() => props.value == null || props.value === "");

  /**
   * 是否渲染遮罩：全局遮罩开启、且没有 long-press 窥视、且本处未声明 no-mask。
   * 空值不算遮罩——「没有数据」已经由 emptyText 表达，再遮一次反而像有数藏着。
   */
  const isMasked = computed(
    () => !props.noMask && !visible.value && !isEmpty.value
  );

  /** 数值转换为数字（解析失败的字符串按 0 处理，不抛错） */
  const numericValue = computed(() => {
    if (isEmpty.value) return 0;
    const val =
      typeof props.value === "string" ? parseFloat(props.value) : props.value;
    return typeof val === "number" && !isNaN(val) ? val : 0;
  });

  const isRise = computed(() => numericValue.value > 0);
  const isFall = computed(() => numericValue.value < 0);
  const isZero = computed(() => numericValue.value === 0);

  /** 是否隐藏涨跌色（自定义颜色即视为指定了颜色） */
  const hideColor = computed(() => !!props.customColor);

  const formattedValue = computed(() =>
    formatAmount(numericValue.value, props.precision ?? 2)
  );

  /** 货币符号（不带空格，通过 CSS 间距控制） */
  const currencySymbol = computed(() => props.currency || "");

  return {
    isEmpty,
    isMasked,
    isRise,
    isFall,
    isZero,
    hideColor,
    formattedValue,
    currencySymbol
  };
}
