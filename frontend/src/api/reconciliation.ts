// src/api/reconciliation.ts
// 统一对账 API（后端 reconciliation/views.py，#1232 P1）
// 信封约定与 positions/summary 一致：业务数据在 data 字段。
import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/** 对账差异项（GET /api/reconciliation/discrepancies/ 元素） */
export interface DiscrepancyItem {
  id: number;
  domain: string;
  ledger_id: number | null;
  symbol: string;
  discrepancy_type: string; // quantity|cost|cash|orphan
  expected_value: number | null;
  actual_value: number | null;
  diff: number | null;
  status: string; // pending|cleared|ignored
  is_permanent: boolean;
  first_detected_at: string | null;
  updated_at: string | null;
}

/** 对账运行结果（POST /api/reconciliation/run/ 响应 data） */
export interface ReconciliationRunResult {
  run_id: number;
  domain: string;
  data_date: string | null;
  summary: {
    pending?: number;
    cleared?: number;
    ignored?: number;
    orphan?: number;
  };
  created: boolean;
}

/** 触发一次对账（域 B 默认；域 C 为导入后自动触发） */
export function runReconciliation(
  domain = "B"
): Promise<ApiResponse<ReconciliationRunResult>> {
  return http.post<ApiResponse<ReconciliationRunResult>, unknown>(
    "/reconciliation/run/",
    { data: { domain } }
  );
}

/** 列出活跃差异（可按域/状态筛） */
export function listDiscrepancies(params?: {
  domain?: string;
  status?: string;
}): Promise<ApiResponse<DiscrepancyItem[]>> {
  return http.get<ApiResponse<DiscrepancyItem[]>, unknown>(
    "/reconciliation/discrepancies/",
    { params }
  );
}

/** 忽略一条差异（临时或永久） */
export function ignoreDiscrepancy(
  id: number,
  payload: { permanent?: boolean; reason?: string }
): Promise<ApiResponse<{ id: number; status: string; is_permanent: boolean }>> {
  return http.post<
    ApiResponse<{ id: number; status: string; is_permanent: boolean }>,
    unknown
  >(`/reconciliation/discrepancies/${id}/ignore/`, { data: payload });
}

/** 就地补充/调整裁决请求（§5.4 / P2） */
export interface AdjustmentPayload {
  kind?: "increment" | "set";
  op_type?: string;
  discrepancy_id?: number;
  reason?: string;
  symbol?: string;
  name?: string;
  asset_type?: string;
  market?: string;
  ledger_id?: number | null;
  account_name?: string;
  quantity?: number;
  avg_price?: number;
  confirm_date?: string;
  snapshot_date?: string;
  [key: string]: unknown;
}

/** 就地补充/调整裁决响应 */
export interface AdjustmentResult {
  action: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  log_id: number;
}

/**
 * 就地补充/调整（§5.4 / P2）：工作台内直接补录，绝不跳「记一笔」。
 * - increment：补一笔缺失买卖 → process_buy_or_deposit / process_sell_or_withdraw（写流水+持仓）
 * - set：期初建仓 / 直接改数量成本 → upsert_from_holding（SET 语义，不建流水）
 */
export function applyAdjustment(
  payload: AdjustmentPayload
): Promise<ApiResponse<AdjustmentResult>> {
  return http.post<ApiResponse<AdjustmentResult>, unknown>(
    "/reconciliation/adjustments/",
    { data: payload }
  );
}

/** 账户持仓快照一致性项（GET /api/reconciliation/ledger-consistency/ 元素，#1133 §4 温柔提醒数据源） */
export interface LedgerConsistencyItem {
  ledger_id: number | null;
  symbol: string;
  name: string | null;
  /** 持仓快照日期（YYYY-MM-DD） */
  snapshot_date: string;
  /** 最近一笔流水日期（YYYY-MM-DD），无流水为 null */
  last_txn_date: string | null;
  /** 截至快照日应有份额（可读单位） */
  expected_qty: number;
  /** 当前实际份额（可读单位） */
  actual_qty: number;
  /** 差额 = 实际 − 应有（可读单位） */
  diff_qty: number;
}

/** 获取账户持仓快照一致性（只读、按需检查；不写 discrepancies 表） */
export function getLedgerConsistency(): Promise<
  ApiResponse<{ items: LedgerConsistencyItem[] }>
> {
  return http.get<ApiResponse<{ items: LedgerConsistencyItem[] }>, unknown>(
    "/reconciliation/ledger-consistency/"
  );
}
