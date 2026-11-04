/**
 * 组合卡「目标达成」的展示口径（2026-10-30）。
 *
 * 后端 `target_progress = market_value / target_amount * 100`，**不封顶**，且未设目标
 * 金额时为 `null`。前端有两件事必须分开处理，混在一起就是「数字和条各说各话」：
 *
 * 1. **数字不封顶**：达成 144% 就要说 144%，压成 100% 等于抹掉「超额」这个事实；
 * 2. **进度条封顶 100%**：条是「满没满」的视觉，超出的部分由数字承载。
 *
 * 另外两个边界：原始值是浮点（如 88.63），直接贴会带一串小数，按整数百分比展示；
 * `null` 不是 0（「没设目标」≠「达成 0%」），由调用方整块不渲染，这里只返回空串兜底。
 */

/** 达成率文案：整数百分比；无值返回空串（调用方应整块不渲染） */
export function formatTargetProgress(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "";
  return `${Math.round(value)}%`;
}

/** 进度条宽度：封顶 100%，负值 / 无值按 0（异常数据不撑出条外） */
export function targetFillWidth(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value) || value <= 0) return "0%";
  return `${Math.min(value, 100)}%`;
}
