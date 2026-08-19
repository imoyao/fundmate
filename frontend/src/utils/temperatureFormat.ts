// src/utils/temperatureFormat.ts
/**
 * 温度计页（views/temperature）展示辅助纯函数。
 * 从 temperature/index.vue 拆分下沉（#980），逻辑与原实现逐字保留，
 * 阈值配置统一来自 constants/temperature，避免页面与组件各自维护。
 */
import {
  BIAS_BAR_RANGE,
  BIAS_EXTREME_THRESHOLD,
  BIAS_HIGH_THRESHOLD,
  CROWDING_HIGH_THRESHOLD,
  CROWDING_LOW_THRESHOLD,
  SOURCE_DISPLAY_NAMES
} from "@/constants/temperature";

/** 数值夹取到 [min, max] 区间 */
export function clamp(n: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, n));
}

/** 数值格式化：按量级自适应小数位（>=10000 取整 / >=100 一位 / 其余两位），空值显示 -- */
export function formatValue(v: number | null | undefined): string {
  if (v === null || v === undefined) return "--";
  if (Math.abs(v) >= 10000) return v.toFixed(0);
  if (Math.abs(v) >= 100) return v.toFixed(1);
  return v.toFixed(2);
}

/** 乖离率档位配色类名：极端高/高/极端低/低/中性 */
export function biasColorClass(bias: number): string {
  if (bias >= BIAS_EXTREME_THRESHOLD) return "bias-extreme-high";
  if (bias >= BIAS_HIGH_THRESHOLD) return "bias-high";
  if (bias <= -BIAS_EXTREME_THRESHOLD) return "bias-extreme-low";
  if (bias <= -BIAS_HIGH_THRESHOLD) return "bias-low";
  return "bias-neutral";
}

/** 乖离率进度条样式：以 0 为中心，可视范围 [-BIAS_BAR_RANGE, BIAS_BAR_RANGE] 映射到进度条 */
export function biasBarStyle(bias: number) {
  const clamped = clamp(bias, -BIAS_BAR_RANGE, BIAS_BAR_RANGE);
  const percent = (Math.abs(clamped) / BIAS_BAR_RANGE) * 50; // 半边最多 50%
  const isPositive = clamped >= 0;
  return {
    width: `${percent}%`,
    left: isPositive ? "50%" : `${50 - percent}%`
  };
}

/** 指标数值配色类名：按等级文案关键词（低/冷/恐惧/低估 -> 低，高/热/贪婪/高估 -> 高） */
export function valueColorClass(value: number | null, label?: string): string {
  if (value === null || value === undefined) return "";
  const text = String(label || "");
  if (
    text.includes("低") ||
    text.includes("冷") ||
    text.includes("恐惧") ||
    text.includes("低估")
  )
    return "val-low";
  if (
    text.includes("高") ||
    text.includes("热") ||
    text.includes("贪婪") ||
    text.includes("高估")
  )
    return "val-high";
  return "val-mid";
}

/** 行业拥挤度档位配色：低=冷(蓝/绿)、中=中性、高=热(红)；复用 val-* 颜色令牌 */
export function crowdingColorClass(pct: number | null | undefined): string {
  if (pct === null || pct === undefined) return "";
  if (pct < CROWDING_LOW_THRESHOLD) return "val-low";
  if (pct > CROWDING_HIGH_THRESHOLD) return "val-high";
  return "val-mid";
}

/** 拥挤度百分位 0-100 映射到进度条宽度 */
export function crowdingBarStyle(pct: number | null | undefined) {
  const v = pct === null || pct === undefined ? 0 : clamp(pct, 0, 100);
  return { width: `${v}%` };
}

/** 来源标识 -> 中文显示名（未命中时原样返回） */
export function displaySource(source?: string): string {
  if (!source) return "";
  return SOURCE_DISPLAY_NAMES[source] || source;
}
