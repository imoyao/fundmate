// src/api/eaccount.ts
// E账户对账与归因 API（后端 e_account_views.py，设计文档 e-account-reconciliation-design-2026-08-16）
// 信封处理与 importer.ts 一致：http.request<T> 的 T 为完整响应体（{data, message}），
// 业务数据在 data 字段，故统一用 ApiResponse<X> 包裹（与 positions/summary 等 typed 模块同约定）。
import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/** 对账冲突项（reconcile 响应 conflict_list 元素） */
export interface ConflictItem {
  record_id: number;
  symbol: string;
  name: string;
  source_broker: string | null;
  fund_manager: string | null;
  target_ledger_id: number | null;
  target_ledger_name: string | null;
  eaccount_quantity: number;
  current_quantity: number;
  current_cost: number | null;
  diff_quantity: number;
}

/** 对账结果（POST /api/e-account/reconcile/ 响应 data） */
export interface ReconcileResult {
  auto_attributed: number;
  verified: number;
  conflicts: number;
  ignored_skipped: number;
  attributed_skipped: number;
  failed_rows: Array<{ line: number; symbol: string; reason: string }>;
  conflict_list: ConflictItem[];
}

/** 对账中心条目（GET /api/e-account/reconciliation/ 响应 items 元素） */
export interface ReconciliationItem {
  record_id: number;
  symbol: string;
  name: string;
  source_broker: string | null;
  fund_manager: string | null;
  eaccount_quantity: number;
  eaccount_total: number;
  system_quantity: number;
  diff: number;
  status: "attributed" | "verified" | "ignored" | "pending";
  attributed_to: string | null;
  is_ignored: boolean;
}

/** 对账中心数据（GET /api/e-account/reconciliation/ 响应 data） */
export interface ReconciliationData {
  data_date: string | null;
  items: ReconciliationItem[];
  summary: {
    pending_count: number;
    attributed_count: number;
    ignored_count: number;
    verified_count: number;
  };
}

/** 归因决策（POST /api/e-account/attribution/ 请求 decisions 元素） */
export interface AttributionDecision {
  symbol: string;
  source_broker: string;
  fund_manager: string;
  action: "cover" | "ignore";
}

/** 归因处理明细（attribution 响应 details 元素） */
export interface AttributionDetail {
  symbol: string;
  source_broker: string;
  fund_manager: string;
  action: string;
  status: string;
  new_position_id?: number | null;
  error?: string;
}

/** 归因结果（POST /api/e-account/attribution/ 响应 data） */
export interface AttributionResult {
  success: number;
  failed: number;
  details: AttributionDetail[];
}

/** E账户持仓快照解析行（POST /api/importers/holdings/parse rows 元素，字段可缺失容错） */
export interface HoldingParseRow {
  symbol?: string;
  name?: string;
  quantity?: number | string;
  price?: number | string;
  snapshot_date?: string;
  source_broker?: string;
  fund_manager?: string;
  /** 解析失败原因（非空即错误行，前端标红禁提交） */
  error?: string | null;
}

/** E账户持仓快照解析响应（对齐后端 /holdings/parse 实际信封：data 即行数组） */
export interface HoldingParseResponse {
  data: HoldingParseRow[];
  total: number;
  error_count: number;
  duplicate_count?: number;
  ledger_id?: number | null;
  ledger_name?: string;
}

/** 解析 E账户持仓快照文件（multipart，复用 holdings/parse 逻辑） */
export function parseHoldings(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return http.request<HoldingParseResponse>(
    "post",
    "/api/importers/holdings/parse",
    {
      data: formData,
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 10000
    }
  );
}

/** 对账并落库：接收 holdings/parse 输出的 rows，返回对账结果（含冲突清单） */
export function reconcileEaccount(rows: HoldingParseRow[]) {
  return http.request<ApiResponse<ReconcileResult>>(
    "post",
    "/api/e-account/reconcile/",
    { data: { rows } }
  );
}

/** 处理对账冲突（cover/ignore，幂等） */
export function attributeEaccount(decisions: AttributionDecision[]) {
  return http.request<ApiResponse<AttributionResult>>(
    "post",
    "/api/e-account/attribution/",
    { data: { decisions } }
  );
}

/** 对账中心：影子记录 + 状态推导 + 系统侧份额汇总 */
export function getEaccountReconciliation() {
  return http.request<ApiResponse<ReconciliationData>>(
    "get",
    "/api/e-account/reconciliation/"
  );
}
