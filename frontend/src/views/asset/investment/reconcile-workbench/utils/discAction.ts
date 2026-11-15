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
 *
 * ## 为什么 `quantity` 不能再走「补录」
 *
 * `quantity` 差异的定义是「持仓份额 − 按流水算出的份额」。补录（increment）走买卖汇点，
 * **同时**写流水与持仓，两端同步移动 ⇒ 差额恒等于补录前的值（#3134 真库实测：补了一笔
 * 卖出 3000，持仓 4000→1000、流水 3000→0，差额仍是 1000 份）。能改变差额的只有改持仓
 * 这一侧：有流水可依时按流水重算（`recompute`），流水本身不可信时由用户照账单填（`set`）。
 */

import type { DiscrepancyItem } from "@/api/reconciliation";

/** 差异类型 → 唯一可用动作 */
export type DiscAction = "supplement" | "anchor" | "recompute" | "set";

/** 判据需要的字段（`expected_value` 只在 `quantity` 上用得到） */
type DiscActionRow = Pick<DiscrepancyItem, "discrepancy_type"> & {
  expected_value?: number | null;
};

/**
 * 按差异类型选动作。
 *
 * - `no_anchor` → `anchor`：缺基准，写当前值为基准；
 * - `quantity` 且理论份额 ≥ 0 → `recompute`：按流水重算份额，差额会真的变；
 * - `quantity` 且理论份额 < 0 → `set`：卖出多于买入（买入腿缺失），照流水重算会把它
 *   清零，而清仓是 #3127 明确「不敢批量做」的动作 ⇒ 交给用户照账单填；
 * - 其余（cost / cash / orphan）→ `supplement`：补一笔缺失的流水才有意义。
 */
export function discActionOf(row: DiscActionRow): DiscAction {
  if (row.discrepancy_type === "no_anchor") return "anchor";
  if (row.discrepancy_type === "quantity") {
    return typeof row.expected_value === "number" && row.expected_value < 0
      ? "set"
      : "recompute";
  }
  return "supplement";
}

/**
 * 动作 → 上抛的事件名。
 *
 * 判据与事件同源：两个宿主（差异表 / 抽屉单条执行区）都调这里，不再各写一份
 * 「什么动作发什么事件」——那种 switch 一旦分叉，表现就是「按钮说重算、实际开补录弹窗」。
 */
export function discActionEvent(
  action: DiscAction
): "supplement" | "recompute" {
  return action === "recompute" ? "recompute" : "supplement";
}

/**
 * 补录弹窗打开时默认选中的模式。
 *
 * 与 `discActionOf` 同源：`no_anchor` → 「以此为准」、`quantity` 超卖 → 「改成这个持仓」
 * （set），其余 → 「补一笔交易」。这行判据若在弹窗里另写一遍
 * （`discrepancy_type === "no_anchor"`），两处迟早分叉——表现是「按钮说以此为准，
 * 弹窗默认补一笔」，用户照着填就编出一笔不存在的交易。
 */
export function defaultSupplementKind(
  row: DiscActionRow | null | undefined
): "increment" | "anchor" | "set" {
  if (!row) return "increment";
  const action = discActionOf(row);
  if (action === "anchor") return "anchor";
  if (action === "set") return "set";
  return "increment";
}

/** 动作按钮文案（与判据同源，避免「按钮说补录、点了写基准」） */
export const DISC_ACTION_LABELS: Record<DiscAction, string> = {
  supplement: "补录这笔",
  anchor: "以此为准",
  recompute: "按流水重算份额",
  set: "改成账单份额"
};

/** 按钮下方的解释（一句话说清「点了会改哪一侧」，避免用户以为三个按钮是同一件事） */
export const DISC_ACTION_HINTS: Record<DiscAction, string> = {
  supplement: "补一笔漏记的买卖，会同时记流水并重算持仓",
  anchor: "把当前份额固定为基准，之后只核对新流水",
  recompute: "按已有流水改持仓份额，差额会跟着变",
  set: "按券商账单上的份额改持仓，不走流水"
};
