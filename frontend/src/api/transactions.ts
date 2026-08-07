// src/api/transactions.ts
import { http } from "@/utils/http";

export interface TransactionRecord {
  id: number;
  position_id: number;
  position_name: string;
  type: string;
  trade_date: string | null;
  quantity: number;
  price: number;
  fee: number;
  amount: number;
  notes: string | null;
  created_at: string | null;
  status?: string; // 交易状态（后端动态字段）
  account_name?: string; // 账户名称（后端动态字段）
}

const BASE_URL = "/api/transactions";

/** 获取交易流水列表 */
export function getTransactions(params?: Record<string, any>) {
  return http.request<any>("get", BASE_URL, { params });
}

/** 导出全部交易流水为 CSV（携带鉴权头，blob 下载） */
export async function exportTransactions() {
  const res = await http.request<Blob>("get", `${BASE_URL}/export/`, {
    responseType: "blob"
  });
  const url = URL.createObjectURL(res);
  const a = document.createElement("a");
  a.href = url;
  a.download = `transactions_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
