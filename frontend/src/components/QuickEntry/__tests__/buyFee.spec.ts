/**
 * 买入手续费换算单测（#980 拆分时新增）。
 *
 * 这段逻辑原先埋在 BuyForm 的三个函数里（applyFeePreset / onFeeModeChange /
 * onFundFeeDiscountChange），判据只有「跑一遍看数字对不对」。抽成纯函数后钉住两件事：
 *
 * 1. **单位随模式变**：金额模式存元、费率模式存百分比。换算方向错一次，用户看到的
 *    手续费会差 100 倍。
 * 2. **算不出来就不要假装算过**：金额为 0 / 手续费为 0 时返回 undefined（清空输入），
 *    而不是写 0 —— 留 0 会让用户以为系统已经算好了。
 */
import { describe, it, expect } from "vitest";
import {
  convertFeeValue,
  feeFromDiscount,
  parseFeeConfig
} from "../composables/useBuyFee";

describe("convertFeeValue（金额 ⇄ 费率）", () => {
  it("切到费率模式：元 → 百分比", () => {
    expect(convertFeeValue("rate", 10, 1000)).toBe(1);
  });

  it("切到金额模式：百分比 → 元", () => {
    expect(convertFeeValue("amount", 1, 1000)).toBe(10);
  });

  it("金额为 0（还没填金额）时不换算，返回 undefined", () => {
    expect(convertFeeValue("rate", 10, 0)).toBeUndefined();
  });

  it("手续费为 0 时返回 undefined，而不是 0", () => {
    expect(convertFeeValue("amount", 0, 1000)).toBeUndefined();
  });

  it("保留 4 位小数（费率）/ 2 位小数（金额）", () => {
    expect(convertFeeValue("rate", 1, 300)).toBe(0.3333);
    expect(convertFeeValue("amount", 0.3333, 300)).toBe(1);
  });
});

describe("feeFromDiscount（快捷折扣档位）", () => {
  it("费率模式返回百分比：申购费 1.5% × 1折 = 0.15", () => {
    expect(
      feeFromDiscount({
        subscriptionRate: 0.015,
        discount: 0.1,
        amount: 1000,
        mode: "rate"
      })
    ).toBe(0.15);
  });

  it("金额模式返回元：1000 × 1.5% × 1折 = 1.5", () => {
    expect(
      feeFromDiscount({
        subscriptionRate: 0.015,
        discount: 0.1,
        amount: 1000,
        mode: "amount"
      })
    ).toBe(1.5);
  });

  it("免申购费（折扣 0）两种模式都归零", () => {
    expect(
      feeFromDiscount({
        subscriptionRate: 0.015,
        discount: 0,
        amount: 1000,
        mode: "amount"
      })
    ).toBe(0);
    expect(
      feeFromDiscount({
        subscriptionRate: 0.015,
        discount: 0,
        amount: 1000,
        mode: "rate"
      })
    ).toBe(0);
  });
});

describe("parseFeeConfig", () => {
  it("null / 空串视为没有配置", () => {
    expect(parseFeeConfig(null)).toBeNull();
    expect(parseFeeConfig("")).toBeNull();
  });

  it("JSON 字符串解析成对象（老数据按字符串存）", () => {
    expect(parseFeeConfig('{"commission":{"rate":0.0003,"min":5}}')).toEqual({
      commission: { rate: 0.0003, min: 5 }
    });
  });

  it("非法 JSON 不抛错，返回 null", () => {
    expect(parseFeeConfig("{not-json")).toBeNull();
  });

  it("已经是对象时原样返回", () => {
    const cfg = { subscription_discount: 0.1 };
    expect(parseFeeConfig(cfg)).toBe(cfg);
  });
});
