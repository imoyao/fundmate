import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/**
 * 收益率方法（#871）：
 * - `xirr`：年化资金加权（默认）。对申赎时点敏感——同一组合不同人介入时点
 *   数字不可比；
 * - `twr`：时间加权。日因子连乘（`pnl_calendar` 的 daily_pnl 口径，#2133
 *   引擎 + #871 组合级扩展），剔除「何时进钱」的影响，跨账户 / 跨人可比；
 * - `dietz`：Modified Dietz 区间收益（线性近似，不年化），答「本月贡献多少」。
 */
export type ReturnMethod = "xirr" | "twr" | "dietz";

/**
 * 收益率响应数据，字段与后端 XirrResponse 保持一致。
 *
 * #871：`method` 决定哪个率值字段有值——
 * - `method=xirr`（默认，含不传 method 的历史调用）⇒ `xirr` 有值；
 * - `method=dietz` ⇒ `dietz` 有值（不年化）；
 * - `method=twr` ⇒ `twr` / `twr_annualized` 有值；无数据时为 `null`，
 *   调用方须降级显示 `—`，**不得**当成 0%。TWR 为总资产口径（日净资产
 *   序列天然含货币基金等现金等价物），`include_cash_equivalents` 对它不生效。
 */
export interface XirrData {
  /** 实际使用的收益率方法 */
  method?: ReturnMethod;
  /** 年化收益率（小数，如 0.1234 表示 12.34%；method=xirr） */
  xirr?: number;
  /** Modified Dietz 区间收益率，不年化（method=dietz） */
  dietz?: number;
  /** 时间加权区间收益率（method=twr；无数据时为 null） */
  twr?: number | null;
  /** 时间加权年化收益率（method=twr；无数据时为 null） */
  twr_annualized?: number | null;
  /** 累计买入金额（毛额：同一笔钱反复买卖会重复累加，**不要**当「投入本金」展示） */
  total_invested: number;
  /** 当前市值 */
  current_value: number;
  /** 历史收回金额（卖出 + 分红，不含当前市值） */
  total_withdrawn: number;
  /** 净投入 = 累计买入 − 历史收回；当前还压在里面的本金，展示口径优先用它 */
  net_invested?: number;
  /** 累计收益 = 当前市值 − 净投入（含已实现 + 未实现 + 分红，赚亏一起算） */
  total_return: number;
  /** 参与计算的现金流笔数 */
  cashflow_count: number;
  /** TWR 参与连乘的天数（method=twr） */
  days_used?: number;
  /** TWR 因缺数据被跳过的天数（method=twr；跳过而非当 0，>0 时结果只覆盖有数据的天） */
  days_skipped?: number;
}

/** 获取收益率（scope 传 portfolio；portfolioId 省略时按家庭整体计算）
 *  @param includeCashEquivalents 是否将货币基金/逆回购/现金纳入年化收益分母；默认 false=仅算主动投资
 *  @param method 收益率方法（#871）；不传走后端默认 xirr，与历史行为一致 */
export function getPortfolioXirr(
  scope: string,
  portfolioId?: number,
  includeCashEquivalents?: boolean,
  method?: ReturnMethod
) {
  const params: Record<string, string | number | boolean> = {
    scope,
    portfolio_id: portfolioId
  };
  if (includeCashEquivalents != null)
    params.include_cash_equivalents = includeCashEquivalents;
  if (method != null) params.method = method;
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
  /** family / ledger / portfolio（#871 起组合级也走同一引擎） */
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
