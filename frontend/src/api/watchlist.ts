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
  /** 自选记录 id；持仓分组返回的虚拟行（真实持仓聚合）无自选记录，恒为 null，前端据此禁用行操作 */
  id: number | null;
  symbol: string;
  market: string;
  asset_type: string;
  venue: string;
  status: string; // HOLDING / WATCHING
  favorite: boolean;
  favorite_at: string | null;
  /** 下次复盘提醒日期（未竟之蹊卡片底部复盘提醒，用户可设） */
  next_review_date?: string | null;
  is_pinned: boolean;
  pinned_at: string | null;
  add_reason: string | null;
  notes: string | null;
  /** 笔记摘要（仅 favorites 接口下发，后端截断 80 字） */
  notes_summary?: string | null;
  created_at?: string;
  updated_at?: string;
  display_name: string;
  group_ids: number[];
  /** 所属分组名称列表（后端 enrich，#1332 所属分组列与排序用） */
  group_names?: string[];
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
  /** 投顾组合补充信息（后端 enrich，仅 AdvisorPortfolio 命中时有值；普通标的恒 null）。
   *  供产品列渲染分层信息行「平台 · 主理人 · 策略」，避免与代码/类型/标签挤一行 */
  advisor_platform?: string | null; // QIEMAN/DANJUAN/TIANTIAN/YINGMI
  advisor_host?: string | null; // 主理人
  advisor_strategy_type?: string | null; // 策略类型（均衡/进取/稳健）
  advisor_org_name?: string | null; // 主理人所属机构/平台方
  manager_company?: string | null; // 基金经理所属基金公司（仅 asset_type=manager 有值）
  // ── 可转债条款（#1285 消费侧 / #1393）──
  // 仅 asset_type=bond 且后端 convertible_bond_terms 命中时有值，其余 null。
  // 数据源：集思录强赎（bond_cb_redeem_jsl）+ 东财基本信息（bond_zh_cov），免 cookie。
  bond_convert_price?: number | null; // 转股价（元）
  bond_convert_value?: number | null; // 转股价值（元）
  bond_premium_rate?: number | null; // 转股溢价率（%）
  bond_force_redeem_price?: number | null; // 强赎触发价（元）
  bond_redeem_count?: number | null; // 强赎天计数（已达）
  bond_redeem_required?: number | null; // 强赎触发所需天数
  bond_redeem_status?: string | null; // 强赎状态
  bond_rating?: string | null; // 信用评级
  bond_maturity_date?: string | null; // 到期日（前端据此算剩余年限）
  bond_remain_size?: number | null; // 剩余规模（亿元）
  bond_issue_size?: number | null; // 发行规模（亿元）
  bond_stock_name?: string | null; // 正股名称
  // ── 指数估值（#1285 消费侧「指数」品类 / #1394）──
  // 仅 asset_type=index 且后端 index_valuations 命中时有值；来源中证官方（免 cookie）。
  index_pe?: number | null; // 市盈率（官方列「市盈率1」）
  index_pe_2?: number | null; // 市盈率2（官方列名，口径以官方为准）
  index_dividend_yield?: number | null; // 股息率(%)（官方列「股息率1」）
  index_valuation_date?: string | null; // 估值日期（口径透明：展示「截至 X」）
  // ── 基金最大回撤（#1285 消费侧「基金」品类 / 设计 §3.10）──
  // §3.10 要求「存口径元数据，不只存数字」，故口径项随值一并下发，由前端展示。
  fund_max_drawdown?: number | null; // 最大回撤(%)，负值
  fund_max_drawdown_basis?: string | null; // current_tenure|prev_tenure|fixed_3y|insufficient
  fund_max_drawdown_window?: string | null; // 窗口描述（如「近3年」）
  fund_max_drawdown_as_of?: string | null; // 序列最后净值日（「截至」）
  // ── 跨渠道关联（#1285 设计 §3.8）：数量角标 + 浮层明细 ──
  // link_type 两类：index_etf（指数↔场内 ETF）、etf_feeder（场内 ETF↔场外联接）。
  // 实测 akshare 无「跟踪标的」字段，关联靠名称匹配，落库口径覆盖率约 66.4%。
  link_count?: number | null;
  links?: { code: string; name: string | null; link_type: string | null }[];
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
  asset_type?: string | null; // 资产类型（后端返回，用于价格精度判定）
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

/** 持仓缺口：有活跃持仓但未加入自选的标的列表（前端 banner 引导一键加入）。 */
export interface HoldingGap {
  symbol: string;
  name: string;
  asset_type: string | null;
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
  return http.request<ApiResponse<WatchlistTag[]>>(
    "get",
    "/api/watchlist/tags/",
    {
      params
    }
  );
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

/** 特别关注（未竟之蹊）列表：后端已 enrich（display_name/持仓统计/notes_summary） */
export function getFavorites() {
  return http.request<ApiResponse<WatchlistItem[]>>(
    "get",
    "/api/watchlist/favorites/"
  );
}
