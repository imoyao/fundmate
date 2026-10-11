import { http } from "@/utils/http";
// 实体类型（#965 P1「类型集中」）：定义在 `api/types.d.ts`，这里既 import 供本文件
// 的函数签名使用，也re-export 给既有 31 个 `from "@/api/watchlist"` 的引用方。
// 注意 `export type { X } from` 只做对外 re-export、**不在本地引入绑定**，本文件内
// 用到这些名字时必须另有 import —— 否则 tsc 报 TS2304「Cannot find name」。
import type {
  ApiResponse,
  DeleteResponse,
  WatchlistItem,
  HomeSummaryItem,
  WatchlistGroup,
  HoldingGap,
  WatchlistTag
} from "@/api/types";

export type {
  WatchlistItem,
  HomeSummaryItem,
  WatchlistGroup,
  HoldingGap,
  WatchlistTag
} from "@/api/types";

/** 自选资产分页响应（对齐后端信封：{ data, total, ... }，不同于标准 ApiResponse） */
export interface WatchlistPageResponse<T> {
  data: T[];
  total: number;
  page?: number;
  per_page?: number;
  message?: string;
}

/**
 * 分组创建/更新的返回项（对齐后端 WatchlistGroupOut）。
 * 与列表项 WatchlistGroup 的区别：不含 count/key/label（列表 enrich 专属）。
 */
export interface WatchlistGroupMutationResult {
  id: number;
  name: string;
  color: string | null;
  sort_order: number | null;
  is_system: boolean | null;
  is_visible: boolean | null;
  entity_type: string | null;
}

/** 创建自选资产入参（对齐后端 WatchlistItemCreate） */
export interface WatchlistItemCreateInput {
  symbol: string;
  market?: string;
  asset_type?: string;
  venue?: string;
  /** 产品名称快照（#1508）：搜索接口已回显 name，随创建一并落库，
      读取端优先用快照，避免读时跨重叠码空间反查出错名。 */
  name?: string;
  add_reason?: string;
  is_pinned?: boolean;
  cost_price?: number;
  quantity?: number;
}

/** 更新自选资产入参（PATCH，对齐后端 WatchlistItemUpdate，所有字段可选） */
export interface WatchlistItemUpdateInput {
  is_pinned?: boolean;
  status?: string;
  venue?: string;
  favorite?: boolean;
  notes?: string | null;
  add_reason?: string | null;
  /** 下次复盘提醒日期（YYYY-MM-DD） */
  next_review_date?: string | null;
}

/** 创建自选资产（重复添加时后端返回 409） */
export function createWatchlistItem(data: WatchlistItemCreateInput) {
  return http.request<ApiResponse<WatchlistItem>>(
    "post",
    "/api/watchlist/items/",
    { data }
  );
}

export function getWatchlistGroups() {
  return http.request<ApiResponse<WatchlistGroup[]>>(
    "get",
    "/api/watchlist/groups/"
  );
}

/** 创建自定义分组（重名时后端返回 409） */
export function createWatchlistGroup(data: { name: string; color?: string }) {
  return http.request<ApiResponse<WatchlistGroupMutationResult>>(
    "post",
    "/api/watchlist/groups/",
    { data }
  );
}

/** 更新自定义分组（名称/颜色/排序/可见性） */
export function updateWatchlistGroup(
  id: number,
  data: {
    name?: string;
    color?: string;
    sort_order?: number;
    is_visible?: boolean;
  }
) {
  return http.request<ApiResponse<WatchlistGroupMutationResult>>(
    "patch",
    `/api/watchlist/groups/${id}/`,
    { data }
  );
}

export function deleteWatchlistGroup(id: number) {
  return http.request<DeleteResponse>("delete", `/api/watchlist/groups/${id}/`);
}

// 资产更新 / 删除 / 置顶 / 特别关注
export function updateWatchlistItem(
  id: number,
  data: WatchlistItemUpdateInput
) {
  return http.request<ApiResponse<WatchlistItem>>(
    "patch",
    `/api/watchlist/items/${id}/`,
    { data }
  );
}

export function deleteWatchlistItem(id: number) {
  return http.request<DeleteResponse>("delete", `/api/watchlist/items/${id}/`);
}

// 分组关联（加入成功后端仅返回 { message }，无 data）
export function addItemToGroup(itemId: number, groupId: number) {
  return http.request<{ message: string }>(
    "post",
    `/api/watchlist/items/${itemId}/groups/${groupId}/`
  );
}

export function removeItemFromGroup(itemId: number, groupId: number) {
  return http.request<DeleteResponse>(
    "delete",
    `/api/watchlist/items/${itemId}/groups/${groupId}/`
  );
}

// 标签关联（绑定成功后端仅返回 { message }，无 data）
export function addTagToItem(itemId: number, tagId: number) {
  return http.request<{ message: string }>(
    "post",
    `/api/watchlist/items/${itemId}/tags/${tagId}/`
  );
}

export function removeTagFromItem(itemId: number, tagId: number) {
  return http.request<DeleteResponse>(
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

/** 批量获取标的近 N 日收盘价序列（迷你走势图，#990）；无数据的 symbol 键缺省 */
export function getWatchlistTrends(symbols: string[], days = 60) {
  return http.request<{ data: Record<string, number[]>; message?: string }>(
    "get",
    "/api/watchlist/trends/",
    { params: { symbols: symbols.join(","), days } }
  );
}

/** 首页自选摘要：置顶优先，不足则按持仓市值降序补齐，最多5条 */
export function getHomeSummary() {
  return http.request<ApiResponse<HomeSummaryItem[]>>(
    "get",
    "/api/watchlist/home-summary/"
  );
}

export function getHoldingGaps() {
  return http.request<ApiResponse<HoldingGap[]>>(
    "get",
    "/api/watchlist/holding-gaps/"
  );
}

/** 一键补齐：为活跃持仓创建 HOLDING 自选记录（买入即入自选的批量版）。
 *  demote=true 时同时把无持仓的 HOLDING 项降级为 WATCHING。返回 { created, promoted, demoted }。 */
export function reconcileWatchlist(demote = true) {
  return http.request<
    ApiResponse<{ created: number; promoted: number; demoted: number }>
  >("post", "/api/watchlist/reconcile/", { data: { demote } });
}

/** 获取标签 */
export function getWatchlistTags(
  params?: Record<string, string | number | boolean>
) {
  return http.request<ApiResponse<WatchlistTag[]>>(
    "get",
    "/api/watchlist/tags/",
    {
      params
    }
  );
}

/** 创建标签（重名时后端返回 409） */
export function createWatchlistTag(data: { name: string; color?: string }) {
  return http.request<ApiResponse<WatchlistTag>>(
    "post",
    "/api/watchlist/tags/",
    { data }
  );
}

/** 删除标签（已被资产使用的标签后端返回 409 拒绝） */
export function deleteWatchlistTag(id: number) {
  return http.request<DeleteResponse>("delete", `/api/watchlist/tags/${id}/`);
}

export function updateWatchlistTag(
  id: number,
  data: { name?: string; color?: string }
) {
  return http.request<ApiResponse<WatchlistTag>>(
    "patch",
    `/api/watchlist/tags/${id}/`,
    { data }
  );
}

/** 特别关注（未竟之蹊）列表：后端已 enrich（display_name/持仓统计/notes_summary） */
export function getFavorites() {
  return http.request<ApiResponse<WatchlistItem[]>>(
    "get",
    "/api/watchlist/favorites/"
  );
}
