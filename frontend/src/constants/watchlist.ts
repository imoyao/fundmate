// src/constants/watchlist.ts
/**
 * 自选（watchlist）相关常量：系统分组、标签/分组预设色集中管理。
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

/**
 * 标签/分组预设色（莫兰迪色系，低饱和、灰调柔和、区分度高）。
 * 仅作为「可选色板」与「默认色 / 受控随机取色」的候选来源，不限制后端可存任意 hex。
 * 扩到 12 色以拉开相邻色相距离，避免原 6 色近似度过高的问题。
 */
export const PRESET_TAG_COLORS: string[] = [
  "#e07a6b", // 珊瑚红
  "#5b8a9c", // 雾蓝
  "#c9a66b", // 沙金
  "#8a9a5b", // 橄榄绿
  "#9b7ca0", // 灰紫
  "#c98a8a", // 藕粉
  "#6b8e7f", // 灰绿松石
  "#d4a017", // 芥末黄
  "#7a6f9b", // 蓝紫灰
  "#b08968", // 焦糖棕
  "#5f9ea0", // 蓝绿灰
  "#cf7f96" // 玫红灰
];

/** 标签/分组默认色（创建时未指定 / 读取缺失时回退，取色板第一项） */
export const DEFAULT_TAG_COLOR = PRESET_TAG_COLORS[0];

/**
 * 在莫兰迪色板内做「受控随机」取色：不是纯随机，而是先从色板中排除已用色，
 * 再从剩余候选里随机挑一个，保证范围可控 + 用户可读性 + 界面区分度。
 * @param usedColors 已被占用的颜色集合（标签/分组现有颜色），尽量避开
 * @returns 选中的十六进制颜色
 */
export function randomMorandiColor(
  usedColors?: readonly string[] | Set<string>
): string {
  const source = usedColors ?? [];
  const used = new Set(Array.from(source).map(c => (c || "").toLowerCase()));
  const available = PRESET_TAG_COLORS.filter(c => !used.has(c.toLowerCase()));
  const pool = available.length > 0 ? available : PRESET_TAG_COLORS;
  const idx = Math.floor(Math.random() * pool.length);
  return pool[idx];
}
