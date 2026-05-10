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
}

const BASE_URL = "/api/transactions";

/** 获取交易流水列表 */
export function getTransactions(params?: Record<string, any>) {
  return http.request<any>("get", BASE_URL, { params });
}
