// 未竟之蹊卡片展示用的纯函数：涨跌幅派生、日期文案。
//
// 原则（AGENTS.md 核心约束）：后端没有的口径绝不编造数值——
// 缺数据一律返回 null，由卡片降级显示「—」。

import type { RoadItem } from "@/types/favorites";

/** 走势序列的区间涨跌幅（%）：首尾比较；不足两点返回 null */
export function trendChangePct(series: number[]): number | null {
  if (!series || series.length < 2) return null;
  const first = series[0];
  const last = series[series.length - 1];
  if (!first) return null;
  return ((last - first) / first) * 100;
}

/** 自选以来涨跌幅（%）：现价 vs 添加日收盘价；任一缺失返回 null */
export function sinceAddedPct(item: RoadItem): number | null {
  const cur = item.current_price;
  const added = item.price_at_added;
  if (cur == null || added == null || !added) return null;
  return ((cur - added) / added) * 100;
}

export interface RoadMetric {
  label: string;
  value: number;
}

/** 卡片「对比数据条」：全部真实派生值，缺数据的口径不出现该格 */
export function cardMetrics(item: RoadItem): RoadMetric[] {
  const list: RoadMetric[] = [];
  const since = sinceAddedPct(item);
  if (since != null) list.push({ label: "自选以来", value: since });
  const range = trendChangePct(item.trend);
  if (range != null)
    list.push({ label: `近 ${item.trend.length} 日`, value: range });
  if (item.holding_pnl_percent != null)
    list.push({ label: "持仓收益", value: item.holding_pnl_percent });
  return list;
}

/** 按值取涨跌语义令牌（0 视为持平走主文字色） */
export function pctColorVar(value: number | null): string {
  if (value == null || value === 0) return "var(--text-secondary)";
  return value > 0 ? "var(--color-rise)" : "var(--color-fall)";
}

/** 百分比文案：带正负号，空值返回 — */
export function pctText(value: number | null, precision = 2): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(precision)}%`;
}

/** 距今天数（负=已过去，正=还有几天）；日期非法返回 null */
export function daysFromToday(date: string | null): number | null {
  if (!date) return null;
  const target = new Date(`${date}T00:00:00`);
  if (Number.isNaN(target.getTime())) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - today.getTime()) / 86400000);
}

/**
 * 复盘提醒文案：
 * - 已过期 → 「复盘已逾期 N 天」
 * - 7 天内 → 「还有 N 天该复盘」
 * - 更远   → 「YYYY-MM-DD 复盘」
 * - 未设置 → null（卡片提示「设个复盘日期」）
 */
export function reviewHintText(date: string | null): string | null {
  const days = daysFromToday(date);
  if (days == null) return null;
  if (days < 0) return `复盘已逾期 ${Math.abs(days)} 天`;
  if (days === 0) return "今天该复盘了";
  if (days <= 7) return `还有 ${days} 天该复盘`;
  return `${date} 复盘`;
}

/** 两个日期之间的天数（用于「持有 N 天」） */
export function daysBetween(
  start: string | null,
  end?: string | null
): number | null {
  if (!start) return null;
  const from = new Date(`${start.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(from.getTime())) return null;
  const to = end ? new Date(`${end.slice(0, 10)}T00:00:00`) : new Date();
  if (Number.isNaN(to.getTime())) return null;
  return Math.max(0, Math.round((to.getTime() - from.getTime()) / 86400000));
}
