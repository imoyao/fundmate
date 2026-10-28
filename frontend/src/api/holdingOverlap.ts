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
   * 重复投入金额（分）：Σ min(持仓市值A × 占比A, 持仓市值B × 占比B)。
   * 与 `weighted_overlap` 互补——后者说「两只基金像不像」，前者说「这笔重复值多少钱」。
   * 取 `min` 是关键：一只投 ¥0.53、一只投 ¥19,404 的同一只基金，重复的只是那 5 毛 3。
   */
  overlap_amount_cents: number;
  /**
   * 重叠定性（后端按双口径阈值 + 金额闸门判定，前端**不**二次推导）：
   * - `duplicate` 配置重复（weighted≥20 或 jaccard≥0.5，且金额过提示线）；
   * - `watch` 需留意（weighted≥10 或 jaccard≥0.3，且金额过提示线）；
   * - `low` 比例未达提示线（进弱提醒区）；
   * - `trivial` 比例可能很高，但重复投入金额低于分档线（观察仓，进弱提醒区）；
   * - `same-series` 同一只基金的不同份额（如 A/C 类），属份额重复、**不计入**
   *   `duplicate_count`。
   */
  overlap_level: "duplicate" | "watch" | "low" | "same-series" | "trivial";
  /**
   * 触发原因的说明（如「共同重仓 15 只、86.5% 仓位重叠」）；
   * `low` 为空串（前端补一句兜底），`trivial` 说明为什么降档（如「重叠 94.8% 但重复投入约 ¥12」）。
   */
  overlap_reason: string;
  common_holdings: OverlapCommonHolding[];
}

/**
 * 参与比较的一只基金（#2686）。
 *
 * `pairs` 只有「有重叠」的对，矩阵要铺满行列就必须有**全体**成员：
 * 三只基金只有一对重叠时，缺了它矩阵就只剩 2 个格子。
 */
export interface OverlapFund {
  fund_code: string;
  symbol: string;
  name: string;
  market_value_cents: number;
  /** 该基金自身最新报告期（各取各的，不强制对齐） */
  report_period: string | null;
  /** 该报告期的披露口径：`full`=半年报/年报全量，`top10`=季报前十大 */
  basis: string | null;
}

export interface OverlapUncovered {
  symbol: string;
  name: string;
  market_value_cents: number;
}

export interface HoldingOverlapData {
  /** 有重叠的基金对：先按档位、档内按重复金额降序；无重合的对不出现（没信息量） */
  pairs: OverlapPair[];
  /**
   * 参与比较的**全体**基金（市值降序，含彼此零重叠的成员）——矩阵视图铺行列用（#2686）。
   * 与 `pairs` 的区别：`pairs` 是结论（只列有重叠的对），这里是成员清单（不做结论过滤）。
   */
  funds: OverlapFund[];
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
  /** 判为「配置重复」的基金对数（不含 `same-series`，也不含弱提醒档） */
  duplicate_count: number;
  /** 弱提醒条数（`low` + `trivial`）：比例未达强提醒线，或重复金额不足分档线 */
  weak_count: number;
  /** 金额分档线（分），弱提醒区文案里的「不足 ¥X」用它，前端不另写一个数 */
  min_overlap_amount_cents: number;
  /**
   * 口径声明（后端下发，前端原样展示）：持仓快照滞后、高换手基金失真、
   * 未接入基金级换手率，以及「重复金额是按披露持仓估算的保守下界」。
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
