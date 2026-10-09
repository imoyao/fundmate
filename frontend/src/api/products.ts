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

/** 走势区间档位（设计 §5 B 区块；默认 3M 见 §12 ⑤） */
export type TrendRange = "1M" | "3M" | "6M" | "1Y";

export interface ProductTrendResult {
  symbol: string;
  /** `close`=场内收盘价口径；`nav`=场外单位净值；空串=该品类无序列数据源（指数等） */
  kind: string;
  /** 与 values 等长的日期轴（YYYY-MM-DD） */
  dates: string[];
  values: number[];
  /** 口径脚注用：数据来源（如「price_history 前复权收盘价」） */
  source: string;
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
