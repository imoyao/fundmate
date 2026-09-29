import { http } from "@/utils/http";
import type { ApiResponse, DeleteResponse } from "@/api/types";

/** 组合列表项（对齐后端 list_portfolios 的 MVP 字段） */
export interface PortfolioItem {
  id: number;
  name: string;
  purpose?: string | null;
  created_at?: string | null;
}

/** 组合详情（对齐后端 _portfolio_to_dict 全量字段） */
export interface PortfolioDetail extends PortfolioItem {
  description?: string | null;
  target_return?: number | null;
  target_amount?: number | null;
  target_date?: string | null;
  benchmark?: string | null;
  is_deleted: boolean;
  updated_at?: string | null;
}

/** 创建组合入参（对齐后端 PortfolioCreate） */
export interface PortfolioCreateInput {
  name: string;
  description?: string;
  purpose?: string;
  target_return?: number;
  target_amount?: number;
  target_date?: string;
  benchmark?: string;
}

/** 更新组合入参（PATCH，对齐后端 PortfolioUpdate；后端按「传入才更新」语义处理） */
export interface PortfolioUpdateInput {
  name?: string;
  description?: string;
  purpose?: string;
  target_return?: number;
  target_amount?: number;
  target_date?: string;
  benchmark?: string;
}

/** 组合持仓明细行（对齐 build_portfolio_holdings；资产行 id = asset.id + 100000） */
export interface PortfolioHoldingItem {
  id: number;
  symbol: string;
  name: string | null;
  type: string | null;
  type_label: string;
  account_name: string | null;
  /** 仅资产行下发（持仓行无此字段） */
  ledger_id?: number | null;
  quantity: number;
  current_price: number;
  avg_price: number;
  market_value: number;
  pnl: number;
  pnl_rate: number;
}

/** 获取组合列表（仅 id/name/purpose/created_at） */
export function getPortfolios() {
  return http.request<ApiResponse<PortfolioItem[]>>("get", "/api/portfolios/");
}

/** 获取组合详情 */
export function getPortfolio(id: number) {
  return http.request<ApiResponse<PortfolioDetail>>(
    "get",
    `/api/portfolios/${id}/`
  );
}

/** 创建组合 */
export function createPortfolio(data: PortfolioCreateInput) {
  return http.request<ApiResponse<PortfolioDetail>>(
    "post",
    "/api/portfolios/",
    { data }
  );
}

/** 更新组合 */
export function updatePortfolio(id: number, data: PortfolioUpdateInput) {
  return http.request<ApiResponse<PortfolioDetail>>(
    "patch",
    `/api/portfolios/${id}/`,
    { data }
  );
}

/** 删除组合（软删除，并自动解绑关联账户） */
export function deletePortfolio(id: number) {
  return http.request<DeleteResponse>("delete", `/api/portfolios/${id}/`);
}

/** 组合下所有关联账户的持仓/资产明细 */
export function getPortfolioHoldings(id: number) {
  return http.request<ApiResponse<PortfolioHoldingItem[]>>(
    "get",
    `/api/portfolios/${id}/holdings/`
  );
}
