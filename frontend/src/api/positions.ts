// src/api/positions.ts
import { http } from "@/utils/http";
import type {
  ApiResponse,
  Position,
  PositionCreate,
  PositionGroupedResponse,
  PositionListParams,
  PositionListResponse,
  PositionTransaction,
  PositionUpdate,
  TradeValidationResult
} from "./types";

const BASE_URL = "/api/positions/";

/**
 * 获取持仓分页列表。
 * 对齐后端 list_positions 分页信封：{ data: Position[], total, page, per_page, message }。
 */
export function getPositions(params?: PositionListParams) {
  return http.request<PositionListResponse>("get", BASE_URL, { params });
}

/**
 * 按账户分组获取全部持仓。
 * 对齐后端 group_by=account 返回：{ data: {账户名: [position_dict]}, message }。
 * 独立函数而非给 getPositions 传 { group_by }，保证两条路径的信封类型互不混淆。
 */
export function getPositionsGroupedByAccount() {
  return http.request<PositionGroupedResponse>("get", BASE_URL, {
    params: { group_by: "account" }
  });
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
    headers: { "Content-Type": "application/json" }
  });
}

/** 更新一条持仓记录 (PATCH) */
export function updatePosition(id: number, data: PositionUpdate) {
  return http.request<ApiResponse<Position>>("patch", `${BASE_URL}/${id}/`, {
    data
  });
}

/** 删除持仓，可选择同时删除关联交易 */
export function deletePosition(
  id: number,
  deleteTransactions: boolean = false
) {
  return http.request<ApiResponse<null>>("delete", `${BASE_URL}/${id}/`, {
    params: { delete_transactions: deleteTransactions }
  });
}

/** 获取持仓的关联交易明细 */
export function getPositionTransactions(id: number) {
  return http.request<ApiResponse<PositionTransaction[]>>(
    "get",
    `${BASE_URL}/${id}/transactions/`
  );
}

/** 交易规则校验（卖出数量/步长等），后端返回 { valid, message } */
export function validateTradeOrder(data: {
  symbol: string;
  market?: string;
  type: string;
  current_hold: number;
  order_qty: number;
  op_type: "buy" | "sell";
}) {
  return http.request<TradeValidationResult>("post", `${BASE_URL}/validate/`, {
    data
  });
}
