/**
 * 转换请求体单测（#980 拆分 ConversionForm.vue 时新增）。
 *
 * 为什么值得单测：拆分前「试算」与「提交」各自手写了一遍这份 8 字段请求体，
 * 一致性全靠人眼比对。这份请求体里有三处**静默错**——错了不会报错，只会算错钱：
 *
 * 1. **全部转出**：`out_quantity` 必须是 `null`（后端按持仓 4 位精确值清算），
 *    传 `undefined`/0 会被当成「0 份」或落回「按份额」，末位零头被抹掉；
 * 2. **金额 / 份额互斥**：后端对同时传 `in_amount` 与 `in_quantity` 直接拒绝，
 *    所以非当前口径必须显式发 `null`，不能省略；
 * 3. **费用修正**：`fee_override` 为 `null` 表示「按费率表算」。若误把 0 值传上去，
 *    后端会当成「用户把费用改成 0」——那是免赎回费的另一种含义，账就不平了。
 *
 * 另外钉住「提交 = 基础字段 + 差额去向 + 幂等键」，防止以后有人只改其中一份。
 */
import { describe, it, expect } from "vitest";
import {
  buildConversionBaseParams,
  buildConversionSubmitParams,
  type ConversionPayloadCtx
} from "../conversionPayload";
import {
  defaultConversionForm,
  type ConversionFormModel
} from "../conversionFormModel";

function mkForm(
  overrides: Partial<ConversionFormModel> = {}
): ConversionFormModel {
  return {
    ...defaultConversionForm(),
    positionId: 11,
    quantity: 500,
    trade_date: "2026-10-24",
    inSymbol: "110011",
    ...overrides
  };
}

const ctx: ConversionPayloadCtx = {
  ledgerId: 1,
  transferAll: false,
  feeOverride: null
};

describe("buildConversionBaseParams 转出份额", () => {
  it("填了份额：原样下发", () => {
    const p = buildConversionBaseParams(mkForm(), ctx);
    expect(p.out_quantity).toBe(500);
  });

  it("全部转出：out_quantity 必须是 null（后端取持仓精确值、不抹零）", () => {
    const p = buildConversionBaseParams(mkForm(), {
      ...ctx,
      transferAll: true
    });
    expect(p.out_quantity).toBeNull();
  });

  it("全部转出时即便 form.quantity 有值也不下发（避免两套语义打架）", () => {
    const p = buildConversionBaseParams(mkForm({ quantity: 500 }), {
      ...ctx,
      transferAll: true
    });
    expect(p.out_quantity).toBeNull();
  });

  it("未填份额：缺省 null（不是 undefined——后端按缺省=全部处理，两者语义不同）", () => {
    const p = buildConversionBaseParams(mkForm({ quantity: undefined }), ctx);
    expect(p.out_quantity).toBeNull();
  });
});

describe("buildConversionBaseParams 转入金额 / 份额互斥", () => {
  it("金额口径：只发 in_amount，in_quantity 显式 null", () => {
    const p = buildConversionBaseParams(
      mkForm({ inMode: "amount", inAmount: 900, inQuantity: 30 }),
      ctx
    );
    expect(p.in_amount).toBe(900);
    expect(p.in_quantity).toBeNull();
  });

  it("份额口径：只发 in_quantity，in_amount 显式 null", () => {
    const p = buildConversionBaseParams(
      mkForm({ inMode: "quantity", inAmount: 900, inQuantity: 30 }),
      ctx
    );
    expect(p.in_amount).toBeNull();
    expect(p.in_quantity).toBe(30);
  });

  it("金额口径留空 = 净额全部转入：in_amount 为 null 而不是 0", () => {
    const p = buildConversionBaseParams(
      mkForm({ inMode: "amount", inAmount: undefined }),
      ctx
    );
    expect(p.in_amount).toBeNull();
  });

  it("两种口径都不发送 0（0 与「留空」后端语义不同）", () => {
    const p = buildConversionBaseParams(
      mkForm({ inMode: "quantity", inQuantity: undefined }),
      ctx
    );
    expect(p.in_amount).toBeNull();
    expect(p.in_quantity).toBeNull();
  });
});

describe("buildConversionBaseParams 费用与账户", () => {
  it("未修正费用：fee_override 为 null（按费率表算）", () => {
    const p = buildConversionBaseParams(mkForm(), ctx);
    expect(p.fee_override).toBeNull();
  });

  it("修正过费用：原样带上两个数（含 0——那是用户显式改成免赎回费）", () => {
    const p = buildConversionBaseParams(mkForm(), {
      ...ctx,
      feeOverride: { redeem: 0, compensate: 1.23 }
    });
    expect(p.fee_override).toEqual({ redeem: 0, compensate: 1.23 });
  });

  it("账本与交易日取自 ctx / form，不由子组件各自决定", () => {
    const p = buildConversionBaseParams(mkForm({ trade_date: "2026-10-20" }), {
      ...ctx,
      ledgerId: 3
    });
    expect(p.ledger_id).toBe(3);
    expect(p.trade_date).toBe("2026-10-20");
    expect(p.out_position_id).toBe(11);
    expect(p.in_symbol).toBe("110011");
  });
});

describe("buildConversionSubmitParams", () => {
  it("= 基础字段 + 差额去向 + 幂等键", () => {
    const form = mkForm({ refundMode: "money_fund" });
    const base = buildConversionBaseParams(form, ctx);
    const sub = buildConversionSubmitParams(form, ctx, "uuid-1");
    expect(sub).toEqual({
      ...base,
      refund_mode: "money_fund",
      idempotency_key: "uuid-1"
    });
  });

  it("差额去向未选：下发 null（空串不是一种去向）", () => {
    const sub = buildConversionSubmitParams(
      mkForm({ refundMode: "" }),
      ctx,
      "k"
    );
    expect(sub.refund_mode).toBeNull();
  });

  it("基础字段与试算完全一致（两份请求体不许漂移）", () => {
    const form = mkForm({ inMode: "quantity", inQuantity: 12.34 });
    const base = buildConversionBaseParams(form, ctx);
    const sub = buildConversionSubmitParams(form, ctx, "k");
    const { refund_mode, idempotency_key, ...rest } = sub;
    expect(rest).toEqual(base);
    // 显式引用，避免 lint 认为解构出的变量未使用
    expect(refund_mode).toBeNull();
    expect(idempotency_key).toBe("k");
  });
});
