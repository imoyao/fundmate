/**
 * 价格展示精度契约单测（用户实测反馈：基金详情页净值应为 4 位）。
 *
 * 这个契约的难点从来不是「位数定几」，而是**出口太多、每个出口都能自己写一遍**：
 * 位数契约 `pricePrecision` 早就在，表格类组件也确实用了，但走势图 y 轴压根没
 * 接（echarts 默认只给 1 位，净值 4.8124 在轴上显示成 4.8）、持仓「单位成本」
 * 写死 4 位（股票也跟着 4 位）、tooltip 又写死自己的一份。
 *
 * 所以这里钉的是**契约行为本身**，让「新增出口」可以无脑调它而不必知道位数：
 * - 分档（谁 4 位谁 2 位）；
 * - 非有限值统一占位（不渲染 "NaN" / "null"）；
 * - 轴标签格式化器与 `formatPrice` **同源**（两者各说一套正是本卡的成因）。
 *
 * 至于「有没有新出口绕过契约」，那是 `scripts/guard_price_precision.mjs` 的活
 * —— 单测钉行为，守卫钉接线，缺一个契约就会再次漂移。
 */
import { describe, it, expect } from "vitest";
import {
  PRICE_PLACEHOLDER,
  formatPrice,
  priceAxisLabelFormatter,
  pricePrecision
} from "@/utils/pricePrecision";

describe("pricePrecision：按资产类型分档", () => {
  it("基金 / ETF / 货币基金 = 4 位（最新价是净值）", () => {
    expect(pricePrecision("fund")).toBe(4);
    expect(pricePrecision("etf")).toBe(4);
    expect(pricePrecision("money_fund")).toBe(4);
  });

  it("其余证券 = 2 位", () => {
    expect(pricePrecision("stock")).toBe(2);
    expect(pricePrecision("bond")).toBe(2);
  });

  it("未知 / 缺失按证券口径 2 位（猜成 4 位会让股价出现无意义尾数）", () => {
    expect(pricePrecision()).toBe(2);
    expect(pricePrecision(null)).toBe(2);
    expect(pricePrecision("")).toBe(2);
    expect(pricePrecision("some_new_type")).toBe(2);
  });
});

describe("formatPrice：与位数同源的格式化", () => {
  it("净值 4 位、股价 2 位，同一个函数两种口径", () => {
    expect(formatPrice(4.8124, "fund")).toBe("4.8124");
    expect(formatPrice(4.8124, "stock")).toBe("4.81");
  });

  it("补零到约定位数（4.8 不能只显示一位）", () => {
    expect(formatPrice(4.8, "fund")).toBe("4.8000");
  });

  it("非有限值统一占位，不渲染 NaN / null", () => {
    expect(formatPrice(null, "fund")).toBe(PRICE_PLACEHOLDER);
    expect(formatPrice(undefined, "fund")).toBe(PRICE_PLACEHOLDER);
    expect(formatPrice(Number.NaN, "fund")).toBe(PRICE_PLACEHOLDER);
    expect(formatPrice(Number.POSITIVE_INFINITY, "fund")).toBe(
      PRICE_PLACEHOLDER
    );
  });

  it("0 是有效价格，不能被当成 falsy 吞掉", () => {
    expect(formatPrice(0, "fund")).toBe("0.0000");
  });
});

describe("priceAxisLabelFormatter：图表出口与 formatPrice 同源", () => {
  it("轴标签与 tooltip 必须给同一个结果（本卡成因就是两者各说一套）", () => {
    const axis = priceAxisLabelFormatter("fund");
    expect(axis(4.8124)).toBe(formatPrice(4.8124, "fund"));
    expect(axis(4.8124)).toBe("4.8124");
  });

  it("可直接挂 echarts axisLabel.formatter（入参是数值）", () => {
    const axis = priceAxisLabelFormatter("stock");
    expect(axis(12.5)).toBe("12.50");
  });
});
