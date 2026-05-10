// src/api/types.d.ts
/** 后端统一响应格式 */
export interface ApiResponse<T> {
  data: T;
  message: string;
}

/** 后端错误响应格式 */
export interface ApiError {
  error: {
    code: string;
    message: string;
  };
}

/** 持仓记录 */
export interface Position {
  id: number;
  symbol: string;
  name: string | null;
  market: string;
  type: string;
  account_name: string;
  quantity: number;
  avg_price: number;
  currency: string;
  current_price: number;
  purchase_date: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

/** 创建持仓请求体 */
export interface PositionCreate {
  symbol: string;
  name?: string;
  market: string;
  type: string;
  account_name: string;
  quantity: number;
  avg_price: number;
  currency?: string;
  purchase_date: string;
  fee?: number;
  confirm_date?: string;
  notes?: string;
}

/** 更新持仓请求体 (PATCH，所有字段可选) */
export interface PositionUpdate {
  name?: string;
  account_name?: string;
  quantity?: number;
  avg_price?: number;
  current_price?: number;
  currency?: string;
  purchase_date?: string;
  notes?: string;
}

/** 仪表盘聚合数据 */
export interface SummaryData {
  total_assets_cny: number;
  total_pnl_cny: number;
  market_distribution: Record<string, number>;
}

/** 五笔钱分组枚举 */
export type AllocationType =
  | "liquid"
  | "stable"
  | "longterm"
  | "speculative"
  | "security";

/** 五笔钱分组标签映射 */
export const AllocationLabels: Record<AllocationType, string> = {
  liquid: "活钱",
  stable: "稳健底仓",
  longterm: "长期增值",
  speculative: "高风险博弈",
  security: "保险保障"
};
