// src/api/positions.ts
import {http} from "@/utils/http";
import type {
  ApiResponse,
  Position,
  PositionCreate,
  PositionUpdate
} from "./types";

const BASE_URL = "/api/positions";

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
export function deletePosition(id: number) {
  return http.request<ApiResponse<null>>("delete", `${BASE_URL}/${id}/`);
}
