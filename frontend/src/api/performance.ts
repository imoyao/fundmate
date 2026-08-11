import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/** 年化收益率（XIRR）响应数据，字段与后端 XirrResponse 保持一致 */
export interface XirrData {
  /** 年化收益率（小数，如 0.1234 表示 12.34%） */
  xirr: number;
  /** 总投入金额 */
  total_invested: number;
  /** 当前市值 */
  current_value: number;
  /** 总收益 */
  total_return: number;
  /** 参与计算的现金流笔数 */
  cashflow_count: number;
}

/** 获取年化收益率（scope 传 portfolio；portfolioId 省略时按家庭整体计算） */
export function getPortfolioXirr(scope: string, portfolioId?: number) {
  return http.request<ApiResponse<XirrData>>("get", "/api/performance/xirr/", {
    params: { scope, portfolio_id: portfolioId }
  });
}

/** 获取持仓年化收益率 */
export function getPositionXirr(positionId: number) {
  return http.request<ApiResponse<XirrData>>("get", "/api/performance/xirr/", {
    params: { scope: "position", position_id: positionId }
  });
}
