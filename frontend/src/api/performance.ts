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

/** 获取持仓年化收益率 */
export function getPositionXirr(positionId: number) {
  return http.request<ApiResponse<XirrData>>("get", "/api/performance/xirr/", {
    params: { scope: "position", position_id: positionId }
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

/** 货币基金收益查询参数（scope=ledger 时须传 ledger_id；scope=family 无需） */
export interface MoneyFundIncomeParams {
  scope: "ledger" | "family";
  ledger_id?: number;
  start_date?: string;
  end_date?: string;
}

/** 获取货币基金收益（账户维度 / 家庭维度） */
export function getMoneyFundIncome(params: MoneyFundIncomeParams) {
  const query: Record<string, string | number> = { scope: params.scope };
  if (params.ledger_id != null) query.ledger_id = params.ledger_id;
  if (params.start_date) query.start_date = params.start_date;
  if (params.end_date) query.end_date = params.end_date;
  return http.request<ApiResponse<MoneyFundIncomeData>>(
    "get",
    "/api/performance/money-fund-income/",
    { params: query }
  );
}
