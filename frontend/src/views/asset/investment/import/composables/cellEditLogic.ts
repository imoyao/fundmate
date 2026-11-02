/**
 * 行内就地编辑的纯逻辑（#1790，规范 #783 §6.2）。
 *
 * 与 batchFixLogic 同理从 useImportWizard 抽出：这些分支直接决定
 * 「改一处、金额跟着变」的对账语义，错了会静默产生错账，必须可单测钉住。
 */

/**
 * 编辑字段自身为 NaN 时从另两项互推（原 useImportWizard.smartFill，#1792 前既有）。
 * 只补「缺的那个」，不重算金额——金额方向由 recalcAfterEdit 负责。
 */
export function smartFill(row: any, field: string): void {
  const qty = parseFloat(row.quantity),
    prc = parseFloat(row.price),
    amt = parseFloat(row.amount);
  if (field === "quantity" && isNaN(qty) && !isNaN(prc) && !isNaN(amt)) {
    row.quantity = parseFloat((amt / prc).toFixed(4));
    row.smartFilled = true;
  } else if (field === "price" && isNaN(prc) && !isNaN(qty) && !isNaN(amt)) {
    row.price = parseFloat((amt / qty).toFixed(4));
    row.smartFilled = true;
  }
}

/**
 * 提交后的金额自动计算（#783 §6.2，#1790 要做的事 5）：
 * - 改数量/单价 → 金额 = 数量 × 单价（两者均有效时才算；否则维持原状，缺项交给 smartFill）；
 * - 改金额 → 有数量则反算单价（#1790「改金额→反算单价」）；数量缺失但单价在则反推数量；
 *   两者均缺失则不计算（§6.2 明文）。
 *
 * 精度对齐既有口径：金额 2 位、数量单价 4 位，避免浮点尾巴进入分类比较
 * （|数量×单价−金额| > 0.01 即判不符，见 categorizeRow）。
 * 注意：重算后的金额与数量×单价恒等，故本函数只可能消解「不符」、不会制造新不符。
 */
export function recalcAfterEdit(row: any, field: string): void {
  const qty = parseFloat(row.quantity),
    prc = parseFloat(row.price),
    amt = parseFloat(row.amount);
  if (field === "quantity" || field === "price") {
    if (!isNaN(qty) && qty > 0 && !isNaN(prc) && prc > 0)
      row.amount = parseFloat((qty * prc).toFixed(2));
    return;
  }
  if (field !== "amount" || isNaN(amt)) return;
  if (!isNaN(qty) && qty > 0) row.price = parseFloat((amt / qty).toFixed(4));
  else if (!isNaN(prc) && prc > 0)
    row.quantity = parseFloat((amt / prc).toFixed(4));
}

/** #2137 费用拆分四键（元），顺序与后端 `_FEE_BREAKDOWN_KEYS` 一致 */
const FEE_BREAKDOWN_KEYS = [
  "fee_commission",
  "fee_stamp_duty",
  "fee_transfer_fee",
  "fee_other"
] as const;

/**
 * 手改手续费总额后处置拆分列（#2137 不变量前置，2026-11-02）。
 *
 * WHY 必须在提交时清、而不是留给后端兜：`Transaction.before_insert`
 * 要求「四列之和 == fee」，只改总额不改四列 → 写入抛 ValueError → 整批导入
 * 失败，而前端只会看到「导入失败」，根因（拆分对不上）完全不可见。
 *
 * 语义：用户手改总额 = 以总额为准、放弃明细，故四列置空（全 NULL = 未拆分，
 * 事件放行）。返回是否**真的清掉了数字明细**，供调用方决定要不要提示。
 *
 * `''` 与 `null` 的口径差：后端 `_fee_breakdown_kwargs` 把两者同等视为「未提供」，
 * 但 `''` 与数字**混合**时会走另一分支抛 ValueError。故清理动作必须把 `''` 一并
 * 归零，而提示只在真有数字明细时弹——全空行弹「已清除明细」是假告警。
 */
export function clearFeeBreakdownOnEdit(row: any, field: string): boolean {
  if (field !== "fee") return false;
  const present = FEE_BREAKDOWN_KEYS.some(
    k => row[k] !== null && row[k] !== undefined
  );
  if (!present) return false;
  const hadNumbers = FEE_BREAKDOWN_KEYS.some(
    k => row[k] !== null && row[k] !== undefined && row[k] !== ""
  );
  FEE_BREAKDOWN_KEYS.forEach(k => {
    row[k] = null;
  });
  return hadNumbers;
}

/**
 * 金额列 cell-missing 判定（getCellClassName 用）。
 * 该高亮原挂手续费列，列收敛退场（#1790）后改挂金额列——金额是三个可编辑列之一，
 * 缺失时给左色条提示比挂在一个已删列上更有用。
 */
export function isMissingAmount(row: any): boolean {
  return (
    row.amount === null ||
    row.amount === undefined ||
    isNaN(parseFloat(row.amount))
  );
}
