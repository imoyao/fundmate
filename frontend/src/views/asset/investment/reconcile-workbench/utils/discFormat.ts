/**
 * 对账工作台纯格式化函数（#980 拆分自 index.vue 的 utils/ 步骤，零行为变更）
 *
 * 与页面结构无关的纯函数：差异类型 / 状态中文映射、差异值格式与着色类名。
 */

/** 差异类型中文 */
export function typeLabel(t: string): string {
  const map: Record<string, string> = {
    quantity: "数量",
    cost: "成本",
    cash: "资金",
    orphan: "孤儿"
  };
  return map[t] || t;
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

/** E账户记录状态中文（四态） */
export function eStatusLabel(s: string): string {
  const map: Record<string, string> = {
    pending: "待处理",
    attributed: "已归因",
    ignored: "已忽略",
    verified: "已核对"
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
