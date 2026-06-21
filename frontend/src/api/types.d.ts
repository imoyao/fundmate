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
  trade_date: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
  type_label?: string;
  market_label?: string;
  allocation_label?: string;
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
  trade_date: string;
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
  trade_date?: string;
  notes?: string;
}

/** 仪表盘聚合数据 */
export interface SummaryData {
  total_assets_cny: number;
  total_pnl_cny: number;
  market_distribution: Record<string, number>;
}
