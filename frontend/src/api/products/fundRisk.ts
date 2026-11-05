// frontend/src/api/products/fundRisk.ts
// 同类风险类型选择器 / 同类风险榜（#2878 子域拆分；实现逐字搬自 api/products.ts，端点契约勿改）
import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/** 榜单可选的一类基金（#167）。`count` = 当前口径下该类可上榜的只数。 */
export interface FundRiskTypeOption {
  fund_type_id: number;
  name: string;
  /** 当前口径、`basis=acc_nav` 的行数——用来显示「债券型-长期纯债（312）」 */
  count: number;
}

export interface FundRiskTypesResult {
  caliber_version: number;
  /** 只含**有快照行**的类型；按只数降序。没有数据的类型不在内（选中即空榜） */
  types: FundRiskTypeOption[];
}

/**
 * 取「当前有榜可看」的基金小类（#167 · 榜单页类型选择器）。
 *
 * 不用「全库 fund_types 名录」当选项：名录里有些类型一只都没算过，
 * 选中只会看到空榜，而用户分不清「这个类没有基金」与「我们没算」。
 */
export function getFundRiskTypes() {
  return http.request<ApiResponse<FundRiskTypesResult>>(
    "get",
    "/api/products/fund-risk-types/"
  );
}

/** 取同类型基金的风险指标榜（#167）。`fund_type_id` 必填——不做跨类榜。 */
export interface FundRiskRankingRow {
  fund_code: string;
  /** 基金简称（funds 表两步法 join；缺失为 null，前端回退显示代码） */
  fund_name?: string | null;
  fund_type_id: number | null;
  as_of: string | null;
  /**
   * 家庭私有标记（持仓体检定位，2026-10-17）：快照目标池本就是「持仓 ∪ 自选」，
   * 这两个字段让页面回答「我持有的那只在同类里排第几」。未登录 / 无此状态恒 false。
   */
  in_holdings: boolean;
  in_watchlist: boolean;
  max_drawdown: number | null;
  current_drawdown: number | null;
  drawdown_days: number | null;
  annual_return: number | null;
  annual_volatility: number | null;
  /**
   * 区间收益三列（#2284）：近1月/近3月/近1年，自然日端点（30/90/365 天）。
   * 历史不足该窗口为 null（前端降级「—」，不缩窗口凑数）。
   */
  ret_1m: number | null;
  ret_3m: number | null;
  ret_1y: number | null;
  sharpe: number | null;
  sortino: number | null;
  calmar: number | null;
  ulcer_index: number | null;
  upi: number | null;
  return_drawdown_ratio: number | null;
  win_rate: number | null;
  sample_points: number;
  /** 口径：acc_nav（正常）/ distorted / insufficient */
  basis: string;
  window_label: string;
}

export interface FundRiskRankingResult {
  fund_type_id: number;
  metric: string;
  order: "asc" | "desc";
  caliber_version: number;
  rows: FundRiskRankingRow[];
  /**
   * 因口径可疑（净值跳变 / 样本不足）被剔除的条数。
   *
   * **必须展示**：不展示的话「榜上只剩 3 只」会被读成「同类只有 3 只有数据」。
   */
  excluded_distorted: number;
}

/** 取同类基金的风险指标榜（#167）。`fund_type_id` 必填——风险比跨类别不可比。 */
export function getFundRiskRanking(params: {
  fund_type_id: number;
  metric: string;
  limit?: number;
  order?: "asc" | "desc";
  include_distorted?: boolean;
}) {
  return http.request<ApiResponse<FundRiskRankingResult>>(
    "get",
    "/api/products/fund-risk-ranking/",
    { params }
  );
}
