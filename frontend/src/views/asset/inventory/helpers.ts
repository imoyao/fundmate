/**
 * 全面盘点页（InventoryHome）纯函数工具。
 *
 * 自 `views/asset/inventory/index.vue` 拆出（#955）。全部为无副作用的纯函数，
 * 供页面与子组件共用：颜色换算、大类 / 细分标签解析、投资分布分组构建。
 */

import { getCssVar } from "@/composables/echarts/theme";
import {
  ALLOCATION_OPTIONS,
  INVESTMENT_MINOR_CATEGORIES,
  majorCategoryLabel
} from "@/constants";
import type { AssetRecord } from "@/api/assets";
import { INVENTORY_CATEGORIES } from "./constants";

/** 后端 `GET /api/summary/groups/?dimension=type` 的单个分组 */
export interface AssetGroupRaw {
  name: string;
  total?: number;
  count?: number;
}

/** 「投资分布」卡片的一项（股票 + 可转债 合并为「股票」，基金独立） */
export interface InvestmentGroup {
  type: string;
  label: string;
  icon: string;
  color: string;
  total: number;
  count: number;
}

/**
 * 取异常文案：兼容 axios 抛出的 Error 与后端信封返回的 `{ message }`，
 * 都没有时回退到调用方给的兜底文案。
 */
export function getErrorMessage(e: unknown, fallback: string): string {
  return (e as { message?: string } | null)?.message || fallback;
}

/** 语义色变量（可含 `var()` 包裹）→ 具体色值；读不到时回退中性灰 */
export function resolveCssVar(varName: string): string {
  const name = varName.replace(/var\(|\)/g, "").trim();
  return getCssVar(name, "#8E8B82");
}

/** 语义色变量 + 透明度 → `rgba()`，用于图标底衬等浅色填充 */
export function getColorWithAlpha(colorVar: string, alpha: number): string {
  const hex = resolveCssVar(colorVar);
  if (!/^#[0-9a-fA-F]{3,8}$/.test(hex)) return `rgba(0,0,0,${alpha})`;
  let r = 0,
    g = 0,
    b = 0;
  if (hex.length === 4) {
    r = parseInt(hex[1] + hex[1], 16);
    g = parseInt(hex[2] + hex[2], 16);
    b = parseInt(hex[3] + hex[3], 16);
  } else {
    r = parseInt(hex.slice(1, 3), 16);
    g = parseInt(hex.slice(3, 5), 16);
    b = parseInt(hex.slice(5, 7), 16);
  }
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/**
 * 大类 key → 中文标签。
 *
 * 存量数据可能仍带历史细分大类（如 `bank_wealth`），回退到标签表避免显示英文键。
 */
export function getCategoryLabel(key: string): string {
  const cat = INVENTORY_CATEGORIES.find(c => c.key === key);
  return cat ? cat.label : majorCategoryLabel(key);
}

/** 投资理财明细的细分标签：优先 `minor_category`，存量数据回退到历史大类标签 */
export function getMinorAssetLabel(row: AssetRecord): string {
  if (row.minor_category) {
    const hit = INVESTMENT_MINOR_CATEGORIES.find(
      i => i.value === row.minor_category
    );
    if (hit) return hit.label;
  }
  return majorCategoryLabel(row.major_category);
}

/** 配置目标 key → 语义色变量（桑基图配色，与分布图保持一致） */
const ALLOCATION_COLOR_MAP: Record<string, string> = {
  liquid: "var(--sankey-liquid)",
  stable: "var(--sankey-stable)",
  longterm: "var(--sankey-longterm)",
  speculative: "var(--sankey-speculative)",
  security: "var(--sankey-security)"
};

/** 配置目标 key → 中文标签（未配置 / 未知 key 原样兜底） */
export function getAllocationLabel(key: string | null): string {
  if (!key) return "未配置";
  const opt = ALLOCATION_OPTIONS.find(item => item.value === key);
  return opt ? opt.label : key;
}

/** 配置目标 key → 前景色 */
export function getAllocationColor(key: string | null): string {
  return ALLOCATION_COLOR_MAP[key || ""] || "var(--text-primary)";
}

/** 配置目标 key → 胶囊底色（前景色降透明度） */
export function getAllocationBgColor(key: string | null): string {
  return getColorWithAlpha(getAllocationColor(key), 0.15);
}

/** 后端 `type` 分组 → 页面分组 key（股票 / 可转债 合并为证券，基金归基金，其余忽略） */
const GROUP_KEY_MAP: Record<string, string> = {
  股票: "securities",
  可转债: "securities",
  基金: "fund"
};

const GROUP_META_MAP: Record<
  string,
  { label: string; icon: string; color: string }
> = {
  securities: {
    label: "股票",
    icon: "ep:trend-charts",
    color: "var(--invest-stock)"
  },
  fund: { label: "基金", icon: "ep:money", color: "var(--invest-fund)" }
};

/**
 * 投资分布：消费后端 `GET /api/summary/groups/?dimension=type`（含 count / 总市值），
 * 按原页面语义合并「股票 + 可转债 → 证券」「基金 → 场外基金」。
 */
export function buildInvestmentGroups(raw: AssetGroupRaw[]): InvestmentGroup[] {
  const groups: Record<string, { total: number; count: number }> = {};
  for (const g of raw) {
    const key = GROUP_KEY_MAP[g.name];
    if (!key) continue;
    if (!groups[key]) groups[key] = { total: 0, count: 0 };
    groups[key].total += g.total || 0;
    groups[key].count += g.count || 0;
  }

  return Object.entries(groups).map(([type, data]) => {
    const meta = GROUP_META_MAP[type];
    return {
      type,
      label: meta?.label || type,
      icon: meta?.icon || "ep:question",
      color: meta?.color || "var(--color-neutral)",
      ...data
    };
  });
}
