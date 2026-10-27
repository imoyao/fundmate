// frontend/src/api/funds.ts
import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/** 后端 /api/funds/nav/ 返回的净值项 */
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

/** 申购费率阶梯（对齐 FundService.get_fund_fee_rates；金额为元） */
export interface FundPurchaseRateItem {
  start_quota: number;
  end_quota: number | null;
  rate: number;
  /** 固定金额档（元/笔），与 rate 互斥；大额档常见「1000 元/笔」 */
  fee_amount: number | null;
}

/** 赎回费率阶梯（对齐 FundService.get_fund_fee_rates；end_day 为 null 表示正无穷） */
export interface FundRedeemRateItem {
  start_day: number;
  end_day: number | null;
  rate: number;
}

/** 基金费率结构（对齐 /api/funds/<code>/fee-rates/ 的 data） */
export interface FundFeeRates {
  fund_code: string;
  currency: string;
  purchase: FundPurchaseRateItem[];
  redeem: FundRedeemRateItem[];
}

// 1. 获取基金单日净值（响应为 { data: [...], message } 信封）
export function calcFundNav(symbols: string[], date: string) {
  return http.request<ApiResponse<NavResponseItem[]>>(
    "post",
    "/api/funds/nav/",
    {
      data: { symbols, date }
    }
  );
}

// 2. 预估基金卖出费率与手续费
export function estimateRedeemFee(params: RedeemFeeEstimateParams) {
  return http.request<RedeemFeeEstimateResponse>(
    "post",
    "/api/funds/redeem-fee/estimate/",
    {
      data: params
    }
  );
}

// 3. 同步基金费率
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

/** 获取基金费率结构（基金代码不存在时后端返回 404） */
export function getFundFeeRates(fundCode: string) {
  return http.request<ApiResponse<FundFeeRates>>(
    "get",
    `/api/funds/${fundCode}/fee-rates/`
  );
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

// ── 相似基金只读接口（#2480）──
// 韭圈儿相似度名单（免登录，按需取 + 后端 6h 两级缓存）。
// 降级契约（与后端 issue 验收第 3 条对应）：degraded=true 时 items 为空、error
// 有值——前端显示「暂时取不到」，**不渲染空表格、不当成无相似基金**。

/** 单只相似基金 */
export interface SimilarFundItem {
  fund_code: string;
  fund_name: string;
  /**
   * 0-100 相似度分。null = 上游未打分（只给前若干名打分）——
   * 与「得分 0」是两件事，渲染「—」，不补 0。
   */
  similarity: number | null;
  /** 近 1 年收益率(%)；null = 上游未提供 */
  income_1y_pct: number | null;
  /** 上游收益口径标签（如「近1年」），原样展示 */
  window: string | null;
}

export interface SimilarFundsResult {
  fund_code: string;
  items: SimilarFundItem[];
  /** true = 上游取数失败（items 恒空），前端给「暂时取不到」而非空态 */
  degraded: boolean;
  error: string | null;
  /** 数据来源标记（恒为 jiucaishuo_similar，展示层据此注明来源） */
  source: string;
  /** 本次取数耗时（秒，调试用） */
  fetched_at: number | null;
}

/** 获取相似基金列表（详情页「相似基金」块，仅基金品类渲染） */
export function getSimilarFunds(fundCode: string) {
  return http.request<ApiResponse<SimilarFundsResult>>(
    "get",
    `/api/funds/${fundCode}/similar/`
  );
}

// ── 基金投资风格箱只读接口（#2478）──
// 数据来自 fund_style_exposures（韭圈儿 get-style-history，月度，job 落库）。
// 风格箱只覆盖基金与 ETF，股票持仓不在口径内；QDII 上游映射存疑，后端原样透出
// （fund_style_service 注释：270042 纳指100 实测「固收风格 81.28」），前端按需注明。
// 后端不返回颜色（契约：风格名是稳定字符串枚举，配色由前端令牌决定）。

/** 单风格暴露（0-100，合计应为 100；null = 该时点该风格缺失，不补 0） */
export interface FundStyleItem {
  style_name: string;
  value: number | null;
}

/** 最新风格箱（详情页首屏） */
export interface FundStyleBox {
  fund_code: string;
  /** 箱体系最新时点（YYYY-MM-DD） */
  stat_date: string;
  styles: FundStyleItem[];
  /** 暴露值最大的风格；并列取展示序首位 */
  dominant_style: string | null;
  style_period: string;
  /** 上一时点的主导风格（若有）；用于漂移信号 */
  prev_dominant_style: string | null;
  prev_period: string | null;
  /** 主导风格是否相较上一时点发生切换 */
  dominant_changed: boolean;
  /** 数据来源标记（恒为 jiucaishuo_style，展示层据此注明来源） */
  source: string;
}

/** 单一时点的 wide 风格快照（风格名 → 暴露值） */
export interface FundStyleHistoryPoint {
  stat_date: string;
  styles: Record<string, number | null>;
}

/** 风格漂移序列（月度倒序，wide 形态） */
export interface FundStyleHistory {
  fund_code: string;
  points: FundStyleHistoryPoint[];
  count: number;
}

/** 获取最新风格箱（详情页首屏）。无数据后端返回 data=null，前端降级「—」 */
export function getFundStyleLatest(fundCode: string) {
  return http.request<ApiResponse<FundStyleBox | null>>(
    "get",
    `/api/funds/${fundCode}/style/latest/`
  );
}

/**
 * 获取风格漂移序列（月度倒序，wide）。
 * @param limit 时点数上限（默认 60 ≈ 5 年，后端硬上限 500）
 */
export function getFundStyleHistory(fundCode: string, limit?: number) {
  return http.request<ApiResponse<FundStyleHistory>>(
    "get",
    `/api/funds/${fundCode}/style/history/`,
    { params: limit ? { limit } : undefined }
  );
}

/**
 * 组合加权风格暴露（家庭作用域，#2478 组合透视口子 / #2603 前端消费）。
 *
 * 口径（后端 `services/fund_style_service.portfolio_style_exposure` 定死，前端不二次推导）：
 * - 按持仓市值加权，每只基金取**各自最新时点**的风格箱；
 * - 无风格箱的持仓**不计入加权**，但全额计入分母 → `coverage_pct` 是覆盖率不是权重；
 * - `styles` 为空数组表示「算不出来」，**不等于「全部为 0」**。
 */
export interface PortfolioStyleExposure {
  /** 各风格暴露值（0-100，合计 100）；算不出来时为空数组 */
  styles: FundStyleItem[];
  /** 有风格箱的持仓基金数 */
  fund_count: number;
  covered_market_value_cents: number;
  total_market_value_cents: number;
  /** 风格数据覆盖率（0-100）：有箱体的持仓市值 / 全部持仓市值 */
  coverage_pct: number;
  /** 箱体时点区间（各基金取各自最新，故可能跨月） */
  period_from: string | null;
  period_to: string | null;
  /** 无风格箱的持仓（覆盖率不足时如实在此列出，不藏起来） */
  uncovered: { symbol: string; name: string; market_value_cents: number }[];
  /** 是否含 QDII 持仓：其风格分类为上游原值，口径存疑，展示层须注明 */
  has_qdii: boolean;
  source: string;
}

/**
 * 获取组合加权风格暴露。无持仓 / 全无风格箱数据时 styles 为空数组、coverage_pct=0。
 *
 * @param scope 三级口径（不传 = 家庭级）：`portfolio_id` 组合级 / `ledger_id` 账户级，
 * 两者互斥（后端 400）。组合详情页必须传 `portfolio_id`，否则拿到的是**全家**风格
 * ——标题写「组合风格构成」而数据是家庭级，属口径错误（同类问题 #2595）。
 */
export function getPortfolioStyle(
  scope: { ledger_id?: number; portfolio_id?: number } = {}
) {
  return http.request<ApiResponse<PortfolioStyleExposure>>(
    "get",
    `/api/funds/style/portfolio/`,
    { params: scope }
  );
}
