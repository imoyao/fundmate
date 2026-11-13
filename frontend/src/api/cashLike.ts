/**
 * 账外类现金流水（孤儿货基 / 逆回购）管理 API。
 *
 * 与 `getCashLikeBreakdown()`（`/api/summary/cash-like/`，只读逐产品汇总）互补：
 * 这里按**逐笔流水**读写，让「持仓明细里搜不到 / 管不了」的这批钱可被
 * 搜索、补录、编辑、删除、归置。
 *
 * 口径红线：本文件所有端点都只碰 `transactions`，不建 `positions` 行；
 * 归置只改 `position_id`，净额桶由后端 `summary_service` 自动收敛。
 * 前端**禁止**把这里的金额再加进任何持仓合计（双计）。
 */
import { http } from "@/utils/http";
import type { ApiResponse } from "./types";

const BASE_URL = "/api/summary/cash-like/";

/** 归置标记：这批流水已由目标持仓体现，不再单独计入类现金 */
export type CashLikeReconciled = {
  position_id: number;
  position_name: string;
  /** 系统墙钟，仅作审计，不参与任何 as-of 口径（D99） */
  at: string;
};

export type CashLikeFlow = {
  id: number;
  ledger_id: number | null;
  ledger_name: string;
  asset_type: string;
  asset_type_label: string;
  txn_type: string;
  /** 元（正数；方向由 txn_type 决定） */
  amount: number;
  position_name: string;
  symbol: string;
  /** true = 代码从同产品持仓带入，属推断，不是原始导入事实 */
  symbol_inferred: boolean;
  source: string;
  trade_date: string | null;
  confirm_date: string | null;
  entry_status: string | null;
  notes: string;
  is_income: boolean;
  position_id: number | null;
  reconciled: CashLikeReconciled | null;
  /** 复用后端 orphan_flow_delta 的判据，便于逐笔核对 */
  bucket: "net" | "income" | null;
  is_manual: boolean;
};

export type CashLikeFlowList = {
  items: CashLikeFlow[];
  total: number;
  page: number;
  per_page: number;
  has_more: boolean;
};

export type CashLikeFlowQuery = {
  ledger_id?: number;
  asset_type?: string;
  q?: string;
  /** true = 一并列出已归置到持仓的流水（用于撤销归置） */
  include_reconciled?: boolean;
  page?: number;
  per_page?: number;
};

export type CashLikeTarget = {
  id: number;
  name: string;
  symbol: string;
  asset_type: string;
  ledger_id: number | null;
  is_money_fund: boolean;
};

/** 补录类型；`repayment` = 逆回购到期回款（本金 + 可选利息） */
export type CashLikeFlowKind =
  "buy" | "sell" | "withdraw" | "dividend_cash" | "dividend_tax" | "repayment";

export type CashLikeCreateInput = {
  ledger_id: number;
  asset_type: "money_fund" | "reverse_repo";
  /** 用户显式录入的确认日；新行的 trade_date 由后端唯一写入口径按它兜底 */
  confirm_date: string;
  kind: CashLikeFlowKind;
  /** 元，> 0；repayment 时为本金回款额 */
  amount: number;
  /** repayment 专属：到期利息（元），0/不传则不落收益流水 */
  interest?: number;
  position_name?: string;
  /** 只允许用户手填或显式从同产品持仓带入；系统不批量推断 */
  symbol?: string;
  symbol_inferred?: boolean;
  source?: string;
  notes?: string;
  /** 幂等键：同一次提交重放不会重复落行 */
  client_token: string;
  /** 可选：关联的原买入流水 id，写入 extra 便于核对 */
  link_flow_id?: number;
};

export type CashLikeUpdateInput = {
  amount?: number;
  confirm_date?: string;
  /** 只允许单笔显式手填；留空 = 不改，禁止系统派生回填 */
  trade_date?: string;
  position_name?: string;
  symbol?: string;
  symbol_inferred?: boolean;
  source?: string;
  notes?: string;
  txn_type?: Exclude<CashLikeFlowKind, "repayment">;
};

export type CashLikeReconcileInput = {
  action: "attach" | "detach";
  transaction_ids: number[];
  target_position_id?: number;
};

export type CashLikeReconcileResult = {
  changed: number;
  action: "attach" | "detach";
  target_position_id: number | null;
  target_position_name: string | null;
};

/** 逐笔列表 / 搜索（持仓页用它把「账外类现金」也纳入搜索命中） */
export function getCashLikeFlows(params: CashLikeFlowQuery = {}) {
  return http.request<ApiResponse<CashLikeFlowList>>(
    "get",
    BASE_URL + "flows/",
    {
      params
    }
  );
}

/** 补录（含逆回购「到期回款」组合动作） */
export function createCashLikeFlow(data: CashLikeCreateInput) {
  return http.request<
    ApiResponse<{ ids: number[]; created: number; reused: number }>
  >("post", BASE_URL + "flows/", { data });
}

export function updateCashLikeFlow(id: number, data: CashLikeUpdateInput) {
  return http.request<ApiResponse<CashLikeFlow>>(
    "patch",
    BASE_URL + `flows/${id}/`,
    { data }
  );
}

export function deleteCashLikeFlow(id: number) {
  return http.request<ApiResponse<null>>("delete", BASE_URL + `flows/${id}/`);
}

/** 归置目标候选（同家庭 / 可收窄到同账户的活跃持仓） */
export function getCashLikeTargets(
  params: { ledger_id?: number; q?: string } = {}
) {
  return http.request<ApiResponse<{ items: CashLikeTarget[] }>>(
    "get",
    BASE_URL + "targets/",
    { params }
  );
}

/** 归置 / 撤销归置 */
export function reconcileCashLikeFlows(data: CashLikeReconcileInput) {
  return http.request<ApiResponse<CashLikeReconcileResult>>(
    "post",
    BASE_URL + "reconcile/",
    { data }
  );
}
