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
  /**
   * 是否为货币基金。**三态**：
   * - `true`  = 货币基金（fund_type_id=6，或已同步万份收益记录，或名称命中货基词）
   * - `false` = 明确非货币基金
   * - `null`  = 类型未知（fund_type_id 缺失且无辅助判据）
   *
   * 2026-08-29 起由「fund_type_id === 6」升级为三态判定：本地库 fund_type_id
   * 有 88.7% 为空，旧判定会把券商渠道现金管理产品（如 026029 银河水星现金添利货币）
   * 误判为非货基，导致「活期+」搜不到。判定逻辑见后端
   * `FundService._judge_money_fund`，前端据此做「全量展示 + 选择时限制」。
   */
  is_money_fund?: boolean | null;
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

// ── 投顾组合明细只读接口（#1468）──
// advisor_holdings / advisor_adjust_histories 此前只写不读（同步任务落库但无接口暴露），
// 这两个口子把持仓与调仓明细开放给前端消费。属 market 域公开参照数据，无需登录。

/** 组合成分基金（当前最新快照） */
export interface AdvisorHoldingItem {
  fund_code: string;
  fund_name: string | null;
  /** 调仓前占比(%)，首次快照无前值 */
  pre_ratio: number | null;
  /** 调仓后 / 当前占比(%) */
  after_ratio: number | null;
  op_name: string | null;
  /** 是否已收录进本地 funds 表（暂缺时前端不提供跳转，避免点了没反应） */
  in_local_db: boolean;
}

export interface AdvisorHoldingsResult {
  code: string;
  name: string;
  platform: string;
  /** 快照日（YYYY-MM-DD）；无持仓时为 null */
  as_of_date: string | null;
  holdings: AdvisorHoldingItem[];
}

/** 单只基金的调仓明细 */
export interface AdvisorAdjustItem {
  fund_code: string;
  fund_name: string | null;
  op_name: string | null;
  pre_ratio: number | null;
  after_ratio: number | null;
}

/** 一次调仓（同一调仓日）的整体记录 */
export interface AdvisorAdjustGroup {
  adjust_date: string;
  reason: string | null;
  /** `qieman` = 由我们的持仓快照序列推导；`tiantian` = 官方接口 */
  source: string;
  items: AdvisorAdjustItem[];
}

export interface AdvisorAdjustsResult {
  code: string;
  name: string;
  platform: string;
  /** 按调仓日倒序 */
  adjusts: AdvisorAdjustGroup[];
}

/** 组合当前持仓（含成分基金是否收录本地名录） */
export function getAdvisorHoldings(code: string) {
  return http.request<ApiResponse<AdvisorHoldingsResult>>(
    "get",
    `/api/funds/advisors/${code}/holdings/`
  );
}

/** 组合调仓明细，按调仓日分组；limit = 最近 N 个调仓日（后端上限 50） */
export function getAdvisorAdjusts(code: string, limit = 3) {
  return http.request<ApiResponse<AdvisorAdjustsResult>>(
    "get",
    `/api/funds/advisors/${code}/adjusts/`,
    { params: { limit } }
  );
}
