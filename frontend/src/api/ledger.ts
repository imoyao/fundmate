import { http } from "@/utils/http";

export interface LedgerItem {
  id: number;
  name: string;
  ledger_type: string;
  currency: string;
  notes: string;
  default_allocation?: string;
  linked_cash_ledger_id?: number | null;  // 新增
}

/** 获取用户的所有账户列表 */
export function getLedgers() {
  return http.request<any>("get", "/api/ledgers/");
}

/** 创建新的账户 */
export function createLedger(data: { name: string; ledger_type?: string;default_allocation?: string; currency?: string }) {
  return http.request<any>("post", "/api/ledgers/", { data });
}

export function updateLedger(id: number, data: {
  name?: string;
  ledger_type?: string;
  default_allocation?: string | null;
  notes?: string;
  portfolio_id?: number | null;
}) {
  return http.request("patch", `/api/ledgers/${id}/`, { data });
}

export function deleteLedger(id: number) {
  return http.request("delete", `/api/ledgers/${id}/`);
}

export function getLedgersOverview() { return http.request("get", "/api/ledgers/overview/"); }

/** 删除账户，可选择同时删除持仓 */
export function deleteLedgerWithOptions(id: number, deletePositions: boolean = false) {
  return http.request<any>("delete", `/api/ledgers/${id}/`, {
    params: { delete_positions: deletePositions },
  });
}

/** 将指定账户的持仓批量迁移到同类型目标账户 */
export function migrateLedgerPositions(sourceLedgerId: number, targetLedgerId: number) {
  return http.request<any>("post", `/api/ledgers/${sourceLedgerId}/migrations/`, {
    data: { target_ledger_id: targetLedgerId },
  });
}

// ── 账户详情页专用 ──

/** 获取账户概览卡片数据 */
export function getLedgerSummary(ledgerId: number) {
  return http.request("get", `/api/ledgers/${ledgerId}/summary/`);
}

/** 获取账户持仓明细（分页） */
export function getLedgerPositions(ledgerId: number, params: { page: number; per_page: number }) {
  return http.request("get", `/api/ledgers/${ledgerId}/positions/`, { params });
}

/** 获取账户交易记录（分页） */
export function getLedgerTransactions(ledgerId: number, params: { page: number; per_page: number }) {
  return http.request("get", `/api/ledgers/${ledgerId}/transactions/`, { params });
}

/** 编辑持仓 */
export function updateLedgerPosition(ledgerId: number, positionId: number, data: Record<string, any>) {
  return http.request("patch", `/api/ledgers/${ledgerId}/positions/${positionId}/`, { data });
}

/** 删除持仓（可选级联删除交易） */
export function deleteLedgerPosition(ledgerId: number, positionId: number, deleteTransactions = false) {
  return http.request("delete", `/api/ledgers/${ledgerId}/positions/${positionId}/`, {
    params: { delete_transactions: deleteTransactions },
  });
}

/** 编辑交易 */
export function updateLedgerTransaction(ledgerId: number, transactionId: number, data: Record<string, any>) {
  return http.request("patch", `/api/ledgers/${ledgerId}/transactions/${transactionId}/`, { data });
}

/** 删除交易 */
export function deleteLedgerTransaction(ledgerId: number, transactionId: number) {
  return http.request("delete", `/api/ledgers/${ledgerId}/transactions/${transactionId}/`);
}
