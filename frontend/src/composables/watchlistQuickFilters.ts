/**
 * 类型快捷筛选偏好的校验归一原语（#1449，纯函数可单测）。
 *
 * 与 useWatchlistColumnVisibility 的分工同款：本文件只做「值合不合法、怎么归一」，
 * 不碰 localforage / http / Vue 状态，vitest 直接导入即可。
 */
import {
  DEFAULT_QUICK_FILTER_TYPES,
  WATCHLIST_ASSET_TYPE_OPTIONS
} from "@/views/asset/watchlist/watchlistAssetTypes";

/**
 * user_preferences 偏好键（#1337 方案 B 通用 KV 端点 /api/users/preferences/<key>/，
 * 后端零改动即可承载；首字母段与 issue 建议字段名一致）。
 */
export const QUICK_FILTERS_PREF_KEY = "watchlist_quick_filters";

/** 一层偏好值：外露类型 key 列表 + 本地时钟（updated_at 仅本地存，上云剥离） */
export interface QuickFiltersSettings {
  filters: string[];
  updated_at?: number;
}

const KNOWN_TYPES: ReadonlySet<string> = new Set(WATCHLIST_ASSET_TYPE_OPTIONS);

/**
 * 校验并归一化从本地缓存 / 云端读到的偏好值：
 * - 非数组 / 归一后为空（空数组、全部无效）→ null，调用方回退默认外露集；
 * - 非字符串与未知类型剔除（类型池删项后旧缓存不产生幽灵项）；
 * - 去重并**保留原有顺序**（顺序即用户配置的外露次序）。
 */
export function normalizeQuickFilters(raw: unknown): string[] | null {
  if (!Array.isArray(raw)) return null;
  const out: string[] = [];
  for (const item of raw) {
    if (typeof item !== "string" || !KNOWN_TYPES.has(item)) continue;
    if (!out.includes(item)) out.push(item);
  }
  return out.length > 0 ? out : null;
}

/** 默认外露集的拷贝（防调用方原地改共享常量） */
export function defaultQuickFilters(): string[] {
  return [...DEFAULT_QUICK_FILTER_TYPES];
}
