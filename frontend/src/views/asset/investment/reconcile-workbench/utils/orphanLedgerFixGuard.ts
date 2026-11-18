/**
 * 缺账本流水「逐条确认归属后回填」弹窗的提交准入（#2875）。
 *
 * 与 #2866 悬空引用准入的区别，也是本文件存在的理由：域 F 的归属由**用户选目标持仓**
 * 决定，风险靠「影响预览」告知；域 G 的归属由后端按 account_name 精确同名唯一判定，
 * 前端**没有任何可选项**，所以闸门落在两件别的事上：
 *
 *   1. **逐条归属预览必须真的看过**：后端给的是每组一个 resolved_ledger，但用户要看的是
 *      「这 26 笔分别会挂到哪个账本」。没展开过明细就提交，等于让系统替用户确认了一批
 *      他没看过的写操作；
 *   2. **二次确认必须勾选**：回填会改 transactions.ledger_id（可撤销，但仍是一次写库）。
 *
 * 另外有一条硬闸门：整组若含任何 ``block_reason``（组级或逐条），一律不许提交。
 * 后端 ``backfill_orphan_ledgers`` 会逐条重新解析并整体拒绝，前端不该把注定 400 的
 * 请求发出去，也不该把「无法归属」伪装成「可以试试」。
 *
 * 抽成纯函数：这段判据最容易被「顺手去掉一个条件」改坏，而单测跑在 node 环境、
 * 不渲染 el-dialog；断言落在**具体原因文案**上，不只数按钮的 disabled 属性。
 */

/** 准入只关心「有没有 blocked 行」，不读具体流水字段（与 API 类型解耦） */
export interface BackfillGroupLike {
  block_reason: string | null;
  transactions: Array<{ block_reason: string | null }>;
}

export interface OrphanLedgerSubmitInput {
  group: BackfillGroupLike | null;
  /** 用户是否已展开看过逐条归属明细 */
  previewSeen: boolean;
  /** 用户是否勾选「我已核对，确认只回填账本」 */
  confirmed: boolean;
  submitting: boolean;
}

export type OrphanLedgerBlockReason =
  | "未选择待回填分组"
  | "该组没有可回填的流水"
  | "该组含无法唯一归属的流水，不能回填"
  | "正在提交回填"
  | "请先展开查看逐条归属"
  | "请勾选确认后再回填"
  | null;

/** 返回禁止提交的原因；返回 null 才允许提交。顺序即优先级：先挡住「根本不能写」。 */
export function submitBlockReason(
  input: OrphanLedgerSubmitInput
): OrphanLedgerBlockReason {
  if (!input.group) return "未选择待回填分组";
  // 空组：后端 _normalize_ids 会拒绝空 transaction_ids，前端不该发出注定 400
  // 的请求（否则界面表现为「点了没反应」，比禁用更难懂）。
  if (input.group.transactions.length === 0) {
    return "该组没有可回填的流水";
  }
  // 组级 / 逐条两级都要查：组级原因是「概括说明」，逐条原因才是真相
  if (
    input.group.block_reason !== null ||
    input.group.transactions.some(t => t.block_reason !== null)
  ) {
    return "该组含无法唯一归属的流水，不能回填";
  }
  if (input.submitting) return "正在提交回填";
  if (!input.previewSeen) return "请先展开查看逐条归属";
  if (!input.confirmed) return "请勾选确认后再回填";
  return null;
}

export function canSubmitOrphanBackfill(
  input: OrphanLedgerSubmitInput
): boolean {
  return submitBlockReason(input) === null;
}
