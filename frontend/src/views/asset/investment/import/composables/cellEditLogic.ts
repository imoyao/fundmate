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
