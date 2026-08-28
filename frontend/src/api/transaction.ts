import { http } from "@/utils/http";

/** 删除单条交易流水（端点已迁至 transactions 域：DELETE /api/transactions/<id>/） */
export function deleteTransaction(transactionId: number) {
  return http.request("delete", `/api/transactions/${transactionId}/`);
}
