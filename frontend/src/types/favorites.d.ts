/**
 * 未竟之蹊（/the-road-not-taken）视图模型。
 *
 * 字段来源（全部为真实接口，无编造数值）：
 * - GET /api/watchlist/favorites/ → 主体（含 notes_summary / 持仓统计 / tag_ids）
 * - GET /api/watchlist/trends/    → trend（近 N 日收盘价序列，迷你走势封面）
 * - 状态「已清仓」由 GET /api/watchlist/items/?status=cleared 的 symbol 集合推导
 *   （后端不存 CLEARED 状态，见 docs/features/watchlist.md §1.3.1）
 */
export interface RoadItem {
  /** 自选记录 id */
  id: number | null;
  symbol: string;
  market: string;
  display_name: string;
  asset_type: string | null;
  venue: string | null;
  /** 一级胶囊归类（股票/基金/经理/指数） */
  entity: RoadEntityType;
  /** 持仓状态（持仓中 / 观察中 / 已清仓） */
  holdingState: RoadHoldingState;
  favorite_at: string | null;
  /** 下次复盘提醒日期（watchlist.next_review_date，用户可设） */
  next_review_date: string | null;
  is_pinned: boolean;
  notes: string | null;
  /** 后端截断的笔记摘要（80 字） */
  notes_summary: string | null;
  add_reason: string | null;
  tag_ids: number[];
  /** 近 N 日收盘价序列；无历史数据时为空数组 */
  trend: number[];
  current_price: number | null;
  price_at_added: number | null;
  holding_quantity: number | null;
  holding_pnl: number | null;
  holding_pnl_percent: number | null;
  position_market_value: number | null;
  created_at: string | null;
  updated_at: string | null;
  /** 设计预览用的示例卡（非真实数据，卡片带「示例」标记且不可保存） */
  isDemo?: boolean;
}

export type RoadEntityType = "stock" | "fund" | "manager" | "index";

export type RoadHoldingState = "holding" | "watching" | "cleared";

/** 二级状态胶囊的 key（含两个虚拟筛选：全部状态 / 待复盘） */
export type RoadStatusFilter = "all" | "review" | RoadHoldingState;
