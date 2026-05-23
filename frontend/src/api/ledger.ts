import { http } from "@/utils/http";

export interface LedgerItem {
  id: number;
  name: string;
  ledger_type: string;
  currency: string;
  notes: string;
  default_allocation?: string;
}

/** 获取用户的所有账户列表 */
export function getLedgers() {
  return http.request<any>("get", "/api/ledgers/");
}

/** 创建新的账户 */
export function createLedger(data: { name: string; ledger_type?: string;default_allocation?: string; currency?: string }) {
  return http.request<any>("post", "/api/ledgers/", { data });
}
