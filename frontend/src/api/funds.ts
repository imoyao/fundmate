// frontend/src/api/funds.ts
import { http } from "@/utils/http";

interface NavResponseItem {
  fund_code: string;
  unit_nav: number;
  date: string;
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

export function searchFunds(query: string) {
  return http.request<any>("get", "/api/funds/search/", {
    params: { q: query }
  });
}

export function getFundFeeRates(fundCode: string) {
  return http.request<any>("get", `/api/funds/${fundCode}/fee-rates/`);
}
