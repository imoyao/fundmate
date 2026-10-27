/**
 * 导入结果页的两条显隐规则（自 ResultStep.vue 抽出，纯函数）。
 *
 * 这两条规则决定「用户看到的导入结论」——
 * ① `hasAnomalies` 决定副文案是「全部数据校验通过」还是「N 笔跳过（重复 M 条）· 异常 K 条」，
 * ② `hasSupplements` 决定整块补充信息卡片是否出现。
 * 它们此前以 computed 内联在 .vue 里，只能靠跑完一整套导入流程才能验证；
 * 抽成纯函数后由 `__tests__/importResultModel.spec.ts` 直接钉住边界（尤其是
 * 「`keptBlockedCount` 只影响 ①、`keptCount` 只影响 ②」这种容易记反的口径）。
 *
 * ⚠️ 口径来源（勿凭直觉改）：
 * - ① 里放的是「被跳过的异常」：skipped / duplicate / error / orphan / keptBlocked
 *   （keptBlocked 是「勾选保留但被去重规则拦下」= 实际没入库，属异常侧）；
 * - ② 里放的是「需要额外解释的信息」：cashTransfers / kept / keptBlocked / orphan /
 *   importErrors / showPriceUpdateTip（kept 是「按勾选真的入库了」，不需要告警但需要说明）。
 * - `duplicate` / `error` 不进 ②：它们的明细已经由 ImportErrorSummary 展开，重复展示无益。
 */

/** 结果页需要的全部计数与开关（由 useImportWizard 的 ctx 逐项喂入） */
export interface ImportResultState {
  /** 跳过笔数 */
  skipped: number;
  /** 疑似重复条数 */
  duplicate: number;
  /** 异常条数 */
  error: number;
  /** 孤儿交易（缺对应持仓）笔数 */
  orphan: number;
  /** 勾选保留后真的入库的疑似重复笔数（#1882） */
  kept: number;
  /** 勾选保留但被去重规则拦截的笔数（#1882） */
  keptBlocked: number;
  /** 银证转账同步生成的现金侧记录数（#1010） */
  cashTransfers: number;
  /** 是否存在导入错误明细（决定要不要渲染 ImportErrorSummary） */
  hasImportErrors: boolean;
  /** 是否展示「持仓市价已自动更新」提示 */
  showPriceUpdateTip: boolean;
}

/** 是否有跳过/异常记录（决定副文案走「干净」分支还是明细分支） */
export function hasAnomalies(s: ImportResultState): boolean {
  return (
    s.skipped > 0 ||
    s.duplicate > 0 ||
    s.error > 0 ||
    s.orphan > 0 ||
    s.keptBlocked > 0
  );
}

/** 是否有补充信息区块（转账 / 保留 / 孤儿 / 错误 / 价格提示任一存在） */
export function hasSupplements(s: ImportResultState): boolean {
  return (
    s.cashTransfers > 0 ||
    s.kept > 0 ||
    s.keptBlocked > 0 ||
    s.orphan > 0 ||
    s.hasImportErrors ||
    s.showPriceUpdateTip
  );
}
