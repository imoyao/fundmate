// src/components/ValuationSourceBadge/helpers.ts
/**
 * 估/确认徽标的文案与映射（#2143）。
 *
 * 单一出口纪律：
 * - 盘中预估的完整免责文案 `ESTIMATE_DISCLAIMER` 仍住在 `usePositionValuation`
 *   （既有唯一出口；本文件**不复制**它——各语境完整提示语由调用方传 `tip`）；
 * - 本文件只放「状态短语 + 来源映射」——各语境的完整提示语由调用方传入
 *   `tip`（盘中副行 vs 日历定格说的是两回事，不该共用一句话）。
 */

/** 后端 fund-valuation.status 契约值；未知状态不画徽标（诚实缺席，不猜） */
export type ValuationStatus = "estimated" | "confirmed";

/** 来源标识 → 展示名。后端 source（fund-valuation）与前端 Quote.provider 共用一张表 */
const SOURCE_LABELS: Record<string, string> = {
  tiantian_gsz: "天天基金估值",
  tiantian: "天天基金估值",
  "tiantian-batch": "天天基金估值",
  tencent: "腾讯行情",
  sina: "新浪行情",
  official: "官方净值",
  daily_worth: "官方净值"
};

/** 徽标内文字：预估 →「估」，确认 →「确认」，未知 → 空串（整块不渲染） */
export function valuationStatusLabel(
  status: string | null | undefined
): string {
  if (status === "estimated") return "估";
  if (status === "confirmed") return "确认";
  return "";
}

/** 来源标识 → 展示名；表里没有的原样返回（新数据源缺映射时不装懂） */
export function valuationSourceLabel(
  source: string | null | undefined
): string {
  if (!source) return "";
  return SOURCE_LABELS[source] ?? source;
}

/**
 * 「来源 · 数据时间」一行元信息；两者皆缺返回空串（徽标旁不加任何缀文）。
 * 数据时间是源端字符串原样展示（如 "2026-10-13 15:00"），不在前端再解析。
 */
export function valuationMetaText(
  source: string | null | undefined,
  sourceTime: string | null | undefined
): string {
  const parts: string[] = [];
  const label = valuationSourceLabel(source);
  if (label) parts.push(label);
  if (sourceTime) parts.push(sourceTime);
  return parts.join(" · ");
}

/**
 * 无障碍/缺省提示语：调用方没传 `tip` 时按状态推导的短语。
 * 只描述状态本身（「是什么」），不展开语境解释——语境解释归调用方的 tip。
 */
export function valuationDefaultAria(
  status: string | null | undefined
): string {
  if (status === "estimated") return "预估值，非官方净值";
  if (status === "confirmed") return "官方净值已确认";
  return "";
}
