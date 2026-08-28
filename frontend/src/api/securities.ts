import { http } from "@/utils/http";
import type { SecurityPriceRange } from "@/api/types";

export interface SecurityOption {
  symbol: string;
  name: string;
  market: string;
  type: string;
}

/**
 * #948 价格区间 / 净值契约类型已集中到 frontend/src/api/types.d.ts（验收要求）。
 * 本文件仅保留请求函数。
 */

export function searchSecurities(keyword: string) {
  return http.request<any>("get", "/api/securities/search/", {
    params: { q: keyword }
  });
}

/** 股票指定日价格区间；无行情返回 data=null（保持手输不阻塞） */
export function getSecurityPriceRange(symbol: string, date?: string) {
  return http.request<{ data: SecurityPriceRange | null }>(
    "get",
    `/api/securities/${symbol}/price-range/`,
    { params: date ? { date } : {} }
  );
}
