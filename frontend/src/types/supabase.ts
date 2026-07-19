export type WatchlistGroup = {
  id: number;
  user_id: string;
  name: string;
  group_type: "custom" | "observation" | "system";
  is_system: boolean;
  color: string;
  created_at: string;
  updated_at: string;
};

export type WatchlistItem = {
  id: number;
  user_id: string;
  symbol: string;
  name: string;
  asset_type: "stock" | "fund" | "etf";
  venue: "EXCHANGE" | "OTC";
  is_pinned: boolean;
  favorite: boolean;
  add_reason?: string;
  status: "WATCHING" | "HOLDING" | "CLEARED";
  created_at: string;
  updated_at: string;
};

export type WatchlistTag = {
  id: number;
  user_id: string;
  name: string;
  color: string;
  created_at: string;
};
