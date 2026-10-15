// src/api/notification.ts
// 站内通知（对齐后端 `app/domains/notification/views.py` 的四个端点）。
// 本文件的类型自持、不写进 `src/api/types.d.ts`——后者只放跨域共享实体，
// 单域专属类型放在各自 api 文件里（#965「类型集中」的收口约定）。
import { http } from "@/utils/http";

const BASE_URL = "/api/notifications/";

/** 通知级别（后端 `Notification.level` 注释口径）：P0 强 / P1 中 / P2 弱 */
export type NotificationLevel = "P0" | "P1" | "P2";

/** 通知归类（后端 `Notification.category` 注释口径）：策略 / 自选 / 系统 */
export type NotificationCategory = "strategy" | "watchlist" | "system";

/**
 * 单条站内通知，逐字段对齐后端 `notification_service.to_dict`。
 *
 * 合规红线：title / body 由后端产出，只陈述「某条规则被触发了」这一客观事实；
 * 前端**只陈列不加工**——禁止自行改写成「建议买入 / 建议卖出」一类建议语气
 * （后端 `notification_service` 模块 docstring 第 4 条）。
 */
export interface NotificationItem {
  id: number;
  level: NotificationLevel;
  category: NotificationCategory;
  /** 消息标题（后端限长 120） */
  title: string;
  /** 消息正文（后端限长 500，可为空） */
  body: string | null;
  /** 产生来源：allocation_deviation（配比偏离）/ trend_signal（趋势）等 */
  source_type: string;
  /** 来源业务键（多为标的代码），可为空 */
  source_key: string | null;
  is_read: boolean;
  /** ISO 字符串；后端无值时为 null */
  created_at: string | null;
  /** ISO 字符串；未读时为 null */
  read_at: string | null;
}

/** 列表查询参数（对齐后端 `list_notifications` 的 query） */
export interface NotificationListParams {
  /** 只看未读，默认否 */
  unread_only?: boolean;
  /** 单页条数，后端钳制到 1~200，默认 50 */
  limit?: number;
}

/** `GET /api/notifications/` 的 data 信封 */
export interface NotificationListData {
  items: NotificationItem[];
  /** 本家庭通知总条数（分页用） */
  total: number;
  /** 未读条数：随列表一起返回，省去红点单独再发一次请求 */
  unread_count: number;
  /** 首页横栏候选：最高优先级的 1 条未读，无未读时为 null */
  banner: NotificationItem | null;
}

/** `GET /api/notifications/` 的完整响应（http 已剥壳，这里是后端 JSON 原样） */
export interface NotificationListResponse {
  data: NotificationListData;
  message?: string;
}

/** `GET /api/notifications/unread-count/` 的完整响应 */
export interface UnreadCountResponse {
  data: {
    unread_count: number;
  };
  message?: string;
}

/** `PATCH /api/notifications/<id>/read/` 的完整响应 */
export interface MarkReadResponse {
  data: {
    id: number;
    is_read: boolean;
  };
  message?: string;
}

/** `POST /api/notifications/read-all/` 的完整响应 */
export interface MarkAllReadResponse {
  data: {
    /** 本次被标记的条数，可能为 0（非错误） */
    marked: number;
  };
  message?: string;
}

/**
 * 通知列表（未读优先、新的在前），同时带回未读总数与首页横栏候选。
 * 对齐 `GET /api/notifications/`。
 */
export function getNotifications(params?: NotificationListParams) {
  return http.request<NotificationListResponse>("get", BASE_URL, {
    params: toQuery(params)
  });
}

/**
 * 仅未读条数——铃铛红点每进一次页面都要问，故独立于列表、后端也更轻。
 * 对齐 `GET /api/notifications/unread-count/`。
 */
export function getUnreadCount() {
  return http.request<UnreadCountResponse>("get", `${BASE_URL}unread-count/`);
}

/**
 * 标记单条已读（幂等）。不存在 / 不属于本家庭时后端返回 404。
 * 对齐 `PATCH /api/notifications/<id>/read/`。
 */
export function markNotificationRead(id: number) {
  return http.request<MarkReadResponse>("patch", `${BASE_URL}${id}/read/`);
}

/**
 * 全部标记已读，返回本次被标记条数。
 * 对齐 `POST /api/notifications/read-all/`。
 */
export function markAllNotificationsRead() {
  return http.request<MarkAllReadResponse>("post", `${BASE_URL}read-all/`);
}

/**
 * 布尔查询参数转字符串：后端 `_as_bool` 只认 '1'/'true'/'yes'/'on'，
 * 而 axios/qs 默认会把 true 序列化成 `unread_only=true`（能识别），
 * false 序列化成 `unread_only=false`（同样为假）——两端一致，但显式写成
 * '0'/'1' 是为了让 DevTools 里的查询串与实际语义一一对应，不受序列化器版本影响。
 */
function toQuery(params?: NotificationListParams) {
  if (!params) return undefined;
  const query: Record<string, string | number> = {};
  if (params.unread_only !== undefined) {
    query.unread_only = params.unread_only ? "1" : "0";
  }
  if (params.limit !== undefined) {
    query.limit = params.limit;
  }
  return query;
}
