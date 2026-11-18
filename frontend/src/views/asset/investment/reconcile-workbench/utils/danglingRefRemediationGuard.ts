/**
 * 「数据缺失」分组「补全信息 / 删除」弹窗的提交准入（#2866 后续）。
 *
 * 与 danglingRefFixGuard 同一条硬规矩：**没看过影响预览，就不许写**。
 * 补全额外要求：这组确实有可补字段（否则整组代码日期已齐，动作不成立）、
 * 至少填一个字段、预览对应的输入未变（防拿 A 输入的预览去提交
 * B 输入）、二次勾选确认；删除额外要求：输入「删除」二字（后端也会硬校验，
 * 这里只是不把明显不合格的请求发出去）。
 *
 * 抽成纯函数、单测跑在 node 环境、不渲染 el-dialog，也不 import 完整 API 类型：
 * 准入只关心预览的最小形状，API 定义落盘前单测即可独立运行。
 */

/** 补全预览的最小形状：准入只关心「预览是否已返回」与预览时的输入签名。 */
export interface EnrichPreviewLike {
  symbol: string | null;
  trade_date: string | null;
}

/** 删除预览的最小形状：准入只关心「预览是否已返回」。 */
export interface DeletePreviewLike {
  txn_count: number;
}

export interface EnrichGuardInput {
  preview: EnrichPreviewLike | null;
  hasField: boolean;
  /**
   * 这组是否**还有**可补的字段（`inspectGroupNeeds().complete` 的反面）。
   * 组内代码与日期全齐时，补全动作在语义上不成立——不是「用户没填」，
   * 所以这条判据必须排在 `hasField` 之前，否则会把原因说成
   * 「请至少填写标的代码或交易日期」，让用户以为是自己漏填了。
   */
  needsFill: boolean;
  fieldSignature: string;
  confirmed: boolean;
  previewing: boolean;
  submitting: boolean;
  txnCount: number;
}

export interface DeleteGuardInput {
  preview: DeletePreviewLike | null;
  confirmPhrase: string;
  previewing: boolean;
  submitting: boolean;
  txnCount: number;
}

export type EnrichBlockReason =
  | "该组没有可处理的交易"
  | "这组没有可补的字段"
  | "请至少填写标的代码或交易日期"
  | "正在查看影响"
  | "正在提交"
  | "请先查看影响"
  | "输入已变化，请重新查看影响"
  | "请先勾选二次确认"
  | null;

export type DeleteBlockReason =
  | "该组没有可处理的交易"
  | "正在查看影响"
  | "正在提交"
  | "请先查看影响"
  | "请输入「删除」二字确认"
  | null;

/** 输入签名：当前输入与预览输入共用同一拼法，才能比对出「输入已变化」。 */
export function buildFieldSignature(
  symbol: string | null | undefined,
  tradeDate: string | null | undefined
): string {
  return `${symbol ?? ""}|${tradeDate ?? ""}`;
}

/** 返回禁止提交的原因；返回 null 才允许提交。顺序即优先级：先挡住「还没看清」。 */
export function enrichBlockReason(input: EnrichGuardInput): EnrichBlockReason {
  if (input.txnCount === 0) return "该组没有可处理的交易";
  if (!input.needsFill) return "这组没有可补的字段";
  if (!input.hasField) return "请至少填写标的代码或交易日期";
  if (input.previewing) return "正在查看影响";
  if (input.submitting) return "正在提交";
  if (!input.preview) return "请先查看影响";
  if (
    buildFieldSignature(input.preview.symbol, input.preview.trade_date) !==
    input.fieldSignature
  )
    return "输入已变化，请重新查看影响";
  if (!input.confirmed) return "请先勾选二次确认";
  return null;
}

export function deleteBlockReason(input: DeleteGuardInput): DeleteBlockReason {
  if (input.txnCount === 0) return "该组没有可处理的交易";
  if (input.previewing) return "正在查看影响";
  if (input.submitting) return "正在提交";
  if (!input.preview) return "请先查看影响";
  if (input.confirmPhrase !== "删除") return "请输入「删除」二字确认";
  return null;
}

export function canSubmitEnrich(input: EnrichGuardInput): boolean {
  return enrichBlockReason(input) === null;
}

export function canSubmitDelete(input: DeleteGuardInput): boolean {
  return deleteBlockReason(input) === null;
}
