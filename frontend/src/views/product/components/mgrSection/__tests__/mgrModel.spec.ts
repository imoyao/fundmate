import { describe, expect, it } from "vitest";
import type { ManagerProfileResult } from "@/api/products";
import {
  bestReturnClass,
  fundsTruncated,
  hasTenureData,
  styleTierClass,
  tenureCaption,
  tenureSpan
} from "../mgrModel";

const profile = (over: Partial<ManagerProfileResult> = {}) =>
  ({ funds: [], fund_count: 0, ...over }) as unknown as ManagerProfileResult;

describe("bestReturnClass：涨跌色由前端按符号决定", () => {
  it("缺失不涂色（不是「跌」）", () => {
    expect(bestReturnClass(null)).toBe("");
    expect(bestReturnClass(undefined)).toBe("");
  });

  it("0 归为涨：不涨不跌不涂绿", () => {
    expect(bestReturnClass(0)).toBe("is-rise");
  });

  it("正负分档", () => {
    expect(bestReturnClass(12.5)).toBe("is-rise");
    expect(bestReturnClass(-0.01)).toBe("is-fall");
  });
});

describe("tenureCaption：口径必须写出来", () => {
  it("没有任期数据时不给副文案（不凭空解释）", () => {
    expect(tenureCaption(null)).toBeUndefined();
    expect(tenureCaption(undefined)).toBeUndefined();
  });

  it("按数据来源分两种口径", () => {
    expect(tenureCaption({ basis: "em_days_derived" })).toBe("自首次任职起算");
    expect(tenureCaption({ basis: "start_date" })).toBe("按任职起始日推算");
    expect(tenureCaption({})).toBe("按任职起始日推算");
  });
});

describe("styleTierClass：强度阶梯不是评价", () => {
  it("metric 维度的 low/high 落两端", () => {
    expect(styleTierClass("concentration_low")).toBe("is-low");
    expect(styleTierClass("concentration_high")).toBe("is-high");
  });

  it("size 维度的 small/large 复用同一阶梯", () => {
    expect(styleTierClass("cap_size_small")).toBe("is-low");
    expect(styleTierClass("cap_size_large")).toBe("is-high");
  });

  it("未知后缀与前向兼容：落中性档，不报错", () => {
    expect(styleTierClass("turnover_balanced")).toBe("is-mid");
    expect(styleTierClass("weird")).toBe("is-mid");
    expect(styleTierClass("")).toBe("is-mid");
  });

  it("只看最后一段后缀：中间带 low 不影响", () => {
    expect(styleTierClass("low_turnover_high")).toBe("is-high");
  });
});

describe("hasTenureData", () => {
  it("四个信号位任一有值即算有数据", () => {
    expect(hasTenureData(profile({ appointment_date: "2015-01-01" }))).toBe(
      true
    );
    expect(hasTenureData(profile({ tenure_display: {} as never }))).toBe(true);
    expect(hasTenureData(profile({ sum_scale: 0 }))).toBe(true);
    expect(
      hasTenureData(
        profile({
          funds: [{ fund_code: "X", start_date: "2020-01-01" }] as never
        })
      )
    ).toBe(true);
  });

  it("全空返回 false（于是会渲染「尚未同步」说明）", () => {
    expect(hasTenureData(profile())).toBe(false);
    expect(hasTenureData(null)).toBe(false);
  });
});

describe("fundsTruncated", () => {
  it("总数大于已返回数才算被截断", () => {
    expect(
      fundsTruncated(profile({ fund_count: 42, funds: new Array(20) as never }))
    ).toBe(true);
    expect(
      fundsTruncated(profile({ fund_count: 3, funds: new Array(3) as never }))
    ).toBe(false);
  });

  it("没有档案时不提示截断", () => {
    expect(fundsTruncated(null)).toBe(false);
  });
});

describe("tenureSpan", () => {
  it("精度到月，在任写「至今」", () => {
    expect(tenureSpan("2020-03-01", null)).toBe("2020-03 ~ 至今");
    expect(tenureSpan("2020-03-01", "2021-07-15")).toBe("2020-03 ~ 2021-07");
  });

  it("没有起始日整段不渲染（不显示「— ~ —」）", () => {
    expect(tenureSpan(null, "2021-07-15")).toBeUndefined();
    expect(tenureSpan(undefined, undefined)).toBeUndefined();
    expect(tenureSpan("", null)).toBeUndefined();
  });
});
