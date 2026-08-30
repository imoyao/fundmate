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

/** 按占比批量更新某产品跨账户总价（#1176）的入参 */
export type AllocateValueRequest = {
  /** 产品代码（同一产品跨账户分摊总价） */
  symbol: string;
  /** 产品维度新总价（元），必须 > 0 */
  total_value: number;
  /** 市值录入日期 YYYY-MM-DD，默认今天 */
  as_of?: string;
  /** 限定只分摊到某个账户；缺省覆盖该家庭下全部活跃账户 */
  ledger_id?: number;
};

/** 单个账户的分摊结果 */
export type AllocateValueAllocation = {
  position_id: number;
  ledger_id: number | null;
  allocated_cents: number;
  allocated_yuan: number;
  ratio: number;
};

/** 按占比批量更新总价的返回（后端 value_allocation_service） */
export type AllocateValueResult = {
  symbol: string;
  total_value_cents: number;
  total_weight_cents: number;
  as_of: string;
  allocations: AllocateValueAllocation[];
};

/**
 * 产品维度批量更新持仓总价（#1176）。
 *
 * 后端按各账户**既有市值**占比分摊：整数分计算、尾差归占比最大一笔，
 * 保证各账户分配值之和**严格等于**传入总价（不会出现一分钱对不上）。
 * 典型场景：某投顾产品跨两个账户分别投入 2 万 / 3 万，现总价 5.1 万，
 * 直接改总价即可按占比分配为 2.04 万 / 3.06 万。
 */
export function allocateValue(data: AllocateValueRequest) {
  // 注意 BASE_URL 已带尾斜杠，此处不再拼接斜杠，避免 /api/positions//xxx
  return http.request<ApiResponse<AllocateValueResult>>(
    "post",
    `${BASE_URL}allocate-value/`,
    {
      data,
      headers: { "Content-Type": "application/json" }
    }
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
