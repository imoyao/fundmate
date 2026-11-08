import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/**
 * 自选提醒（到价 / 单日跌幅 / 回撤）。
 *
 * 对齐后端 `domains/watchlist/alert_views.py`：
 * - 阈值一律由前端下发，后端只有默认值（`defaults`），不在后端写死；
 * - 家庭默认口径（`settings`）与逐标的规则（`rules`）是两层：
 *   单标的规则「存在但停用」= 该标的关掉这类提醒，即使家庭默认开着。
 */

export type WatchlistAlertType =
  "PRICE_UP" | "PRICE_DOWN" | "CHANGE_PCT" | "DRAWDOWN";

/** 幅度类（可在家庭默认里配置的类型；到价是逐标的） */
export type WatchlistMagnitudeType = "CHANGE_PCT" | "DRAWDOWN";

export interface WatchlistAlertRule {
  id: number;
  item_id: number;
  alert_type: WatchlistAlertType;
  /** 到价：元；幅度类：百分比正数（5 表示 5%） */
  threshold_value: number;
  is_active: boolean;
  last_triggered_at: string | null;
  symbol?: string;
  name?: string;
  asset_type?: string | null;
  venue?: string | null;
}

/** 单标的生效口径：item=自有规则；family=沿用家庭默认；off=关闭 */
export interface WatchlistAlertEffective {
  is_enabled: boolean;
  threshold_value: number;
  window_days: number | null;
  source: "item" | "family" | "off";
}

export interface WatchlistAlertDefaults {
  threshold_value: number;
  window_days: number | null;
  level: string;
}

export interface WatchlistAlertSettingsItem {
  alert_type: WatchlistMagnitudeType;
  is_enabled: boolean;
  threshold_value: number;
  window_days: number | null;
  level: string;
  is_customized: boolean;
}

export interface WatchlistAlertSettingsPayload {
  items: WatchlistAlertSettingsItem[];
  defaults: Record<WatchlistMagnitudeType, WatchlistAlertDefaults>;
}

export interface WatchlistItemAlerts {
  item: {
    id: number;
    symbol: string;
    name: string;
    asset_type?: string | null;
    venue?: string | null;
  };
  rules: WatchlistAlertRule[];
  effective: Record<WatchlistMagnitudeType, WatchlistAlertEffective>;
  quote: {
    latest: number | null;
    prev: number | null;
    window_high: number | null;
    as_of: string | null;
  };
  defaults: Record<WatchlistMagnitudeType, WatchlistAlertDefaults>;
}

export function getItemAlerts(itemId: number) {
  return http.request<ApiResponse<WatchlistItemAlerts>>(
    "get",
    `/api/watchlist/items/${itemId}/alerts/`
  );
}

export function upsertItemAlert(
  itemId: number,
  data: {
    alert_type: WatchlistAlertType;
    threshold_value: number;
    is_active?: boolean;
  }
) {
  return http.request<ApiResponse<WatchlistAlertRule>>(
    "post",
    `/api/watchlist/items/${itemId}/alerts/`,
    { data }
  );
}

export function patchAlert(
  alertId: number,
  data: { threshold_value?: number; is_active?: boolean }
) {
  return http.request<ApiResponse<WatchlistAlertRule>>(
    "patch",
    `/api/watchlist/alerts/${alertId}/`,
    { data }
  );
}

export function deleteAlert(alertId: number) {
  return http.request<ApiResponse<{ id: number; deleted: boolean }>>(
    "delete",
    `/api/watchlist/alerts/${alertId}/`
  );
}

export function getAlertSettings() {
  return http.request<ApiResponse<WatchlistAlertSettingsPayload>>(
    "get",
    "/api/watchlist/alerts/settings/"
  );
}

export function updateAlertSettings(
  items: Array<{
    alert_type: WatchlistMagnitudeType;
    is_enabled: boolean;
    threshold_value: number;
    window_days?: number | null;
  }>
) {
  return http.request<ApiResponse<WatchlistAlertSettingsPayload>>(
    "put",
    "/api/watchlist/alerts/settings/",
    { data: { items } }
  );
}
