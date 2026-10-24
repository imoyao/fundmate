/**
 * 幂等命中（409）回执拼装单测（#980 拆分 ConversionForm.vue 时新增）。
 *
 * 这段代码原先藏在 `submit` 的 catch 分支里，40 行字面量、没人测过。
 * 它是**唯一一条「后端不给完整回执」的路径**：用户重复点击或网络重发时，
 * 后端返回 409 + 已有组号，页面必须靠「本次表单 + 上一次试算」把结果页补齐。
 * 补错的后果不是报错，而是展示一张**数字不对的回执**：
 * - 没有组号却渲染回执 → 页面出现「申请单号 --」但状态是「已提交」；
 * - 试算缺失时金额补成 0 → 用户以为这笔转出金额是 0；
 * - `refund.mode` 把空串写成 "" → 结果页「已回到」后面空着。
 */
import { describe, it, expect } from "vitest";
import type {
  ConversionEstimateResult,
  ConversionSubmitResult
} from "@/api/positions";
import type { Position } from "@/api/types";
import { buildDuplicateConversionResult } from "../conversionDuplicateResult";
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
    inName: "易方达中小盘",
    refundMode: "money_fund",
    ...overrides
  };
}

const POSITION: Position = {
  id: 11,
  ledger_id: 1,
  symbol: "000001",
  name: "华夏成长",
  type: "fund",
  quantity: 1234.5678,
  currency: "CNY"
} as Position;

const ESTIMATE: ConversionEstimateResult = {
  out: {
    symbol: "000001",
    name: "华夏成长",
    quantity: 500,
    nav: 2.1,
    amount: 1050,
    fee: 5.25,
    fee_breakdown: { redeem: 5.25, compensate: 0 },
    fee_estimated: { redeem: 5.25, compensate: 0 },
    realized_pnl_estimate: 12.5
  },
  in: {
    symbol: "110011",
    name: "易方达中小盘",
    nav: 3.5,
    amount: 1044.75,
    quantity: 298.5
  },
  net_amount: 1044.75,
  refund: {
    amount: 0,
    options: [{ type: "money_fund", symbol: "000198", name: "余额宝" }]
  },
  supplement: { amount: 0, required: false },
  trade_date: "2026-10-24",
  warnings: []
};

describe("buildDuplicateConversionResult 组号", () => {
  it("有 link_group_id：组号同时作为回执单号", () => {
    const r = buildDuplicateConversionResult({
      dup: { link_group_id: "grp-1" },
      form: mkForm(),
      estimate: ESTIMATE,
      position: POSITION
    });
    expect(r?.link_group_id).toBe("grp-1");
    expect(r?.group_no).toBe("grp-1");
    expect(r?.status).toBe("pending");
    expect(r?.confirm_date).toBe("");
  });

  it("没有组号：返回 null（没有回执可展示，不能靠拼装硬凑一张）", () => {
    expect(
      buildDuplicateConversionResult({
        dup: null,
        form: mkForm(),
        estimate: ESTIMATE,
        position: POSITION
      })
    ).toBeNull();
    expect(
      buildDuplicateConversionResult({
        dup: { link_group_id: "" },
        form: mkForm(),
        estimate: ESTIMATE,
        position: POSITION
      })
    ).toBeNull();
  });
});

describe("buildDuplicateConversionResult 数字来源", () => {
  it("有试算：out / in / refund 全部沿用试算结果", () => {
    const r = buildDuplicateConversionResult({
      dup: { link_group_id: "grp-1" },
      form: mkForm(),
      estimate: ESTIMATE,
      position: POSITION
    }) as ConversionSubmitResult;
    expect(r.out).toEqual(ESTIMATE.out);
    expect(r.in).toEqual({ ...ESTIMATE.in, position_id: null });
    expect(r.refund).toEqual({
      amount: 0,
      mode: "money_fund",
      txn_id: null
    });
    expect(r.warnings).toEqual([]);
  });

  it("没试算：用手填值兜底，金额类补 0（不是 NaN / undefined）", () => {
    const r = buildDuplicateConversionResult({
      dup: { link_group_id: "grp-1" },
      form: mkForm(),
      estimate: null,
      position: POSITION
    }) as ConversionSubmitResult;
    expect(r.out).toEqual({
      symbol: "000001",
      name: "华夏成长",
      quantity: 500,
      nav: 0,
      amount: 0,
      fee: 0,
      fee_breakdown: { redeem: 0, compensate: 0 },
      realized_pnl_estimate: 0
    });
    expect(r.in).toEqual({
      symbol: "110011",
      name: "易方达中小盘",
      nav: 0,
      amount: 0,
      quantity: 0,
      position_id: null
    });
    expect(r.refund.amount).toBe(0);
  });

  it("没试算也没持仓：转出代码留空串而不是 undefined", () => {
    const r = buildDuplicateConversionResult({
      dup: { link_group_id: "grp-1" },
      form: mkForm({ quantity: undefined }),
      estimate: null,
      position: null
    }) as ConversionSubmitResult;
    expect(r.out.symbol).toBe("");
    expect(r.out.name).toBeNull();
    expect(r.out.quantity).toBe(0);
  });

  it("refund.mode 空串 → null（结果页据此判断「未选」）", () => {
    const r = buildDuplicateConversionResult({
      dup: { link_group_id: "grp-1" },
      form: mkForm({ refundMode: "" }),
      estimate: ESTIMATE,
      position: POSITION
    }) as ConversionSubmitResult;
    expect(r.refund.mode).toBeNull();
  });

  it("交易日取表单值（后端 409 不回传交易日）", () => {
    const r = buildDuplicateConversionResult({
      dup: { link_group_id: "grp-1" },
      form: mkForm({ trade_date: "2026-09-30" }),
      estimate: null,
      position: POSITION
    }) as ConversionSubmitResult;
    expect(r.trade_date).toBe("2026-09-30");
  });
});
