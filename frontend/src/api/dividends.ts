// src/api/dividends.ts
/**
 * 分红与股息（#872）API。
 *
 * 金额字段一律**整数分**（`*_cents`，见后端 `services/dividend_service.py`），
 * 展示前经 `utils/currency.ts` 的 `centsToYuan` 换算，页面内禁止散写 `/ 100`；
 * 比率字段（`*_pct`）是百分比数值（`5.0` 表示 5%），分母非正时后端返回 `null`。
 */
import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/** 统计桶：一段窗口内的分红分列汇总（金额单位：分） */
export interface DividendBucket {
  /** 现金分红 */
  cash_cents: number;
  /** 红利再投资（以份额形式发放，同样计入分红权益） */
  reinvest_cents: number;
  /** 红利税（后端已转成正数；净分红 = 现金 + 再投 − 税） */
  tax_cents: number;
  /** 净分红 = cash + reinvest − tax */
  net_cents: number;
  /** 事件数（含送股） */
  event_count: number;
  /** 送股/拆分事件数（无金额） */
  split_count: number;
}

/** 逐自然年分红桶 */
export interface DividendYearBucket extends DividendBucket {
  year: number;
}

/** 累计口径（全量流水，含已清仓与孤儿分红） */
export interface DividendTotals {
  /** 近 N 月窗口 */
  ttm: DividendBucket;
  /** 有史以来全部 */
  all_time: DividendBucket;
  first_date: string | null;
  last_date: string | null;
}

/** 逐持仓分红口径（仅含在管持仓） */
export interface DividendHolding extends DividendBucket {
  position_id: number;
  symbol: string | null;
  name: string | null;
  asset_type: string | null;
  account_name: string | null;
  ledger_id: number | null;
  cost_cents: number;
  market_value_cents: number;
  /** 净分红 / 成本 × 100 */
  yield_on_cost_pct: number | null;
  /** 现金分红 / 成本 × 100 */
  cash_yield_on_cost_pct: number | null;
  /** 净分红 / 市值 × 100 */
  yield_on_value_pct: number | null;
  all_time_cash_cents: number;
  all_time_net_cents: number;
  all_time_event_count: number;
  /** 红利再投至今浮盈（分）；人工录市值的持仓无法反推 → null */
  reinvest_gain_cents: number | null;
  last_dividend_date: string | null;
}

/** 组合口径（在管持仓，分子分母同域） */
export interface DividendPortfolio extends DividendBucket {
  holding_count: number;
  paying_count: number;
  cost_cents: number;
  market_value_cents: number;
  yield_on_cost_pct: number | null;
  cash_yield_on_cost_pct: number | null;
  yield_on_value_pct: number | null;
  reinvest_gain_cents: number | null;
}

/** 股息目标配置（写入侧返回，不含达成度） */
export interface DividendTargetConfig {
  configured: boolean;
  target_yield_pct: number | null;
  notes: string | null;
}

/** 股息目标 + 达成度（读总览时返回） */
export interface DividendTarget extends DividendTargetConfig {
  progress_pct: number | null;
  gap_pct: number | null;
  met: boolean | null;
}

export interface DividendSummary {
  as_of: string;
  period: { months: number; start: string; end: string };
  totals: DividendTotals;
  by_year: DividendYearBucket[];
  portfolio: DividendPortfolio;
  holdings: DividendHolding[];
  target: DividendTarget;
}

export interface DividendSummaryParams {
  /** 股息率与近期分红统计窗口（自然月，1~60，默认 12） */
  months?: number;
  /** 逐年汇总回溯年数（1~20，默认 5） */
  years?: number;
}

export interface DividendTargetInput {
  /** 目标年化股息率（%，0 < x ≤ 100） */
  target_yield_pct: number;
  notes?: string | null;
}

const BASE_URL = "/api/dividends/";

/** 分红与股息总览 */
export function getDividendSummary(params?: DividendSummaryParams) {
  return http.request<ApiResponse<DividendSummary>>(
    "get",
    `${BASE_URL}summary/`,
    {
      params
    }
  );
}

/** 设置 / 更新家庭股息目标 */
export function saveDividendTarget(data: DividendTargetInput) {
  return http.request<ApiResponse<DividendTargetConfig>>(
    "put",
    `${BASE_URL}target/`,
    { data }
  );
}

/** 清除股息目标（幂等） */
export function clearDividendTarget() {
  return http.request<ApiResponse<DividendTargetConfig>>(
    "delete",
    `${BASE_URL}target/`
  );
}
