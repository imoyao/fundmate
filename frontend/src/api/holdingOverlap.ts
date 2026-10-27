import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/**
 * 组合内基金持仓重叠度（家庭作用域，#2604）。
 *
 * 口径（后端 `services/holding_overlap.py` 定死，前端不二次推导）：
 * - 每只基金取**各自最新报告期**的报告持仓（半年报/年报全量 `full` 优先于季报前十大
 *   `top10`），报告期**不强制对齐**——强制对齐会把报告期落后的基金整体排除；
 * - **披露口径不同的基金对不计算**（混算会系统性低估重叠，给出「我的基金不重叠」的
 *   错误安心），被跳过的对数由 `skipped_basis_mismatch` 如实给出；
 * - `jaccard` 是集合口径（按共同个股数），`weighted_overlap` 是加权口径
 *   （按共同持仓的 min(占净值比例) 求和，单位百分点）。
 */
export interface OverlapCommonHolding {
  stock_code: string;
  stock_name: string;
  ratio_a: number;
  ratio_b: number;
  min_ratio: number;
}

export interface OverlapPair {
  fund_code_a: string;
  fund_name_a: string;
  report_period_a: string;
  fund_code_b: string;
  fund_name_b: string;
  report_period_b: string;
  /** full=半年报/年报全量，top10=季报前十大 */
  holding_basis: string;
  jaccard: number;
  weighted_overlap: number;
  /**
   * 重叠定性（后端按双口径阈值判定，前端**不**二次推导）：
   * - `duplicate` 配置重复（weighted≥20 或 jaccard≥0.5）；
   * - `watch` 需留意（weighted≥10 或 jaccard≥0.3）；
   * - `low` 一般；
   * - `same-series` 同一只基金的不同份额（如 A/C 类），属份额重复、**不计入**
   *   `duplicate_count`。
   */
  overlap_level: "duplicate" | "watch" | "low" | "same-series";
  /** 触发原因的说明（如「共同重仓 15 只、86.5% 仓位重叠」；`low` 时为空串） */
  overlap_reason: string;
  common_holdings: OverlapCommonHolding[];
}

export interface OverlapUncovered {
  symbol: string;
  name: string;
  market_value_cents: number;
}

export interface HoldingOverlapData {
  /** 有重叠的基金对，按加权口径降序；无重合的对不出现（没信息量） */
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
  /** 判为「配置重复」的基金对数（不含 `same-series` 的份额重复） */
  duplicate_count: number;
  /**
   * 口径声明（后端下发，前端原样展示）：持仓快照滞后、高换手基金失真，
   * 以及「未接入基金级换手率，无法自动标出高换手」。
   */
  caveats: string[];
  /** 取数失败时为 true；此时不得渲染成「重叠 0%」 */
  degraded: boolean;
  source: string;
}

/**
 * 组合内基金持仓重叠度。
 *
 * ⚠️ `pairs` 为空有三种成因，含义完全不同，**不得一律渲染成「重叠 0%」**：
 * 1. `degraded=true` —— 取数失败，显示「暂时取不到」；
 * 2. `fund_count < 2` —— 可比基金不足 2 只，**算不出**；
 * 3. `fund_count >= 2` 且 pairs 为空 —— 算出来了，结论就是**确实不重叠**。
 */
export function getHoldingOverlap() {
  return http.request<ApiResponse<HoldingOverlapData>>(
    "get",
    "/api/funds/overlap/"
  );
}
