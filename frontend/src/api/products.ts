// frontend/src/api/products.ts
import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/** 产品身份解析结果（#1963 后端契约，#1964 消费） */
export interface ProductResolveResult {
  symbol: string;
  asset_type: string;
  market: string;
  venue: string;
  display_name: string;
  /** 未登录为 null（端点是「可选登录」端点），不可当 false 用——那是「未知」不是「没有」 */
  in_watchlist: boolean | null;
  /** 同 in_watchlist */
  has_position: boolean | null;
  /** 判定来源：watchlist / position / catalog / hint，仅供排查 */
  source: string;
}

export interface ProductResolveParams {
  symbol: string;
  /** 市场消歧（同品类跨市场同码，如 000001） */
  market?: string;
  /** 交易场所消歧（EXCHANGE / OTC） */
  venue?: string;
  /** 入口提示的前端路径段品类；后端判定优先于此，仅在目录查不到时兜底 */
  asset_type?: string;
}

/** 解析产品身份。404 = 未识别的产品代码（前端走空态，不是白屏）。 */
export function resolveProduct(params: ProductResolveParams) {
  return http.request<ApiResponse<ProductResolveResult>>(
    "get",
    "/api/products/resolve/",
    { params }
  );
}

/** 基金经理条目（`/api/products/fund-profile/` 返回） */
export interface FundProfileManager {
  mgr_code: string;
  name: string;
  company: string | null;
  appointment_date: string | null;
}

/** 基金资料聚合结果（#1968）。字段缺失一律为 null，前端据此降级为「—」 */
export interface FundProfileResult {
  fund_code: string;
  name: string;
  full_name: string | null;
  /** 基金小类名（股票型 / 混合型…），直接是后端中文名，前端不另建映射表 */
  fund_type: string | null;
  /** 基金大类名 */
  fund_variety: string | null;
  /** 基金公司 */
  company: string | null;
  /** 首屏三项：单位净值 + 净值日期 + 日涨跌(%)。change_pct 为 null 表示**前一日净值缺失**，
      不是「今天没涨」——前端不可把它当 0 显示 */
  unit_nav: number | null;
  nav_date: string | null;
  prev_unit_nav: number | null;
  prev_nav_date: string | null;
  change_pct: number | null;
  /** 规模（亿元） */
  scale: number | null;
  /** 成立日期 YYYY-MM-DD */
  create_time: string | null;
  risk_level: number | null;
  benchmark: string | null;
  managers: FundProfileManager[];
  /** 费率阶梯；取不到时为 null（不阻断其余字段） */
  fee_rates: {
    fund_code: string;
    currency: string | null;
    purchase: { start_quota: number; end_quota: number | null; rate: number }[];
    redeem: { start_day: number; end_day: number | null; rate: number }[];
  } | null;
}

/** 取基金资料聚合（详情页首屏 + 资料区块）。404 = 该代码不是基金。 */
export function getFundProfile(code: string) {
  return http.request<ApiResponse<FundProfileResult>>(
    "get",
    "/api/products/fund-profile/",
    { params: { code } }
  );
}
