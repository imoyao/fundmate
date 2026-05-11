// src/api/summary.ts
import { http } from "@/utils/http";
import type { ApiResponse, SummaryData } from "./types";

const BASE_URL = "/api/summary/";

/** 获取首页仪表盘聚合数据 */
export function getSummary() {
  return http.request<ApiResponse<SummaryData>>("get", BASE_URL);
}
