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

/**
 * 矩阵成员裁剪结果（#2686 第二期）。
 *
 * 规则在后端 `services/matrix_members.py` 唯一实现：累计市值覆盖 ≥90%、上限 20 只、
 * 下限 8 只。前端**只读结果**，不自己算——两张矩阵（重叠度 / 相关性）必须共用同一份
 * 成员，否则切换视图会「少了几只」，用户没法对照。
 *
 * 为什么不再是固定 12 只：2026-10-28 实测本地真实库（排除个股后 140 只基金/ETF/债），
 * top12 只覆盖 49.6% 市值、top20 覆盖 67%、top30 才 83%——固定只数在分散组合里会把
 * 一半仓位挡在矩阵外，而矩阵结论会被当成「整体分散度」来读。
 */
export interface OverlapMatrixMembers {
  /** 参与矩阵的成员（市值降序，已按覆盖规则裁剪） */
  funds: OverlapFund[];
  /** 被折叠的只数（0 = 全量展示） */
  truncated_count: number;
  /** 被折叠部分占总市值的百分比（0 = 无未覆盖部分，或市值不可用） */
  truncated_market_value_pct: number;
  /** 覆盖率目标（0~1），前端文案里的「90%」读这里，不另写数字 */
  coverage_target: number;
  max_members: number;
  min_members: number;
}

export interface HoldingOverlapData {
  /** 有重叠的基金对：先按档位、档内按重复金额降序；无重合的对不出现（没信息量） */
  pairs: OverlapPair[];
  /**
   * 参与比较的**全体**基金（市值降序，含彼此零重叠的成员）——矩阵视图铺行列用（#2686）。
   * 与 `pairs` 的区别：`pairs` 是结论（只列有重叠的对），这里是成员清单（不做结论过滤）。
   */
  funds: OverlapFund[];
  /**
   * 矩阵成员裁剪结果（#2686 第二期）：`funds` 是全量，`matrix.funds` 是裁剪后的。
   * 矩阵视图只读这里；列表/结论视图仍用 `pairs`。
   */
  matrix: OverlapMatrixMembers;
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

/**
 * 相关性格子的状态（后端 `holding_correlation._STATUS_BY_REASON` 映射）。
 *
 * 三种「没有值」**必须分开渲染**，都不许画成 0：
 * - `no_series`：该基金没有净值/价格序列（新成立、未入库）；
 * - `short_overlap`：同期交易日不足 `min_overlap`（披露日历不同、上市不足一季度）；
 * - `zero_variance`：净值长期不变（货基、长期停牌），Pearson 未定义。
 *
 * `0` 的含义是「无关」，而它们是「无信息」——两者天差地别。
 */
export type CorrelationStatus =
  | "ok"
  | "no_series"
  | "short_overlap"
  | "zero_variance";

/** 相关性矩阵成员（市值降序，后端已按覆盖规则截断） */
export interface CorrelationFund {
  fund_code: string;
  symbol: string;
  name: string;
  market_value_cents: number;
  /** 占**全部**基金持仓市值的比例（%），已截断成员之外的部分不计入 */
  market_value_pct: number;
}

/** 一对基金的相关性（上三角，`fund_code_a/b` 无序） */
export interface CorrelationCell {
  fund_code_a: string;
  fund_code_b: string;
  /** -1 ~ 1；`null` = 算不出来（看 `status`，**不是 0**） */
  correlation: number | null;
  /** 日期交集内的日收益个数（`short_overlap` 时是「差多少」的证据） */
  overlap_days: number;
  status: CorrelationStatus;
  /** 人话原因（如「同期交易日不足（12 < 60）」），用于悬停说明 */
  reason: string;
}

/** 矩阵截断规则（后端下发，前端文案不另写数字） */
export interface CorrelationMatrixRule {
  /** 目标市值覆盖率（0~1） */
  coverage_target: number;
  max_members: number;
  min_members: number;
}

export interface HoldingCorrelationData {
  /** 序列窗口（如 `1Y`） */
  window: string;
  /** 同期交易日下限（后端 `MIN_OVERLAP`，与 #994 联动分析同值） */
  min_overlap: number;
  /** 矩阵成员（已截断，市值降序） */
  funds: CorrelationFund[];
  /** 成员内两两结果（上三角） */
  cells: CorrelationCell[];
  /** **截断前**的成员总数：区分「组合里只有 3 只」与「96 只里只展开 20 只」 */
  fund_count: number;
  /** 可算出的对数（卡面要求的「先给可算出比例」） */
  computed_pairs: number;
  total_pairs: number;
  /** 被折叠的只数与市值占比（`count=0` 表示全量展开） */
  truncated: { count: number; market_value_pct: number };
  matrix_rule: CorrelationMatrixRule;
  /** 口径声明（矩阵截断、窗口敏感性、相关性固有失真），与结论同屏展示 */
  caveats: string[];
  /** 取数失败：显示「暂时取不到」，**不得**渲染成「相关性 0」 */
  degraded: boolean;
  source: string;
}

/**
 * 组合内基金两两相关性矩阵（#2686 第二交付，家庭作用域）。
 *
 * 与重叠度矩阵**同源**：成员来自同一份持仓聚合，截断规则同一个实现。相关性本身
 * 不需要持仓明细，但成员一致更重要——否则切换视图会「少了几只」。
 */
export function getHoldingCorrelation() {
  return http.request<ApiResponse<HoldingCorrelationData>>(
    "get",
    "/api/funds/overlap/correlation/"
  );
}
