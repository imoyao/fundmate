/**
 * 编辑交易弹窗的口径（#980 拆分时抽出）。
 *
 * 三处「看起来是 UI、实际是业务口径」的东西收在这里：
 * - **金额为权威**：基金按「金额 → 份额」反算，股票按「数量 × 单价 + 手续费」正算；
 *   两边都保留 4 / 2 位小数的 `Math.round` 而不是 `toFixed`（后者返回字符串，会污染数字输入框）；
 * - **资产类型的四级兜底**（外部传入 → asset_type → type → security_type → position_type）；
 * - **份额与该不该被反算覆盖**：靠调用方的 `sharesTouched` 标志，这里只负责算。
 */
import type { LedgerTransactionUpdateInput } from "@/api/ledger";

/** 编辑弹窗的表单模型 */
export interface TransactionEditForm {
  quantity: number | null;
  price: number | null;
  amount: number | null;
  fee: number | null;
  trade_date: string | null;
  confirm_date: string | null;
  notes: string;
}

/** 基金类（含货币基金）按份额（小数）处理；其余按股 / 张（整数） */
export const FUND_ASSET_TYPES = ["fund", "money_fund"];

/** 证券类：卖出价区间校验与日期联动只对这几类生效 */
export const STOCK_ASSET_TYPES = ["stock", "etf", "bond", "convertible"];

/**
 * 资产类型：优先用外部传入，否则从交易记录里逐字段兜底。
 *
 * 四级兜底不是洁癖——同一条流水在三个入口（账户详情 / 持仓流水抽屉 / 流水列表）
 * 拿到的对象字段并不一致：有的带 `asset_type`，有的只有 `type`。
 */
export function resolveAssetType(record: any, override?: string): string {
  return (
    override ||
    record?.asset_type ||
    record?.type ||
    record?.security_type ||
    record?.position_type ||
    ""
  );
}

export function isFundAssetType(assetType: string): boolean {
  return FUND_ASSET_TYPES.includes(assetType);
}

export function isStockAssetType(assetType: string): boolean {
  return STOCK_ASSET_TYPES.includes(assetType);
}

/** 份额 / 数量的步进与精度：基金 4 位小数，股票 1 股 */
export function quantityMeta(assetType: string): {
  precision: number;
  step: number;
} {
  return isFundAssetType(assetType)
    ? { precision: 4, step: 0.0001 }
    : { precision: 0, step: 1 };
}

/**
 * 基金：由金额反算份额 `(amount - fee) / nav`，保留 4 位小数。
 *
 * 条件不满足返回 `null`（调用方不写回），而不是返回 0——写 0 会把用户刚填的份额清掉。
 */
export function recalcShares(
  amount: number | null | undefined,
  price: number | null | undefined,
  fee: number | null | undefined
): number | null {
  if (
    amount == null ||
    price == null ||
    Number(price) <= 0 ||
    Number(amount) < 0
  )
    return null;
  return (
    Math.round(((Number(amount) - Number(fee || 0)) / Number(price)) * 10000) /
    10000
  );
}

/**
 * 股票 / 可转债：由数量正算金额 `qty * price + fee`，保留 2 位小数。
 *
 * 同样返回 `null` 表示「不该写回」。
 */
export function recalcAmount(
  quantity: number | null | undefined,
  price: number | null | undefined,
  fee: number | null | undefined
): number | null {
  if (
    quantity == null ||
    price == null ||
    Number(quantity) < 0 ||
    Number(price) < 0
  )
    return null;
  return (
    Math.round((Number(quantity) * Number(price) + Number(fee || 0)) * 100) /
    100
  );
}

/** 打开弹窗时的表单快照（与交易记录逐字段对齐） */
export function formSnapshotOf(record: any): TransactionEditForm {
  const t = record || {};
  return {
    quantity: t.quantity ?? null,
    price: t.price ?? null,
    amount: t.amount ?? null,
    fee: t.fee ?? null,
    trade_date: t.trade_date || null,
    confirm_date: t.confirm_date || null,
    notes: t.notes ?? ""
  };
}

/** 关闭弹窗后的空表单（基线要一起清，否则 `isDirty` 恒为 true） */
export function blankForm(): TransactionEditForm {
  return {
    quantity: null,
    price: null,
    amount: null,
    fee: null,
    trade_date: null,
    confirm_date: null,
    notes: ""
  };
}

/** 保存请求体：只提交可编辑的 7 个字段，空日期转 null */
export function buildUpdatePayload(
  form: TransactionEditForm
): LedgerTransactionUpdateInput {
  return {
    quantity: form.quantity,
    price: form.price,
    amount: form.amount,
    fee: form.fee,
    trade_date: form.trade_date || null,
    confirm_date: form.confirm_date || null,
    notes: form.notes
  } as LedgerTransactionUpdateInput;
}
