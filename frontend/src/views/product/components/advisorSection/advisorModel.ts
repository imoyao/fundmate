import type { AdvisorProfileResult } from "@/api/products";

/**
 * 「投顾组合」区块的指标构造（#980 拆分，纯函数）。
 *
 * 关键口径不能改：**指标区只渲染有值的项**。本机真实库 105 个组合实测，
 * `strategy_type` / `cum_return` / `running_days` / `benchmark` / `excess_return`
 * 填充率 0%，`host` 1.9%、`return_ytd` 2.9% —— 一排「—」是「没数据」的另一种噪声。
 */

export const DASH = "—";

/**
 * 我持有某只成分基金的**仓位事实**。
 *
 * - `cents`：我的市值（整数分，后端 `*_cents` 口径，展示经 `centsToYuan`）；
 * - `pct`：占我**权益仓位总市值**的比例（%）；分母非正时为 null，界面只显示金额。
 *
 * 为什么不只传一个布尔「已持有」（2026-11-26 用户实测）：「假如买的是观察仓，
 * 有什么价值呢」——500 元的观察位和 5 万元的真仓位，对「要不要跟这个组合」
 * 是完全不同的答案，必须一眼看到量级。
 */
export interface HeldPosition {
  cents: number;
  /** 占我权益市值的百分比；分母 ≤ 0（空仓 / 取不到）时为 null */
  pct: number | null;
}

/** 收益类指标：只保留有值的项（后端 0% 填充字段恒为 null，不占版面） */
export interface ReturnMetric {
  label: string;
  value: number | null;
}

export interface RiskMetric {
  label: string;
  text: string | null;
}

export function buildReturnMetrics(
  p: AdvisorProfileResult | null | undefined
): ReturnMetric[] {
  if (!p) return [];
  return [
    { label: "近 1 月", value: p.return_1m },
    { label: "近 3 月", value: p.return_1q },
    { label: "近 6 月", value: p.return_6m },
    { label: "近 1 年", value: p.return_1y },
    { label: "成立以来", value: p.return_since_incep },
    { label: "年化", value: p.annual_return }
  ].filter(m => m.value != null);
}

/**
 * 风险指标：与收益分开渲染，且**不用涨跌色** —— 回撤是负数，套用「跌」的绿色
 * 会读成「亏得少」，与语义不符（数字本身带负号已足够）。
 *
 * 夏普是无量纲比值，保留 3 位；回撤与波动率是百分比，2 位。
 */
export function buildRiskMetrics(
  p: AdvisorProfileResult | null | undefined
): RiskMetric[] {
  if (!p) return [];
  const items: RiskMetric[] = [
    {
      label: "最大回撤",
      text: p.max_drawdown != null ? `${p.max_drawdown.toFixed(2)}%` : null
    },
    {
      label: "年化波动率",
      text: p.volatility != null ? `${p.volatility.toFixed(2)}%` : null
    },
    {
      label: "夏普比率",
      text: p.sharpe_ratio != null ? p.sharpe_ratio.toFixed(3) : null
    }
  ];
  return items.filter(i => i.text != null);
}

/** 策略说明：摘要与详情都可能有，优先摘要（更短） */
export function strategyText(
  p: AdvisorProfileResult | null | undefined
): string {
  return p?.strategy_summary || p?.strategy_desc || "";
}

/** 收益文案：正数显式带「+」（负号自己带），缺失降级「—」 */
export function fmtPct(value: number | null): string {
  if (value == null) return DASH;
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

/** 涨跌色 class：0 与缺失都不涂色（0 不是涨） */
export function riseFallClass(value: number | null): string {
  if (value == null || value === 0) return "";
  return value > 0 ? "is-rise" : "is-fall";
}

/**
 * 「占我仓位」的文案（成分基金表的副行）。
 *
 * 两个坑都是实测出来的（2026-11-26 用户截图）：
 * - 「占我 0.0%」不成句 —— 中文里要落在「仓位」这个名词上，否则读作「占我（这个人）」；
 * - 四舍五入到 `0.0%` 更糟：明明持有 126 元，界面却说占了 0%，像数据错了。
 *   不足 0.1% 一律写 `<0.1%` —— 那是「很小」，不是「没有」。
 *
 * 分母非正时上游给 `null`（不是 0）：此时**没有比例可言**，返回空串由调用方
 * 只显示金额，不去编一个 0%。
 */
export function heldPctText(pct: number | null | undefined): string {
  if (pct == null) return "";
  return `占我仓位 ${pct < 0.1 ? "<0.1" : pct.toFixed(1)}%`;
}
