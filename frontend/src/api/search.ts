import { http } from "@/utils/http";

/** 品种差异化展示字段（#1285 消费），按 asset_type 可选出现 */
export interface AssetSearchExtra {
  platform?: string | null;
  risk_level?: string | null;
  host?: string | null;
  company?: string | null;
  exchange?: string | null;
}

/** 聚合搜索统一信封条目（#1286）：code 即 watchlist.symbol 的取值
 * （场内 SH600519 形态 / 场外基金 6 位码 / 经理 MGR_ 前缀 / 组合平台原生码）；
 * market/venue 为空串表示无市场实体（经理/组合） */
export interface AssetSearchResult {
  code: string;
  name: string;
  asset_type: string;
  market: string;
  venue: string;
  extra?: AssetSearchExtra;
}

/** 统一资产聚合搜索（证券/基金/指数/投顾组合/基金经理一次扇出） */
export function searchAssets(keyword: string) {
  return http.request<{
    data: AssetSearchResult[];
    message: string;
    error_code: number | string;
  }>("get", "/api/search/assets/", { params: { q: keyword } });
}
