/**
 * 补录弹窗的纯判据（无 Vue 依赖，可单测）。
 *
 * 与 `reconDisplay.ts` 的分工：那边是「后端字段 → 用户语言」（展示），
 * 这里是「差异方向 → 补录时该预填哪个交易类型」（写路径的默认值）。
 * 之所以单独成一个文件：方向搞反会静默写成反向交易（账上多一笔卖出），
 * 这是必须能被测试咬住的判断，不能只在 `.vue` 的模板/脚本里 `v-if` 一行算完。
 */

import type { DiscrepancyItem } from "@/api/reconciliation";

export type SupplementOpType = "buy" | "sell";

/**
 * 按差异方向推断补录该填「买入」还是「卖出」。
 *
 * 口径（后端 `backend/app/services/reconciliation_service.py:171-198`）：
 * - `expected_value` = 按流水算的份额（`theoretical_qty`）
 * - `actual_value`   = 账上记的份额（`pos.quantity`）
 * - `diff`           = `actual - expected`
 *
 * ⇒ `diff < 0`（流水比账上多）＝少记了一笔**卖出** → `sell`；
 *   `diff > 0`（流水比账上少）＝少记了一笔**买入** → `buy`；
 *   `diff === 0` / 缺值 → 不预填，交回表单默认值。
 *
 * ## 为什么必须排除 `orphan`
 *
 * `orphan` 的 `actual_value` 恒为 0（该业务键根本没有持仓行），
 * `diff` 必然为负 —— 按符号规则会算成「卖出」，但真实情况是
 * 「持仓行没了、流水是对的」，那件事由「按流水重建持仓」处理
 * （#3066）。按符号硬推会让用户去补一笔根本不存在的卖出。
 * `cost` 差异与买卖方向无关，同样不参与。
 *
 * `diff` 缺失时按两个值现算（同后端 `:198` 的算式），两个值都缺才放弃——
 * 缺一个就预填一个方向，等于替用户猜。
 */
export function inferSupplementOpType(
  row: DiscrepancyItem | null
): SupplementOpType | null {
  const delta = deltaOf(row);
  if (delta === null || delta === 0) return null;
  return delta < 0 ? "sell" : "buy";
}

/**
 * 按差异预填的成交数量：差额的绝对值。
 *
 * 语义是「补上差的那一笔，差异就消失」——比让用户自己算 `|账上 − 流水|` 少一次
 * 口算出错的机会（owner 2026-11-12 拍板「数量可以预填」）。
 *
 * 它和「卖出全仓」是两个不同的默认值，**不要合并**：
 * - 这里 = 差额（补完两边相等）；
 * - 「卖出全仓」= 按流水算的份额（补完整条持仓归零，清仓语义）。
 * 两者都保留，用户按实际成交选一个，也可以直接手改。
 *
 * 与方向预填同一道闸：只对 `quantity` 型生效（`orphan` / `cost` 返回 `null`），
 * 差额为 0 或缺值时不预填——预填 0 会让「成交数量 0」看起来像个已填好的值。
 */
export function inferSupplementQuantity(
  row: DiscrepancyItem | null
): number | null {
  const delta = deltaOf(row);
  if (delta === null || delta === 0) return null;
  return Math.abs(delta);
}

/**
 * 差异量（`actual - expected`，即后端 `diff` 的口径）。
 *
 * 只对 `quantity` 型返回数值：`orphan` 的 `actual_value` 恒为 0、`diff` 必负，
 * 直接拿来预填就会引导用户补一笔不存在的卖出（那类问题归「按流水重建持仓」，
 * #3066）；`cost` 差异与成交方向、数量都无关。`diff` 缺失时按两值现算，
 * 两个值都缺才放弃——缺一个就预填，等于替用户猜。
 */
function deltaOf(row: DiscrepancyItem | null): number | null {
  if (!row || row.discrepancy_type !== "quantity") return null;
  const { expected_value: expected, actual_value: actual, diff } = row;
  if (typeof diff === "number") return diff;
  if (typeof expected === "number" && typeof actual === "number") {
    return actual - expected;
  }
  return null;
}
