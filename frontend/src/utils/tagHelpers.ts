// src/utils/tagHelpers.ts
/**
 * 自选标签工具：按 id 从标签列表查找名称/颜色（纯函数）。
 * 供 watchlist 页面及 TagManagerDialog / TagEditorDialog 共用。
 */
import type { WatchlistTag } from "@/api/watchlist";
import { DEFAULT_TAG_COLOR } from "@/constants/watchlist";

/** 按 id 取标签名，缺失回退 "?" */
export function findTagName(tags: WatchlistTag[], tagId: number): string {
  return tags.find(t => t.id === tagId)?.name || "?";
}

/** 按 id 取标签色，缺失回退 DEFAULT_TAG_COLOR */
export function findTagColor(
  tags: WatchlistTag[],
  tagId: number
): string {
  return tags.find(t => t.id === tagId)?.color || DEFAULT_TAG_COLOR;
}
