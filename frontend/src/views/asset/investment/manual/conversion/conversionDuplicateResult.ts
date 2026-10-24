// frontend/src/views/asset/investment/manual/conversion/conversionDuplicateResult.ts
// 幂等命中（409）时拼一份「结果页回执」（#980 拆分自 ConversionForm.vue）。
//
// 为什么单独成文件：这段是 `submit` 的 catch 分支里一个 40 行的字面量，
// 混在提交编排里既读不出「它在补什么」，也没法单测。它的语义其实很清楚：
// **409 表示这笔已经落库了，后端不会返回完整回执**，所以要用「本次表单 +
// 上一次试算」把结果页要展示的字段补齐，让用户看到原组号而不是一片空白。

import type {
  ConversionEstimateResult,
  ConversionSubmitResult
} from "@/api/positions";
import type { Position } from "@/api/types";
import type { ConversionFormModel } from "./conversionFormModel";

/** 409 响应体里 `data` 的形状（只取用到的字段，其余不猜） */
export interface ConversionDuplicateBody {
  link_group_id?: string | null;
}

/**
 * 拼幂等命中的结果页数据。
 *
 * @returns 无 `link_group_id` 时返回 `null`——缺组号就没有回执可展示，
 *   调用方据此保持结果为空（原实现的判断就是这个）。
 *
 * 字段退化规则（照抄原实现，勿"优化"）：
 * - `out` 优先用试算结果；没有试算就用手填值兜底，金额类字段补 0；
 * - `in` 同理，且必须补 `position_id: null`（提交结果类型要求该字段，
 *   幂等命中时后端没告诉我们落在哪个持仓）；
 * - `refund.mode` 为空串时下发 `null`（"未选"不是一种去向）。
 */
export function buildDuplicateConversionResult(input: {
  dup: ConversionDuplicateBody | null | undefined;
  form: ConversionFormModel;
  estimate: ConversionEstimateResult | null;
  position: Position | null;
}): ConversionSubmitResult | null {
  const { dup, form, estimate, position } = input;
  const groupId = dup?.link_group_id;
  if (!groupId) return null;

  return {
    link_group_id: groupId,
    group_no: groupId,
    status: "pending",
    trade_date: form.trade_date,
    // 幂等命中走的是拼装结果，确认日未知
    confirm_date: "",
    out: estimate?.out ?? {
      symbol: position?.symbol ?? "",
      name: position?.name ?? null,
      quantity: form.quantity ?? 0,
      nav: 0,
      amount: 0,
      fee: 0,
      fee_breakdown: { redeem: 0, compensate: 0 },
      realized_pnl_estimate: 0
    },
    in: {
      ...(estimate?.in ?? {
        symbol: form.inSymbol,
        name: form.inName || null,
        nav: 0,
        amount: 0,
        quantity: 0
      }),
      position_id: null
    },
    refund: {
      amount: estimate?.refund.amount ?? 0,
      mode: form.refundMode || null,
      txn_id: null
    },
    warnings: []
  };
}
