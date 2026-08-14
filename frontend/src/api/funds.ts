// frontend/src/api/funds.ts
import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

interface NavResponseItem {
  fund_code: string;
  unit_nav: number;
  date: string;
}

/** 基金搜索结果项（对齐后端 /api/funds/search/ 返回字段） */
export interface FundSearchItem {
  code: string;
  name: string;
  type: string;
  subscription_rate: number;
  /** 基金小类 ID（Fund.fund_type_id），后端可能尚未部署，允许缺失 */
  fund_type_id?: number | null;
  /** 是否为货币基金（fund_type_id === 6），后端可能尚未部署，允许缺失 */
  is_money_fund?: boolean;
}

interface RedeemFeeEstimateParams {
  position_id: number;
  shares: number;
  sell_date: string;
}

interface RedeemFeeRuleItem {
  range: string;
  shares: number;
  rate: number;
}

interface RedeemFeeEstimateResponse {
  total_fee: number;
  details: RedeemFeeRuleItem[];
}

// 1. 获取基金单日净值（你已有的接口）
export function calcFundNav(symbols: string[], date: string) {
  return http.request<NavResponseItem[]>("post", "/api/funds/nav/", {
    data: { symbols, date }
  });
}

// 2. 🔥 新增：预估基金卖出费率与手续费
export function estimateRedeemFee(params: RedeemFeeEstimateParams) {
  return http.request<RedeemFeeEstimateResponse>(
    "post",
    "/api/funds/redeem-fee/estimate/",
    {
      data: params
    }
  );
}

// 在 openFeeRateDialog 附近添加函数
export function syncFundFees(fundCode: string) {
  return http.post(`/api/funds/${fundCode}/fee-sync/`);
}

export function searchFunds(query: string) {
  return http.request<ApiResponse<FundSearchItem[]>>(
    "get",
    "/api/funds/search/",
    {
      params: { q: query }
    }
  );
}

export function getFundFeeRates(fundCode: string) {
  return http.request<any>("get", `/api/funds/${fundCode}/fee-rates/`);
}
