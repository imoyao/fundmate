import { describe, expect, it } from "vitest";

import {
  purchaseFeeText,
  redeemFeeLadder,
  redeemFeeText,
  type PurchaseTier,
  type RedeemTier
} from "../fundFeeFormat";

/**
 * 费率文案口径（#1015）。
 *
 * 这里钉的是**两条已经踩过的坑**，而不是格式偏好：
 *
 * 1. 接口不保证阶梯顺序（后端查询无 `ORDER BY`），旧实现取 `rows[0]` 于是「首档」
 *    可能是持有 2 年以上那档的 0%——展示成「赎回费 0.00%」是最危险的一种错；
 * 2. 旧文案拿 `start_day` 当条件（首档为 0）→「1.50%（0 天内）」。区间是半开区间，
 *    条件必须由 `end_day` 推出来（`[0, 7)` = 不足 7 天）。
 */

describe("purchaseFeeText", () => {
  it("单档（无上限）读作「不限金额」", () => {
    const rows: PurchaseTier[] = [
      { start_quota: 0, end_quota: null, rate: 0.015 }
    ];
    expect(purchaseFeeText(rows)).toEqual({
      rate: "1.50%",
      condition: "不限金额",
      tiered: false
    });
  });

  it("多档乱序时取金额下限最小的一档，并标记分档", () => {
    const rows: PurchaseTier[] = [
      { start_quota: 5000000, end_quota: null, rate: 0.001 },
      { start_quota: 0, end_quota: 1000000, rate: 0.015 },
      { start_quota: 1000000, end_quota: 5000000, rate: 0.01 }
    ];
    expect(purchaseFeeText(rows)).toEqual({
      rate: "1.50%",
      condition: "100 万以下",
      tiered: true
    });
  });

  it("中间档用区间、开区间档用「以上」、小额档用元", () => {
    expect(
      purchaseFeeText([
        { start_quota: 1000000, end_quota: 5000000, rate: 0.01 }
      ])?.condition
    ).toBe("100 万–500 万");
    expect(
      purchaseFeeText([{ start_quota: 5000000, end_quota: null, rate: 0.001 }])
        ?.condition
    ).toBe("500 万以上");
    expect(
      purchaseFeeText([{ start_quota: 0, end_quota: 5000, rate: 0.015 }])
        ?.condition
    ).toBe("5000 元以下");
  });

  it("缺失 / 空阶梯返回 null（调用方显示「—」，不编造 0%）", () => {
    expect(purchaseFeeText(null)).toBeNull();
    expect(purchaseFeeText(undefined)).toBeNull();
    expect(purchaseFeeText([])).toBeNull();
  });

  it("固定金额档（1000 元/笔）不读成 0.00%", () => {
    const rows: PurchaseTier[] = [
      { start_quota: 5000000, end_quota: null, rate: 0, fee_amount: 1000 }
    ];
    expect(purchaseFeeText(rows)).toEqual({
      rate: "1000 元/笔",
      condition: "500 万以上",
      tiered: false
    });
  });
});

describe("redeemFeeText", () => {
  it("乱序时取持有天数下限最小的一档（不是 rows[0]）", () => {
    const rows: RedeemTier[] = [
      { start_day: 730, end_day: null, rate: 0 },
      { start_day: 7, end_day: 730, rate: 0.005 },
      { start_day: 0, end_day: 7, rate: 0.015 }
    ];
    expect(redeemFeeText(rows)).toEqual({
      rate: "1.50%",
      condition: "不足 7 天",
      tiered: true
    });
  });

  it("区间是半开区间：上界不含，故 [7, 30) 读作「7–29 天」", () => {
    expect(
      redeemFeeText([{ start_day: 7, end_day: 30, rate: 0.0075 }])?.condition
    ).toBe("7–29 天");
  });

  it("单天档读作「第 N 天」，不写成首尾相同的区间", () => {
    expect(
      redeemFeeText([{ start_day: 7, end_day: 8, rate: 0.0075 }])?.condition
    ).toBe("第 7 天");
  });

  it("开区间档：整年用年、其余用天", () => {
    expect(
      redeemFeeText([{ start_day: 30, end_day: null, rate: 0 }])?.condition
    ).toBe("满 30 天");
    expect(
      redeemFeeText([{ start_day: 365, end_day: null, rate: 0 }])?.condition
    ).toBe("满 1 年");
    expect(
      redeemFeeText([{ start_day: 0, end_day: null, rate: 0 }])?.condition
    ).toBe("不限持有期");
  });

  it("缺失 / 空阶梯返回 null", () => {
    expect(redeemFeeText(null)).toBeNull();
    expect(redeemFeeText([])).toBeNull();
  });
});

describe("redeemFeeLadder", () => {
  it("按持有天数升序展开全部档位", () => {
    const rows: RedeemTier[] = [
      { start_day: 30, end_day: null, rate: 0 },
      { start_day: 0, end_day: 7, rate: 0.015 },
      { start_day: 7, end_day: 30, rate: 0.0075 }
    ];
    expect(redeemFeeLadder(rows).map(t => `${t.condition} ${t.rate}`)).toEqual([
      "不足 7 天 1.50%",
      "7–29 天 0.75%",
      "满 30 天 0.00%"
    ]);
  });

  it("空阶梯返回空数组（折叠区据此不渲染明细表）", () => {
    expect(redeemFeeLadder(null)).toEqual([]);
    expect(redeemFeeLadder([])).toEqual([]);
  });
});
