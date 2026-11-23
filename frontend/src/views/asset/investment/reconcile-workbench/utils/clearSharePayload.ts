/**
 * 「份额与流水不自洽」面板的一键清仓载荷与文案（纯函数，无 Vue 依赖，可单测）。
 *
 * ## 为什么单独一个文件
 *
 * 这个动作改写持仓（quantity=0 + 锚点归零），不可逆。判据写进模板或组件里
 * 不会有测试咬住——一旦有人把 kind 改成 increment、或把 quantity 改成派生值，
 * 表现就是「点了清仓、份额没归零 / 反而被补录污染」。判据必须单一来源且被测试锁死。
 *
 * ## 为什么是 set 0 而不是 recompute / increment
 *
 * - recompute（按流水重算）：后端 `assert_recompute_keeps_position` 对净额 ≤ 0 的
 *   持仓硬拦——本面板命中的正是净额 ≤ 0 的那批，走它必然 400；
 * - increment（补录）：同时写流水与持仓，差额两端同步移动，差额恒定（#3134）；
 * - set + quantity=0：唯一合法的清仓入口，后端 `_clear_position_by_bill`
 *   （reconciliation_decision.py）行保留 + 锚点重置当日 0 份，净值回填不会复活。
 *
 * 清仓是**人的结论**（账单确认已没有这只），所以按钮要二次确认，
 * 且文案必须交代「流水没记全就别点」——净额 ≤ 0 也可能是漏了买入腿（#39 那种）。
 */

import type { AdjustmentPayload } from "@/api/reconciliation";
import type { ShareIntegrityItem } from "@/api/reconciliation";

/** 构造「按账单清仓」请求：只写持仓，不建流水。 */
export function buildClearSharePayload(
  item: ShareIntegrityItem
): AdjustmentPayload {
  return {
    kind: "set",
    quantity: 0,
    // 定位要清的持仓：symbol 是后端硬校验（set 必填），ledger_id 用于区分同名标的在不同账户
    symbol: item.symbol,
    ledger_id: item.ledger_id,
    reason: `按账单确认已清仓（份额与流水不自洽面板）：账上 ${item.quantity_now} 份，流水净额 ${item.flow_net} 份`
  };
}

/** 二次确认文案：把「为什么可能是漏记而非清仓」摆在最前，避免误点。 */
export function clearShareConfirmText(item: ShareIntegrityItem): string {
  const cause =
    item.flow_state === "oversold"
      ? "这只卖出的比买入还多，多半是漏记了买入——先去交易记录补上，别急着清仓。"
      : "这只买卖已经轧平，账上却还剩份额，可能确实已清仓，也可能流水没记全。";
  return (
    `${cause}\n\n` +
    `账上 ${item.quantity_now} 份 / 按流水 ${item.quantity_if_recomputed} 份 / 差 ${item.diff} 份。\n` +
    `只有券商账单确认已经没有这只了才继续：会把份额改成 0 并写当日锚点（保留持仓行，之后不会复活）。` +
    `这一步可从调整记录撤销。`
  );
}

/** 成功后提示：点明「面板会自动消失」，让用户知道状态已更新。 */
export function clearShareResultText(): string {
  return "已按账单清仓（份额改成 0），份额自洽提示已更新";
}
