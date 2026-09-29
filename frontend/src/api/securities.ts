import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/** 证券搜索结果项（对齐后端 /api/securities/search/） */
export interface SecurityOption {
  symbol: string;
  /** 展示用代码（如 sh600519 → 600519 的友好形态，由后端 normalizer 派生） */
  display_symbol: string;
  name: string;
  market: string;
  type: string;
}

/** 指定交易日价格区间（#948）：股票手动记账回填默认价与区间校验 */
export interface SecurityPriceRange {
  symbol: string;
  /** 行情实际日期（≤请求日期的最近交易日） */
  date: string;
  low: number;
  high: number;
  close: number | null;
}

/** 基金确认日净值（#948）：≤请求日期的最近一条单位净值 */
export interface FundNavPoint {
  fund_code: string;
  date: string;
  unit_nav: number;
  acc_nav?: number | null;
}

/** 证券搜索（代码/名称模糊匹配，精确代码优先；最多 20 条） */
export function searchSecurities(keyword: string) {
  return http.request<ApiResponse<SecurityOption[]>>(
    "get",
    "/api/securities/search/",
    {
      params: { q: keyword }
    }
  );
}

/** 股票指定日价格区间；无行情返回 data=null（保持手输不阻塞） */
export function getSecurityPriceRange(symbol: string, date?: string) {
  return http.request<{ data: SecurityPriceRange | null }>(
    "get",
    `/api/securities/${symbol}/price-range/`,
    { params: date ? { date } : {} }
  );
}
