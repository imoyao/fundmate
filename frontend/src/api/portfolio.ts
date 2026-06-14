import { http } from "@/utils/http";

export interface PortfolioItem {
  id: number;
  name: string;
  purpose?: string;
  created_at?: string;
}

export interface PortfolioDetail extends PortfolioItem {
  description?: string;
  target_return?: number;
  target_amount?: number;
  target_date?: string;
  benchmark?: string;
  is_deleted: boolean;
  updated_at?: string;
}

/** 获取组合列表（仅 id/name/purpose/created_at） */
export function getPortfolios() {
  return http.request<any>("get", "/api/portfolios/");
}

/** 获取组合详情 */
export function getPortfolio(id: number) {
  return http.request<any>("get", `/api/portfolios/${id}/`);
}

/** 创建组合 */
export function createPortfolio(data: {
  name: string;
  description?: string;
  purpose?: string;
  target_return?: number;
  target_amount?: number;
  target_date?: string;
  benchmark?: string;
}) {
  return http.request<any>("post", "/api/portfolios/", { data });
}

/** 更新组合 */
export function updatePortfolio(id: number, data: any) {
  return http.request<any>("patch", `/api/portfolios/${id}/`, { data });
}

/** 删除组合（软删除） */
export function deletePortfolio(id: number) {
  return http.request<any>("delete", `/api/portfolios/${id}/`);
}

// 在 portfolio.ts 中增加：
export function getPortfolioHoldings(id: number) {
  return http.request<any>("get", `/api/portfolios/${id}/holdings/`);
}
