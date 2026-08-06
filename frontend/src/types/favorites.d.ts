export interface FavoriteItem {
  id: number;
  symbol: string;
  display_name: string;
  type: "stock" | "fund" | "manager" | "portfolio";
  venue?: "EXCHANGE" | "OTC";
  notes_summary?: string;
  cleared_return_pct?: number;
  holding_days?: number;
  cycle_count?: number;
  favorite_at?: string;
  updated_at?: string;
  // 用于Sparkline的数据，暂时为null
  price_history?: number[];
}
