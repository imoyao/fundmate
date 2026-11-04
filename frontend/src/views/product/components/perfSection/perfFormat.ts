/**
 * 「业绩与风险」区块的展示口径（#980 拆分）。
 *
 * 这些函数原先散在 ProductPerformanceSection.vue 的 script 里。抽出来的唯一目的
 * 是让口径可被单测钉住 —— 「null 降级成 —」「0 回撤说正在新高」这类判断，
 * 靠肉眼 review 模板是看不出来的。
 */

/** 诚实降级的统一占位符（设计 §6：不编造 0、不编造「暂无」以外的措辞） */
export const DASH = "—";

/** 数值 + 单位，null/undefined 降级「—」（诚实降级：不编造占位值）。 */
export function fmtPct(v: number | null | undefined, digits = 2): string {
  return v == null ? DASH : v.toFixed(digits) + "%";
}

/** 比值类指标（无量纲）保留 2 位。 */
export function fmtRatio(v: number | null | undefined): string {
  return v == null ? DASH : v.toFixed(2);
}

/** 回撤文案：0 说「正在新高」，负数说「跌了多少」——0 与 -0.0 都是「在最高点」。 */
export function drawdownText(v: number | null | undefined): string {
  if (v == null) return DASH;
  if (Math.abs(v) < 0.005) return "正在新高";
  return v.toFixed(2) + "%";
}

export const PERIOD_LABEL: Record<string, string> = {
  day: "日",
  week: "周",
  month: "月"
};

/** 本轮熬了多久：自然日 → 「3 天 / 2 个月 / 1 年」这类人话，不显裸数字。 */
export function daysText(days: number | null | undefined): string {
  if (days == null) return DASH;
  if (days <= 0) return "今天";
  if (days < 60) return `${days} 天`;
  if (days < 365) return `${Math.floor(days / 30)} 个月`;
  const y = Math.floor(days / 365);
  const m = Math.floor((days % 365) / 30);
  return m > 0 ? `${y} 年 ${m} 个月` : `${y} 年`;
}

/**
 * 同类分位：**越大越好**是统一读法（后端已按指标方向取过负）。
 *
 * 只在此数据显示；同类样本 < 5 时后端不出分位（缺键即降级「—」）——
 * 2 只基金选出的「同类第一」是噪音，显示它比不显示更坏。
 *
 * 键序即展示序：固定顺序（不按对象键序），否则同一页在不同 JS 引擎下顺序可能不同。
 */
export const PEER_METRIC_LABEL: Record<string, string> = {
  current_drawdown: "本轮回撤",
  max_drawdown: "最大回撤",
  annual_volatility: "波动率",
  sharpe: "夏普",
  sortino: "索提诺",
  calmar: "卡玛",
  upi: "UPI",
  return_drawdown_ratio: "波回比",
  win_rate: "胜率"
};

/** 分位文案：「前 12%」比「第 88 分位」好懂；分位越高越靠前。 */
export function peerText(pct: number): string {
  // 分位 88 ⇒ 低于它的占 88% ⇒ 它在前 12%。四舍五入到整数百分比。
  const ahead = Math.max(1, Math.round(100 - pct));
  return `前 ${ahead}%`;
}
