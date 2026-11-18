/**
 * 买入「金额 / 份额 / 净值（价格） / 手续费」换算的唯一实现。
 *
 * ## 为什么单独成文件
 *
 * 这组换算是买入口径的**唯一事实**（净额 = 金额 − 手续费；份额 = 净额 ÷ 净值），
 * 但它此前只住在 `components/QuickEntry/composables/useBuySharesLinkage.ts` 的
 * watch 回调里，对账工作台的补录弹窗拿不到 —— 于是补录只能让人手填「成交数量 +
 * 成交价格」，同样是基金买入，记一笔按金额、补录按份额，两个入口口径不一致
 * （owner 2026-11-15 指出）。
 *
 * 抽成纯函数后：两个入口共用同一份算术，且能被 vitest 直接咬住（不必渲染组件）。
 *
 * 精度口径沿用既有实现：份额 4 位（基金份额的最小精度），金额 2 位（分）。
 */

/** 金额（含手续费）→ 份额：先按手续费净扣，再除净值 */
export function sharesFromAmount(
  amount: number | undefined,
  price: number | undefined,
  fee: number | undefined
): number | undefined {
  if (!isNumber(amount) || amount <= 0) return undefined;
  if (!isNumber(price) || price <= 0) return undefined;
  const net = amount - (fee || 0);
  // 手续费吃掉全部金额 ⇒ 没有份额，不能返回 0 或负数（那会写成「买入 0 份」）
  if (net <= 0) return undefined;
  return round(net / price, 4);
}

/** 份额 → 金额（含手续费）：份额 × 净值 + 手续费 */
export function amountFromShares(
  shares: number | undefined,
  price: number | undefined,
  fee: number | undefined
): number | undefined {
  if (!isNumber(shares) || shares <= 0) return undefined;
  if (!isNumber(price) || price <= 0) return undefined;
  return round(shares * price + (fee || 0), 2);
}

function isNumber(value: number | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** 四舍五入到指定小数位（`toFixed` 后再 parseFloat，与既有联动实现逐位一致） */
function round(value: number, digits: number): number {
  return parseFloat(value.toFixed(digits));
}
