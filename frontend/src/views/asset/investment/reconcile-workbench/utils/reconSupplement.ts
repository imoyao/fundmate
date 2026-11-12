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
  if (!row || row.discrepancy_type !== "quantity") return null;
  const { expected_value: expected, actual_value: actual, diff } = row;
  const delta =
    typeof diff === "number"
      ? diff
      : typeof expected === "number" && typeof actual === "number"
        ? actual - expected
        : null;
  if (delta === null || delta === 0) return null;
  return delta < 0 ? "sell" : "buy";
}
