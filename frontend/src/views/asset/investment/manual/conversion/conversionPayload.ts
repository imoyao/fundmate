// frontend/src/views/asset/investment/manual/conversion/conversionPayload.ts
// 转换试算 / 提交的请求体组装（#980 拆分自 ConversionForm.vue）。
//
// 为什么抽出来：原实现里「试算」与「提交」各自手写了一遍同一份 8 字段请求体
// （`runEstimate` 与 `submit`），两份写法必须永远一致，否则会出现「试算说 0 元费用、
// 提交带上人工修正」这种对不上的情况。这里收成一份 `buildConversionBaseParams`，
// 提交只在其上追加 `refund_mode` / `idempotency_key`。
//
// 字段口径（照抄接口注释，不要在这里重新解释）：
// - `out_quantity` 为 `null` = 全部转出，由后端按持仓 **4 位精确值**清算、不抹零；
// - `in_amount` / `in_quantity` 二选一，只发当前口径那一个；
// - `fee_override` 为 `null` = 按费率表算，非 null = 用户在确认页改过。

import type {
  ConversionBaseParams,
  ConversionSubmitParams
} from "@/api/positions";
import type { ConversionFormModel } from "./conversionFormModel";

/**
 * 组装请求体需要的「非 form 状态」。
 *
 * 刻意不并进 `ConversionFormModel`：这三项都不是用户填的字段
 * （账户来自父页、`transferAll` 由档位点击派生、`feeOverride` 由确认页产生），
 * 混进 form 会让 `resetForm` 的边界变模糊。
 */
export interface ConversionPayloadCtx {
  /** 账户 ID；父页当前选中的账本 */
  ledgerId: number | null;
  /** 「全部」转出：不传 out_quantity，后端按持仓 4 位精确值处理（D8/§5.2） */
  transferAll: boolean;
  /** 人工修正后的费用；未修正传 null */
  feeOverride: { redeem: number; compensate: number } | null;
}

/** 试算 / 提交共用的 8 个基础字段 */
export function buildConversionBaseParams(
  form: ConversionFormModel,
  ctx: ConversionPayloadCtx
): ConversionBaseParams {
  return {
    ledger_id: ctx.ledgerId,
    out_position_id: form.positionId as number,
    // 全部转出 ⇒ null（后端取精确值）；否则发用户填的份额
    out_quantity: ctx.transferAll ? null : (form.quantity ?? null),
    in_symbol: form.inSymbol,
    // 金额 / 份额二选一：只发当前口径的那个，后端对同时传两者直接拒绝
    in_amount: form.inMode === "amount" ? (form.inAmount ?? null) : null,
    in_quantity: form.inMode === "quantity" ? (form.inQuantity ?? null) : null,
    fee_override: ctx.feeOverride,
    trade_date: form.trade_date
  };
}

/** 提交在基础字段上追加「差额去向」与幂等键 */
export function buildConversionSubmitParams(
  form: ConversionFormModel,
  ctx: ConversionPayloadCtx,
  idempotencyKey: string
): ConversionSubmitParams {
  return {
    ...buildConversionBaseParams(form, ctx),
    refund_mode: form.refundMode || null,
    idempotency_key: idempotencyKey
  };
}
