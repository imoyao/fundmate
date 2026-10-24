/**
 * 账户卡片的展示口径（#980 拆分时抽出）。
 *
 * 全是「模板里一个三元表达式」级别的小判断，但每一条都有产品含义，且都容易在
 * 搬动时写错方向（激活 ↔ 归档、第几位 ↔ 下标、`undefined` vs `0`）：
 *
 * - 三类账户的「右侧第二个指标」不同（银行看活期余额、实物看估值项数、其余看持仓盈亏）；
 * - 归档是**取反**表达（`is_active === false` 才叫已归档），按钮文案与 aria-label 都要跟着翻；
 * - 键盘重排的下标是 0 起，而屏幕阅读器念的是「第几位」（1 起）。
 */

export type PnlMetricKind = "cash" | "count" | "pnl";

export function isArchived(ledger: any): boolean {
  return ledger?.is_active === false;
}

/** 只有落到库里的账户（id 是数字）才有归档 / 删除按钮 */
export function hasRowActions(ledger: any): boolean {
  return typeof ledger?.id === "number";
}

/** 持仓滞后角标：`staleCount` 缺省按 0（父页面可能不传） */
export function showStaleBadge(staleCount?: number): boolean {
  return (staleCount ?? 0) > 0;
}

/** 关联负债只在「银行账户且有房贷」时出现 */
export function hasLinkedLiability(ledger: any): boolean {
  return ledger?.ledger_type === "bank" && ledger?.linked_liability > 0;
}

/** 右侧第二个指标的标题：银行 → 活期余额；实物 → 估值；其余 → 持仓盈亏 */
export function pnlLabelOf(ledgerType?: string): string {
  if (ledgerType === "bank") return "活期余额";
  if (ledgerType === "property") return "估值";
  return "持仓盈亏";
}

/**
 * 右侧第二个指标该渲染哪一种。
 *
 * 顺序即语义：银行的活期余额**可能为空**（`null` / `undefined` 表示未取到），
 * 此时要退回「持仓盈亏」而不是显示 `¥0.00`——把「没数据」显示成 0 会让用户
 * 以为账户余额真被清空了。
 */
export function pnlMetricKindOf(ledger: any): PnlMetricKind {
  const type = ledger?.ledger_type;
  const cash = ledger?.cash_balance;
  if (type === "bank" && cash !== undefined && cash !== null) return "cash";
  if (type === "property") return "count";
  return "pnl";
}

/** 归档 / 激活按钮的文案与 aria-label（两者必须同向，别一个翻一个不翻） */
export function archiveToggleLabel(archived: boolean): string {
  return archived ? "激活" : "归档";
}

export function archiveAriaLabel(name: string, archived: boolean): string {
  return (archived ? "激活账户 " : "归档账户 ") + name;
}

export function deleteAriaLabel(name: string): string {
  return `删除账户 ${name}`;
}

/** 拖拽抓手的 aria-label：念出「第几位 / 共几位」与操作方式（#1841） */
export function dragAriaLabel(
  name: string,
  index?: number,
  total?: number
): string {
  return `调整顺序：${name}，当前第 ${(index ?? 0) + 1} / ${total ?? 1} 位，用上下方向键移动`;
}

export function dragTitle(name: string): string {
  return `拖拽或用方向键调整顺序：${name}`;
}

export type ReorderKey = "up" | "down" | "home" | "end";

/**
 * 键盘重排的目标下标（#1841）：↑/↓ 移一位，Home/End 到首尾。
 *
 * 返回的是**下标**而不是「第几位」——落库接口按数组下标交换。
 * 边界（首位再按 ↑、末位再按 ↓）不在这里夹紧：交给页面层的 `reorderLedgers`
 * 判「越界即忽略」，因为它才知道分组边界（跨组不该复用本组的下标）。
 */
export function reorderTargetOf(
  key: ReorderKey,
  index?: number,
  total?: number
): number {
  const from = index ?? 0;
  if (key === "up") return from - 1;
  if (key === "down") return from + 1;
  if (key === "home") return 0;
  return (total ?? 1) - 1;
}
