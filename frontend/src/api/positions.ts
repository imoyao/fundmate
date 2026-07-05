// src/api/positions.ts
import {http} from "@/utils/http";
import type {
  ApiResponse,
  Position,
  PositionCreate,
  PositionUpdate
} from "./types";

const BASE_URL = "/api/positions/";

/** 获取所有持仓记录 */
export function getPositions(params?: Record<string, any>) {
  return http.request<any>("get", BASE_URL, {params});
}

/** 新增一条持仓记录 */
export function createPosition(data: PositionCreate) {
  // 兜底默认值
  const body = {
    ...data,
    currency: data.currency || "CNY"
  };
  return http.request<ApiResponse<Position>>("post", BASE_URL, {
    data: body,
    headers: {'Content-Type': 'application/json'},
  });
}

/** 更新一条持仓记录 (PATCH) */
export function updatePosition(id: number, data: PositionUpdate) {
  return http.request<ApiResponse<Position>>("patch", `${BASE_URL}/${id}/`, {
    data
  });
}

/** 删除一条持仓记录 */
/** 删除持仓，可选择同时删除关联交易 */
export function deletePosition(id: number, deleteTransactions: boolean = false) {
  return http.request<any>("delete", `${BASE_URL}/${id}/`, {
    params: { delete_transactions: deleteTransactions },
  });
}

/** 获取持仓的关联交易明细 */
export function getPositionTransactions(id: number) {
  return http.request<any>("get", `${BASE_URL}/${id}/transactions/`);
}

// frontend/src/api/positions.ts 追加

export function validateTradeOrder(data: {
  symbol: string;
  market?: string;
  type: string;
  current_hold: number;
  order_qty: number;
  op_type: 'buy' | 'sell';
}) {
  return http.request<any>("post", `${BASE_URL}/validate/`, { data });
}
