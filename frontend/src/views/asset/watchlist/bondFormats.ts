/**
 * 可转债条款列的**格式化纯函数**（#1400 / #2575）。
 *
 * ## 为什么独立成模块
 *
 * vitest 环境是 node（无 DOM），而 `columnRenderers.tsx` 为了画单元格会 import
 * `MoneyDisplay` 等 `.vue` 组件，那条依赖链最终会初始化 router / supabase
 * （实测一路要求 `VITE_SUPABASE_URL` → `VITE_ROUTER_HISTORY`）。故按本目录既有
 * 约定（见 `__tests__/linksRenderer.spec.ts` 的说明）把可测的整形逻辑留在纯模块，
 * 渲染器只做接线。
 *
 * ## 钉死的关键判据：**0 是真实值，不是缺值**
 *
 * 正股 PB 可能是 0（正股净资产恰好为市值的 0 倍，极罕见但合法），YTM 可能是
 * 0.00%（正好打平）。若把 `0` 当缺值处理，用户会看到 `—` 而不是真实数字；
 * 反过来若把 `null` 当 0，用户会看到「收益率为零」——那是**编造**。故：
 *
 * - `null` / `undefined` → `—`（缺值）
 * - `0` → 照常格式化（真实值）
 */

/** 缺值占位符（全仓统一，不用 0 兜底）。 */
export const BOND_EMPTY_TEXT = "—";

function isMissing(v: number | null | undefined): boolean {
  return v == null || Number.isNaN(v);
}

/**
 * 通用数字格式化：两位小数 + 缺值占位。
 *
 * @param v 数值；`null` / `undefined` / `NaN` 视为缺值
 * @param suffix 可选后缀（如 `%`）
 */
export function bondNumberText(
  v: number | null | undefined,
  suffix = ""
): string {
  if (isMissing(v)) return BOND_EMPTY_TEXT;
  return `${(v as number).toFixed(2)}${suffix}`;
}

/**
 * YTM 的涨跌配色类（A 股惯例：涨红跌绿）。
 *
 * 0 归为「跌色」侧不合适（持平不是跌），故 `0` 用中性色（不挂涨跌类）。
 */
export function bondYtmClass(v: number | null | undefined): string {
  if (isMissing(v) || (v as number) === 0) return "";
  return (v as number) > 0 ? "is-ytm-up" : "is-ytm-down";
}
