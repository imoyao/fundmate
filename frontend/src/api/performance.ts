import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/** 年化收益率（XIRR）响应数据，字段与后端 XirrResponse 保持一致 */
export interface XirrData {
  /** 年化收益率（小数，如 0.1234 表示 12.34%） */
  xirr: number;
  /** 总投入金额 */
  total_invested: number;
  /** 当前市值 */
  current_value: number;
  /** 总收益 */
  total_return: number;
  /** 参与计算的现金流笔数 */
  cashflow_count: number;
}

/** 获取年化收益率（scope 传 portfolio；portfolioId 省略时按家庭整体计算）
 *  @param includeCashEquivalents 是否将货币基金/逆回购/现金纳入年化收益分母；默认 false=仅算主动投资 */
export function getPortfolioXirr(
  scope: string,
  portfolioId?: number,
  includeCashEquivalents?: boolean
) {
  const params: Record<string, string | number | boolean> = {
    scope,
    portfolio_id: portfolioId
  };
  if (includeCashEquivalents != null)
    params.include_cash_equivalents = includeCashEquivalents;
  return http.request<ApiResponse<XirrData>>("get", "/api/performance/xirr/", {
    params
  });
}

/**
 * 时间加权收益率（TWR）响应数据，字段与后端 `services/performance/twr.py` 一致（#2133）。
 *
 * 与 XIRR 的区别：XIRR 是资金加权（受投入时点影响），TWR 剔除出入金节奏、衡量组合本身表现。
 * 两者并列展示、不相加。**无数据时后端给 `null` 而不是 0**，展示层据此降级为 `—`。
 */
export interface TwrData {
  /** 区间累计 TWR（小数，如 0.0521 表示 5.21%）；无数据为 null */
  twr: number | null;
  /** 区间年化 TWR（小数）；有效跨度 <2 天时为 null */
  twr_annualized: number | null;
  /** 参与连乘的天数 */
  days_used: number;
  /** 因缺数据被跳过的天数（不是 0 收益，而是没数） */
  days_skipped: number;
  start_date: string | null;
  end_date: string | null;
  net_worth_start: number | null;
  net_worth_end: number | null;
  /** 固定为 daily_chained（逐日因子连乘） */
  method: string;
  /** family / ledger */
  scope: string;
  ledger_id: number | null;
}

/** 获取时间加权收益率（TWR，家庭级；传 ledgerId 则账户级）
 *  @param ledgerId 账户 ID；省略时按家庭整体计算 */
export function getTwr(ledgerId?: number) {
  const params: Record<string, string | number> = {};
  if (ledgerId != null) params.ledger_id = ledgerId;
  return http.request<ApiResponse<TwrData>>("get", "/api/performance/twr/", {
    params
  });
}

/** 获取持仓年化收益率 */
export function getPositionXirr(positionId: number) {
  return http.request<ApiResponse<XirrData>>("get", "/api/performance/xirr/", {
    params: { scope: "position", position_id: positionId }
  });
}

/** 获取产品级持有年化（跨账户按 symbol 汇总现金流，#1972）
 *  无成交且无市值时后端返回全 0 结构（cashflow_count = 0），
 *  调用方据此（以及请求失败时）降级显示 `—`，不显示 NaN。 */
export function getSymbolXirr(symbol: string) {
  return http.request<ApiResponse<XirrData>>("get", "/api/performance/xirr/", {
    params: { scope: "symbol", symbol }
  });
}

/** 货币基金每日收益序列项（金额为元，两位小数） */
export interface MoneyFundDailyIncome {
  /** 日期 YYYY-MM-DD */
  date: string;
  /** 当日收益（元） */
  income: number;
}

/** 货币基金收益响应数据（对齐后端 money-fund-income 契约，金额均为元） */
export interface MoneyFundIncomeData {
  /** 今日收益（元） */
  today_income: number;
  /** 累计收益（元） */
  total_income: number;
  /** 每日收益序列 */
  daily_series: MoneyFundDailyIncome[];
}

/** 货币基金收益查询参数（scope=ledger 须传 ledger_id；scope=portfolio 须传 portfolio_id；scope=family 无需） */
export interface MoneyFundIncomeParams {
  scope: "ledger" | "family" | "portfolio";
  ledger_id?: number;
  portfolio_id?: number;
  start_date?: string;
  end_date?: string;
}

/** 获取货币基金收益（账户维度 / 家庭维度 / 组合维度） */
export function getMoneyFundIncome(params: MoneyFundIncomeParams) {
  const query: Record<string, string | number> = { scope: params.scope };
  if (params.ledger_id != null) query.ledger_id = params.ledger_id;
  if (params.portfolio_id != null) query.portfolio_id = params.portfolio_id;
  if (params.start_date) query.start_date = params.start_date;
  if (params.end_date) query.end_date = params.end_date;
  return http.request<ApiResponse<MoneyFundIncomeData>>(
    "get",
    "/api/performance/money-fund-income/",
    { params: query }
  );
}
