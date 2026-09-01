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
