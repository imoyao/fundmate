/**
 * 对账中心纯格式化函数（#980 拆分自 index.vue 的 utils/ 步骤，零行为变更）
 *
 * 与页面结构无关的纯函数：差异类型 / 状态中文映射、差异值格式与着色类名。
 */

import { discrepancyTypeLabel } from "@/constants";

/** 差异类型中文（映射表已收归 `@/constants`，此处保留导出以兼容既有调用方） */
export function typeLabel(t: string): string {
  return discrepancyTypeLabel(t);
}

/** 状态中文 */
export function statusLabel(s: string): string {
  const map: Record<string, string> = {
    pending: "待处理",
    cleared: "已清除",
    ignored: "已忽略"
  };
  return map[s] || s;
}

/** 差异值格式：份额（已由后端 Money.min_unit_to_shares 转换） */
export function formatDiff(diff: number | null): string {
  if (diff === null) return "—";
  if (diff === 0) return "0";
  return Number.isInteger(diff)
    ? String(diff)
    : diff.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
}

export function diffClass(diff: number | null): string {
  if (!diff) return "disc-diff-zero";
  return diff > 0 ? "disc-diff-pos" : "disc-diff-neg";
}
