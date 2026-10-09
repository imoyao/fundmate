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
  /** 代表作品标记（来自 fund_managers 关联表）。false = 只是该基金的经理之一 */
  is_classic: boolean;
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
  /** 数据来源站点名（如「天天基金」）；#1969 前脚注写的是 daily_worth 这类表名 */
  source: string;
}

/** 取基金资料聚合（详情页首屏 + 资料区块）。404 = 该代码不是基金。 */
export function getFundProfile(code: string) {
  return http.request<ApiResponse<FundProfileResult>>(
    "get",
    "/api/products/fund-profile/",
    { params: { code } }
  );
}

/** 股票资料聚合结果（#1969 · 详情页股票区块）。字段缺失一律为 null，前端据此降级为「—」 */
export interface StockProfileResult {
  symbol: string;
  name: string;
  market: string | null;
  /** 品类（后端 securities.type），如 stock / etf；前端不另建映射表 */
  asset_type: string;
  currency: string | null;
  /** 行业 / 板块；securities.sector 填充率有限，缺失时降级「—」而不是编造 */
  sector: string | null;
  /** 区间统计窗口（**交易日条数**，非自然日）：后端默认 60 */
  window_days: number;
  /** 行情日期 YYYY-MM-DD；无行情为 null */
  quote_date: string | null;
  /** 最新收盘价（优先前复权 adj_close）；无行情为 null */
  close: number | null;
  /** 区间最高 / 最低（**未复权原值**，与持仓页「当日最高/最低」同口径） */
  high: number | null;
  low: number | null;
  /** 区间涨跌幅(%)（窗口首日 → 最新）。null 表示首日缺失或为 0，**不是「没涨」** */
  change_pct: number | null;
  /** 实际参与统计的交易日条数；小于 window_days 说明上市/历史不足，需如实提示 */
  trading_days: number;
  /** 数据来源站点名（如「新浪财经」）；一条行情都没有时为空串 */
  source: string;
  /** 口径说明（前复权收盘价 / 未复权高低） */
  basis: string;
}

/**
 * 取股票资料聚合（详情页股票区块）。
 *
 * 只补 `/trend/` 给不出的东西（基本资料 + 区间高低）：走势曲线仍由
 * `getProductTrend` 取，本端点**不返回序列**，同页不会出现两条行情取数链路。
 * 无行情不是错误（资料照常返回、行情字段为 null），仅代码不存在才 404。
 */
export function getStockProfile(params: { symbol: string; market?: string }) {
  return http.request<ApiResponse<StockProfileResult>>(
    "get",
    "/api/products/stock-profile/",
    { params }
  );
}

/** 走势区间档位（设计 §5 B 区块；默认 3M 见 §12 ⑤） */
export type TrendRange = "1M" | "3M" | "6M" | "1Y";

export interface ProductTrendResult {
  symbol: string;
  /** `close`=场内收盘价口径；`nav`=场外单位净值；空串=该品类无序列数据源（指数等） */
  kind: string;
  /** 与 values 等长的日期轴（YYYY-MM-DD） */
  dates: string[];
  values: number[];
  /** 数据来源**站点名**（如「新浪财经」「天天基金」）；#1969 前这里回的是内部表名 */
  source: string;
  /** 口径说明（如「前复权收盘价」「单位净值」）——与来源分开表达，前端不自行推断 */
  basis: string;
  range: TrendRange;
  /** 请求的区间天数（3M → 90） */
  requested_days: number;
  /** 实际数据跨度天数；远小于 requested_days 说明历史不足，需收敛档位 */
  available_days: number;
}

/** 取产品历史走势序列。空 dates/values 表示无数据，前端渲染空态而非报错。 */
export function getProductTrend(params: {
  symbol: string;
  range: TrendRange;
  /** 品类，由 resolve 返回后回传；后端据此选收盘价口径还是净值口径 */
  asset_type?: string;
}) {
  return http.request<ApiResponse<ProductTrendResult>>(
    "get",
    "/api/products/trend/",
    { params }
  );
}
