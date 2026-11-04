/**
 * 交易状态（`success` / `failed` / `cancelled` / `pending`）的展示口径唯一真源（#2712）。
 *
 * WHY 单独成文件：状态标签原先只长在 `views/asset/transactionList/transactionListModel.ts`，
 * 而**共享表格组件** `components/TransactionTable` 一旦要显示状态列，就只能反过来 import
 * 某个页面的 model —— 共享组件依赖页面模块是方向反的，于是各页各写一张映射表，
 * 状态的中文与配色又开始漂（「修一处漏一处」正是本次统一要挡的）。
 *
 * 为什么放 `utils/` 而不是 `constants/`：这里是「值 → 展示」的映射函数，与
 * `constants` 里那批静态常量表（`TXN_TYPE_LABELS` 等）同类，但需要 el-tag 的语义类型；
 * 独立文件可让「状态」这一组口径就近收口，也便于单测直接覆盖。
 */

export type TxnStatusTag =
  "primary" | "success" | "warning" | "info" | "danger";

/** 状态 → 中文标签。未知状态原样返回，不吞成「未知」——露出原值才好排查数据。 */
export const TXN_STATUS_LABELS: Record<string, string> = {
  success: "成功",
  failed: "失败",
  cancelled: "已撤单",
  pending: "可撤单"
};

export function txnStatusLabel(status: string | null | undefined): string {
  if (!status) return "--";
  return TXN_STATUS_LABELS[status] ?? status;
}

/** 状态 → el-tag 语义色：成功绿、失败红、其余中性 */
export function txnStatusTag(status: string | null | undefined): TxnStatusTag {
  const map: Record<string, TxnStatusTag> = {
    success: "success",
    failed: "danger",
    cancelled: "info",
    pending: "warning"
  };
  return (status && map[status]) || "primary";
}
