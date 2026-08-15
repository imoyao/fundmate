import { http } from "@/utils/http";
import type { ApiResponse } from "./types";

/** 自选资产分页响应（对齐后端信封：{ data, total, ... }，不同于标准 ApiResponse） */
export interface WatchlistPageResponse<T> {
  data: T[];
  total: number;
  page?: number;
  per_page?: number;
  message?: string;
}

export interface WatchlistItem {
  id: number;
  symbol: string;
  market: string;
  asset_type: string;
  venue: string;
  status: string; // HOLDING / WATCHING
  favorite: boolean;
  favorite_at: string | null;
  is_pinned: boolean;
  pinned_at: string | null;
  add_reason: string | null;
  notes: string | null;
  display_name: string;
  group_ids: number[];
  tag_ids: number[];
  current_price?: number;
  change_pct?: number;
  position_market_value?: number;
  /** 真实持仓统计（后端 enrich，positions 表汇总；区别于迁移透传的 cost_price/quantity） */
  holding_quantity?: number | null; // 真实持仓数量（份/股）
  holding_cost_price?: number | null; // 加权成本均价（元）
  holding_pnl?: number | null; // 持仓收益（元）
  holding_pnl_percent?: number | null; // 持仓收益率（%）
  price_at_added?: number | null; // 添加自选日最近交易日收盘价（元）
  type_label?: string; // 资产类型中文标签（后端动态字段）
}

export interface HomeSummaryItem {
  id: number;
  symbol: string;
  display_name: string;
  is_pinned: boolean;
  current_price: number | null;
  change_pct: number | null;
  position_market_value: number;
  status: string;
  venue: string;
  type_label?: string; // 资产类型中文标签（后端动态字段）
}
// 分组相关
export interface WatchlistGroup {
  id?: number;
  key?: string; // 系统分组专用
  name?: string; // 自定义分组专用
  label?: string; // 系统分组专用
  color: string | null;
  sort_order?: number;
  is_system: boolean;
  is_visible?: boolean;
  entity_type?: string;
  count: number; // 新增：资产数量
}

/** 创建自选资产 */
export function createWatchlistItem(data: {
  symbol: string;
  market?: string;
  asset_type?: string;
  venue?: string;
  add_reason?: string;
  is_pinned?: boolean;
  cost_price?: number;
  quantity?: number;
}) {
  return http.request<any>("post", "/api/watchlist/items/", { data });
}

export function getWatchlistGroups() {
  return http.request<ApiResponse<WatchlistGroup[]>>(
    "get",
    "/api/watchlist/groups/"
  );
}

export function createWatchlistGroup(data: { name: string; color?: string }) {
  return http.request<any>("post", "/api/watchlist/groups/", { data });
}

/** 更新自定义分组名称或颜色 */
export function updateWatchlistGroup(
  id: number,
  data: { name?: string; color?: string }
) {
  return http.request<any>("patch", `/api/watchlist/groups/${id}/`, { data });
}

export function deleteWatchlistGroup(id: number) {
  return http.request<any>("delete", `/api/watchlist/groups/${id}/`);
}

// 资产更新 / 删除 / 置顶 / 特别关注
export function updateWatchlistItem(id: number, data: Record<string, any>) {
  return http.request<any>("patch", `/api/watchlist/items/${id}/`, { data });
}

export function deleteWatchlistItem(id: number) {
  return http.request<any>("delete", `/api/watchlist/items/${id}/`);
}

// 分组关联
export function addItemToGroup(itemId: number, groupId: number) {
  return http.request<any>(
    "post",
    `/api/watchlist/items/${itemId}/groups/${groupId}/`
  );
}

export function removeItemFromGroup(itemId: number, groupId: number) {
  return http.request<any>(
    "delete",
    `/api/watchlist/items/${itemId}/groups/${groupId}/`
  );
}

// 标签关联
export function addTagToItem(itemId: number, tagId: number) {
  return http.request<any>(
    "post",
    `/api/watchlist/items/${itemId}/tags/${tagId}/`
  );
}

export function removeTagFromItem(itemId: number, tagId: number) {
  return http.request<any>(
    "delete",
    `/api/watchlist/items/${itemId}/tags/${tagId}/`
  );
}

/** 获取自选资产列表（支持筛选、分页等） */

export function getWatchlistItems(
  params?: Record<string, string | number | boolean>
) {
  return http.request<WatchlistPageResponse<WatchlistItem>>(
    "get",
    "/api/watchlist/items/",
    { params }
  );
}

/** 首页自选摘要：置顶优先，不足则按持仓市值降序补齐，最多5条 */
export function getHomeSummary() {
  return http.request<ApiResponse<HomeSummaryItem[]>>(
    "get",
    "/api/watchlist/home-summary/"
  );
}

// ---------- 标签相关 ----------
export interface WatchlistTag {
  id: number;
  name: string;
  color: string | null;
}

/** 获取标签 */
export function getWatchlistTags(
  params?: Record<string, string | number | boolean>
) {
  return http.request<ApiResponse<WatchlistTag[]>>("get", "/api/watchlist/tags/", {
    params
  });
}

/** 创建标签 */
export function createWatchlistTag(data: { name: string; color?: string }) {
  return http.request<any>("post", "/api/watchlist/tags/", { data });
}

/** 删除标签 */
export function deleteWatchlistTag(id: number) {
  return http.request<any>("delete", `/api/watchlist/tags/${id}/`);
}

export function updateWatchlistTag(
  id: number,
  data: { name?: string; color?: string }
) {
  return http.request<any>("patch", `/api/watchlist/tags/${id}/`, { data });
}

export function getFavorites() {
  return http.request<any>("get", "/api/watchlist/favorites/");
}
