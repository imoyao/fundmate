import { http } from "@/utils/http";
import type { ApiResponse } from "./types";

/** 家庭财务规划配置（晴雨表 v2 自由度分母）。金额单位：元；null = 未配置。 */
export interface FinancialPlanData {
  estimated_annual_expense: number | null;
  estimated_annual_income: number | null;
}

/** 读取本家庭的财务规划配置（未配置时两项均为 null）。 */
export function getFinancialPlan() {
  return http.request<ApiResponse<FinancialPlanData>>(
    "get",
    "/api/financial-plan/"
  );
}

/** 设置 / 更新家庭财务规划（只改显式传入的字段；显式 null 清除该项）。 */
export function putFinancialPlan(data: Partial<FinancialPlanData>) {
  return http.request<ApiResponse<FinancialPlanData>>(
    "put",
    "/api/financial-plan/",
    { data }
  );
}
