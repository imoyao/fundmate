// src/api/transactions.ts
import { http } from "@/utils/http";

/** 交易流水记录（对齐 build_transaction_list 行结构；金额为元、份额为份） */
export interface TransactionRecord {
  id: number;
  /** 所属账户；账户级流水（无 symbol 的存入/税费/分红）可能为 null */
  ledger_id: number | null;
  /** 关联持仓 id；账户级流水（存入/税费等）为 null */
  position_id: number | null;
  position_name: string;
  type: string;
  asset_type: string | null;
  trade_date: string | null;
  confirm_date: string | null;
  quantity: number;
  price: number;
  fee: number;
  amount: number;
  status: string | null;
  account_name: string;
  notes: string | null;
  source: string | null;
  created_at: string | null;
}

/** 交易流水查询参数（对齐后端 list_transactions 的 query args） */
export interface TransactionListParams {
  /** 交易类型过滤（后端 txn_type 等值匹配） */
  type?: string;
  /** 时间范围：1m/3m/6m/1y/custom */
  time_range?: string;
  /** time_range=custom 时的起止日期（含边界） */
  start_date?: string;
  end_date?: string;
  status?: string;
  /** 资产类型过滤（后端经 positions 表关联） */
  asset_type?: string;
  page?: number;
  per_page?: number;
}

/** 交易流水分页响应（对齐后端信封 { data, total, page, per_page, message }） */
export interface TransactionListResponse {
  data: TransactionRecord[];
  total: number;
  page: number;
  per_page: number;
  message: string;
}

const BASE_URL = "/api/transactions";

/** 获取交易流水列表 */
export function getTransactions(params?: TransactionListParams) {
  return http.request<TransactionListResponse>("get", BASE_URL, { params });
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
