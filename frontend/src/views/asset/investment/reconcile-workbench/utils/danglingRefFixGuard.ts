/**
 * 悬空引用「二次回补」弹窗的提交准入（#2866）。
 *
 * 这条链只有一条硬规矩：**没看过影响预览，就不许写**。预览没返回、预览进行中、
 * 或正在提交，都要把提交按钮钉死，并把原因说成用户能读懂的一句话
 * （不是「操作不可用」这种空话）。
 *
 * 预览 safe=false 只代表「流水净额与现存份额不自洽 / symbol 不一致」，而挂回只改
 * transactions.position_id、不动份额，所以它**不是**提交闸门，只由预览面板的 warning
 * 让用户知情；据此拦下会让真库里绝大多数分组都修不了（违背「可看到 + 可修复一起上线」）。
 * 抽成纯函数是因为这段判据最容易被「顺手加个 safe 判断」改坏，而单测跑在 node 环境、
 * 不渲染 el-dialog。
 */

/** 预览响应的最小形状；准入只关心「预览是否已返回」，不读 safe 做闸门 */
export interface PreviewLike {
  safe: boolean;
}

export interface ReattachSubmitInput {
  preview: PreviewLike | null;
  targetSelected: boolean;
  previewing: boolean;
  submitting: boolean;
}

export type ReattachBlockReason =
  | "未选择目标持仓"
  | "正在预览影响"
  | "正在提交回补"
  | "请先查看影响预览"
  | null;

/** 返回禁止提交的原因；返回 null 才允许提交。顺序即优先级：先挡住「还没看清」。 */
export function submitBlockReason(
  input: ReattachSubmitInput
): ReattachBlockReason {
  if (!input.targetSelected) return "未选择目标持仓";
  if (input.previewing) return "正在预览影响";
  if (input.submitting) return "正在提交回补";
  // 预览未落地前不许写：不能把「没数据」当成「安全」
  if (!input.preview) return "请先查看影响预览";
  return null;
}

export function canSubmitReattach(input: ReattachSubmitInput): boolean {
  return submitBlockReason(input) === null;
}
