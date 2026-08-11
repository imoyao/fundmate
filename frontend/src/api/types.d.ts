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
  /** 所属账户 ID：后端 PositionOut 会输出（group_by 路径必含），分页路径可能缺失 */
  ledger_id?: number | null;
  /** 配置目标：后端 PositionOut 可能输出，前端不保证 */
  allocation?: string | null;
  /** 首次确认日期：group_by 路径必含，分页路径可能缺失 */
  confirm_date?: string | null;
  /**
   * 市值/盈亏：后端 enrich_position_dict 目前不产出这两个字段（已知 bug，
   * 见 Inventory 表格 :262/:270），如实标记为可选，避免类型谎报必有。
   */
  market_value?: number;
  pnl?: number;
}

/** 持仓分页列表请求参数（对齐后端 list_positions，仅支持分页参数） */
export interface PositionListParams {
  page?: number;
  per_page?: number;
}

/** 持仓分页响应（对齐后端分页信封：{ data, total, page, per_page, message }） */
export interface PositionListResponse {
  data: Position[];
  total: number;
  page: number;
  per_page: number;
  message: string;
}

/** group_by=account 响应（对齐后端 { data: {账户名: [position_dict]}, message }） */
export interface PositionGroupedResponse {
  data: Record<string, Position[]>;
  message: string;
}

/** 持仓关联交易明细（后端 /<id>/transactions/ 返回项） */
export interface PositionTransaction {
  id: number;
  trade_date: string | null;
  txn_type: string;
  quantity: number;
  price: number;
  amount: number;
  notes: string | null;
}

/** 交易规则校验结果（后端 /validate/ 返回 { valid, message }） */
export interface TradeValidationResult {
  valid: boolean;
  message: string;
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
