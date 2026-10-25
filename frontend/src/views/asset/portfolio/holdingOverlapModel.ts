/**
 * 组合内基金持仓重叠度面板的派生逻辑（#2604）。
 *
 * 提到纯模块的原因与 `views/asset/family/familyMemberModel.ts` 相同：vitest 的 node
 * 环境拉不起渲染器（会连带 router / supabase），组件里可测的判定必须落在这里。
 *
 * **本模块存在的唯一理由是把「没有重叠」的三种成因分开**：
 * 1. `degraded` —— 取数失败，显示「暂时取不到」；
 * 2. `fund_count < 2` —— 可比基金不足 2 只，**算不出**（不是「不重叠」）；
 * 3. `fund_count >= 2` 且 pairs 为空 —— 算出来了，结论就是**确实不重叠**。
 *
 * 把这三种都渲染成「重叠 0%」是**错误安心**：用户会以为已经查过、结果是零重合。
 */

/** 共同重仓股明细 */
export interface OverlapCommonHolding {
  stock_code: string;
  /** 名称只作展示（同一只股票在不同基金里的写法可能不同） */
  stock_name: string;
  ratio_a: number;
  ratio_b: number;
  min_ratio: number;
}

/** 一对有重叠的基金 */
export interface OverlapPair {
  fund_code_a: string;
  fund_name_a: string;
  report_period_a: string;
  fund_code_b: string;
  fund_name_b: string;
  report_period_b: string;
  /** 披露口径：full=半年报/年报全量，top10=季报前十大 */
  holding_basis: string;
  /** 集合口径重叠度（0~1） */
  jaccard: number;
  /** 加权口径重叠度（百分点），按共同持仓的 min(占净值比例) 求和 */
  weighted_overlap: number;
  common_holdings: OverlapCommonHolding[];
}

/** 无持仓明细的持仓 */
export interface OverlapUncovered {
  symbol: string;
  name: string;
  market_value_cents: number;
}

/** 重叠度接口出参 */
export interface HoldingOverlapData {
  pairs: OverlapPair[];
  /** 参与计算的基金数 */
  fund_count: number;
  /** 因披露口径不同被跳过的对数 */
  skipped_basis_mismatch: number;
  /** 因占比缺失被排除的持仓行数 */
  skipped_null_ratio: number;
  total_market_value_cents: number;
  /** 有持仓明细的基金市值 / 全部持仓市值 * 100 */
  coverage_pct: number;
  uncovered: OverlapUncovered[];
  /** 取数失败时为 true */
  degraded: boolean;
  source: string;
}

export type OverlapPanelState =
  "degraded" | "not-computable" | "no-overlap" | "has-pairs";

/** 面板状态判定：三种「没有重叠」的成因必须分开 */
export function resolveOverlapPanelState(
  data: HoldingOverlapData | null | undefined
): OverlapPanelState {
  if (!data || data.degraded) return "degraded";
  if ((data.fund_count ?? 0) < 2) return "not-computable";
  if (!data.pairs || data.pairs.length === 0) return "no-overlap";
  return "has-pairs";
}

/** 加权重叠度格式化（百分点） */
export function formatWeightedOverlap(
  value: number | null | undefined
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(1)}%`;
}

/** 集合口径重叠度格式化（0~1 → 百分比） */
export function formatJaccard(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(0)}%`;
}

/** 披露口径的中文名 */
export function describeBasis(basis: string | null | undefined): string {
  if (basis === "full") return "半年报/年报全量";
  if (basis === "top10") return "季报前十大";
  return basis || "口径未知";
}

/**
 * 报告期错配的提示。
 * 两只基金的报告期不同时，重叠度天然带时点差——必须让用户知道，
 * 否则「62% 重叠」会被当成同一时点的精确结论。
 */
export function describePeriodMismatch(
  pair: OverlapPair | null | undefined
): string {
  if (!pair) return "";
  if (pair.report_period_a === pair.report_period_b) return "";
  return `报告期不同（${pair.report_period_a} / ${pair.report_period_b}），重叠度带时点差`;
}

/** 覆盖率说明文案 */
export function describeCoverage(
  data: HoldingOverlapData | null | undefined
): string {
  const pct = data?.coverage_pct ?? 0;
  const n = data?.fund_count ?? 0;
  return `持仓明细覆盖 ${pct.toFixed(1)}%，${n} 只基金参与比较`;
}

/** 口径跳过说明：披露口径不同的基金对没有比较，必须如实说 */
export function describeSkipped(
  data: HoldingOverlapData | null | undefined
): string {
  const basis = data?.skipped_basis_mismatch ?? 0;
  const nullRatio = data?.skipped_null_ratio ?? 0;
  const parts: string[] = [];
  if (basis > 0) {
    parts.push(`${basis} 对因披露口径不同（半年报全量 vs 季报前十大）未比较`);
  }
  if (nullRatio > 0) {
    parts.push(`${nullRatio} 条持仓因占比缺失未计入`);
  }
  return parts.join("；");
}
