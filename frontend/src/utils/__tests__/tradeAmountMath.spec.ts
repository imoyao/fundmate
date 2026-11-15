/**
 * 买入金额 / 份额 / 净值 / 手续费的换算口径（记一笔与对账补录共用同一份算术）。
 *
 * 用真实形态的数字正反各验一次：任何一侧被改错，另一侧立刻露馅。
 * - 场外基金：买入 1000 元、确认净值 1.5 ⇒ 666.6667 份
 * - 打新中签：500 股 @7.35 ⇒ 3675 元
 */
import { describe, expect, it } from "vitest";
import { amountFromShares, sharesFromAmount } from "../tradeAmountMath";

describe("sharesFromAmount", () => {
  it("金额 ÷ 净值，份额保留 4 位（1000 ÷ 1.5 = 666.6667）", () => {
    expect(sharesFromAmount(1000, 1.5, 0)).toBe(666.6667);
  });

  it("手续费从金额里净扣后换算（(1000 − 1.5) ÷ 1.5 = 665.6667）", () => {
    expect(sharesFromAmount(1000, 1.5, 1.5)).toBe(665.6667);
  });

  it("净额不为正 / 净值缺失时不换算（绝不返回 0 或负数份额）", () => {
    expect(sharesFromAmount(0, 1.5, 0)).toBeUndefined();
    expect(sharesFromAmount(1000, 0, 0)).toBeUndefined();
    expect(sharesFromAmount(undefined, 1.5, 0)).toBeUndefined();
    expect(sharesFromAmount(1000, undefined, 0)).toBeUndefined();
  });
});

describe("amountFromShares", () => {
  it("份额 × 净值 + 手续费，金额保留 2 位（500 × 7.35 = 3675）", () => {
    expect(amountFromShares(500, 7.35, 0)).toBe(3675);
  });

  it("手续费加回金额（666.6667 × 1.5 + 1.5 = 1001.5）", () => {
    expect(amountFromShares(666.6667, 1.5, 1.5)).toBe(1001.5);
  });

  it("净值缺失时不换算", () => {
    expect(amountFromShares(500, 0, 0)).toBeUndefined();
    expect(amountFromShares(500, undefined, 0)).toBeUndefined();
  });
});
