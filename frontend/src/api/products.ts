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
