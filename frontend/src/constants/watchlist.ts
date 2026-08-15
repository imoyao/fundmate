// src/constants/watchlist.ts
/**
 * 自选（watchlist）相关常量：系统分组、标签预设色集中管理。
 *
 * 数据色例外说明：分组/标签色是「用户数据色」（可由用户自定义，非设计令牌），
 * design.md「Data Visualization」红线认可此类例外（缺失时回退中性 token）。
 * 此处集中维护，避免散落各页内联 hex。
 */

/** 系统分组配置（自选页分组 Tab 的「全部/持仓/观察中/已清仓/特别关注」） */
export interface SystemGroupConfig {
  key: string;
  label: string;
  color: string;
  filter: Record<string, string | boolean>;
}

export const SYSTEM_GROUPS: SystemGroupConfig[] = [
  { key: "all", label: "全部", color: "#949599", filter: {} },
  {
    key: "holding",
    label: "持仓",
    color: "#e07a5f",
    filter: { status: "HOLDING" }
  },
  {
    key: "watching",
    label: "观察中",
    color: "#81b29a",
    filter: { status: "WATCHING" }
  },
  {
    key: "cleared",
    label: "已清仓",
    color: "#f2cc8f",
    filter: { cleared: true }
  },
  {
    key: "favorite",
    label: "特别关注",
    color: "#a89f94",
    filter: { favorite: true }
  }
];

/** 标签预设色（用户创建/编辑标签时可选） */
export const PRESET_TAG_COLORS = [
  "#B8A99A",
  "#9CAF88",
  "#8DA3B8",
  "#C4A0A8",
  "#9B9EB0",
  "#B6B09C"
];

/** 标签默认色（创建时未指定 / 读取缺失时回退） */
export const DEFAULT_TAG_COLOR = "#B6B09C";
