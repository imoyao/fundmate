/**
 * 行状态标签的唯一判据（#2836）。
 *
 * ## 为什么要把这件事从组件里抽出来
 *
 * 原先这段是 `StatusCell.vue` 模板里的一串 `v-else-if`。它有一个不易察觉的缺口：
 * 「金额对不上」（`isAmountMismatch`）没有对应分支，于是这类行一路落到末尾的
 * `v-else`，拿到一枚**绿色「正常」**。同一行在别处却有完全不同的说法：
 *
 * - 概览条：`categorizeRow` 把 `isAmountMismatch` 归进 `fix` → 「需要修正 +1」
 * - 修正面板：`fixSectionRows.mismatch` 分区里躺着它
 * - 底栏：「另有 M 条暂不导入」却不含它（因为它默认可勾、默认可导入）
 *
 * 一个分支缺失就让「错账」显示成「正常」，而模板里的 `v-else` 天然吞噬任何
 * 遗漏的分支——漏一个判据不会有任何报错，只会静默降级成最乐观的那个标签。
 *
 * 抽成纯函数后，这个不变式可以被测试直接钉住：
 * **凡是 `categorizeRow` 判为 `fix` 的行，状态标签绝不能是 `ok`。**
 * 新增 fix 判定却忘了配套状态标签时，该测试立刻转红。
 *
 * ## 顺序即语义
 *
 * 从上到下第一条命中即返回。顺序刻意与「用户该先看到什么」一致：
 * 被配对消费（不用管它）→ 配对疑问 → 重复 → 解析错误 → 缺字段（要动手）
 * → 金额对不上 → 差额等于手续费（不用管，可导入）→ 推算值（看一眼）→ 正常。
 */

export type StatusKind =
  | "consumed"
  | "linkWarning"
  | "duplicate"
  | "error"
  | "missingCode"
  | "blocked"
  | "mismatch"
  | "feeExplained"
  | "calculated"
  | "ok";

/** StatusCell 需要的谓词；由 `useImportWizard()` 提供，测试可注入桩 */
export interface StatusPredicates {
  isRowBlocked(row: any): boolean;
  isFeeExplained(row: any): boolean;
  isAmountMismatch(row: any): boolean;
  isMissingCode(row: any): boolean;
}

/**
 * 判定一行的状态标签种类。
 *
 * 注意 `mismatch` 与 `feeExplained` 在数学上互斥（差额要么在手续费能解释的
 * 范围内、要么超出），但这里仍显式按「超出」优先——语义上「对不上」比
 * 「含手续费」重要，将来若有人放宽互斥关系，顺序也不会把严重度说反。
 *
 * 分支顺序与 `categorizeRow` 的 fix 分区顺序对齐（error → missingCode →
 * blocked → mismatch），保证「概览条说是哪一类」与「状态列写的是哪一类」一致。
 */
export function statusKindOf(row: any, p: StatusPredicates): StatusKind {
  if (!row) return "ok";
  if (row.consumed_by) return "consumed";
  if (row.link_warning) return "linkWarning";
  if (row.is_duplicate) return "duplicate";
  if (row.error) return "error";
  if (p.isMissingCode(row)) return "missingCode";
  if (p.isRowBlocked(row)) return "blocked";
  if (p.isAmountMismatch(row)) return "mismatch";
  if (p.isFeeExplained(row)) return "feeExplained";
  if (row.is_calculated) return "calculated";
  return "ok";
}
