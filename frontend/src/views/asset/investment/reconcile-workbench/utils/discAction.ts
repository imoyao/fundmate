/**
 * 「这条差异该点哪个按钮」的判据（纯函数，无 Vue 依赖，可单测）。
 *
 * ## 为什么它必须是一个有测试的函数
 *
 * 按钮与类型绑错不会报错，只会让人点了没用：
 * - `no_anchor` 的成因是「没有快照基准」，`expected_value` 是重新按全量流水算出来的
 *   数，与持仓本就不该互校。给它「补录这笔」等于让用户编造一笔不存在的交易去凑数；
 * - 反过来，把 `quantity` 引导到「以此为准」更糟：那是**有**基准的真差异，直接承认
 *   现状会把真错的数据固化成基准，从此再也对不出来。
 *
 * 所以两个方向的错都有代价，判据只能有一处、且必须被测试咬住
 * （模板里写 `v-if="row.discrepancy_type === 'no_anchor'"` 同样容易，但红了没人知道）。
 */

import type { DiscrepancyItem } from "@/api/reconciliation";

/** 差异类型 → 唯一可用动作 */
export type DiscAction = "supplement" | "anchor";

/**
 * 按差异类型选动作。
 *
 * 只有 `no_anchor` 走「以此为准」；其余（quantity / cost / cash / orphan）保持
 * 「补录这笔」—— 它们要么是真差异、要么由别的域接管（orphan 被域 F 覆盖时整行
 * 已被 `withoutRebuildOnly` 剔除，见 `utils/rebuildOnly.ts`）。
 */
export function discActionOf(
  row: Pick<DiscrepancyItem, "discrepancy_type">
): DiscAction {
  return row.discrepancy_type === "no_anchor" ? "anchor" : "supplement";
}

/**
 * 补录弹窗打开时默认选中的模式。
 *
 * 与 `discActionOf` 同源：`no_anchor` 差异进来就直接是「以此为准」，否则是「补一笔交易」。
 * 这行判据若在弹窗里另写一遍（`discrepancy_type === "no_anchor"`），两处迟早分叉——
 * 表现是「按钮说以此为准，弹窗默认补一笔」，用户照着填就编出一笔不存在的交易。
 */
export function defaultSupplementKind(
  row: Pick<DiscrepancyItem, "discrepancy_type"> | null | undefined
): "increment" | "anchor" {
  return row && discActionOf(row) === "anchor" ? "anchor" : "increment";
}

/** 动作按钮文案（与判据同源，避免「按钮说补录、点了写基准」） */
export const DISC_ACTION_LABELS: Record<DiscAction, string> = {
  supplement: "补录这笔",
  anchor: "以此为准"
};
