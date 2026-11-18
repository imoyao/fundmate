import { describe, it, expect } from "vitest";
import {
  normalizeQuoteDate,
  quoteMinutes,
  isConfirmedQuote,
  resolveQuotePrice
} from "../quoteStatus";

describe("normalizeQuoteDate：数据源自带日期归一成 YYYY-MM-DD", () => {
  it("紧凑格式 20261106 → 2026-11-06", () => {
    expect(normalizeQuoteDate("20261106")).toBe("2026-11-06");
  });
  it("带时分秒 2026-11-06 00:00:00 → 2026-11-06", () => {
    expect(normalizeQuoteDate("2026-11-06 00:00:00")).toBe("2026-11-06");
  });
  it("腾讯时间戳 20261106150000 → 2026-11-06", () => {
    expect(normalizeQuoteDate("20261106150000")).toBe("2026-11-06");
  });
  it("空 / 非法 → null（不靠本地时钟猜）", () => {
    expect(normalizeQuoteDate(null)).toBeNull();
    expect(normalizeQuoteDate("")).toBeNull();
    expect(normalizeQuoteDate("abc")).toBeNull();
  });
});

describe("quoteMinutes：HH:mm / HHmm / HH:mm:ss → 分钟数", () => {
  it("15:00 → 900", () => {
    expect(quoteMinutes("15:00")).toBe(900);
  });
  it("1500 → 900（紧凑）", () => {
    expect(quoteMinutes("1500")).toBe(900);
  });
  it("14:59:30 → 899", () => {
    expect(quoteMinutes("14:59:30")).toBe(899);
  });
  it("非法 → null", () => {
    expect(quoteMinutes("x")).toBeNull();
    expect(quoteMinutes(null)).toBeNull();
  });
});

describe("isConfirmedQuote：确认态判定（单一出口）", () => {
  const today = "2026-11-06";

  it("基金：净值日期 == 今天 ⇒ confirmed（不论时刻）", () => {
    expect(
      isConfirmedQuote({ type: "fund", priceDate: today, now: new Date(today) })
    ).toBe(true);
  });

  it("基金：净值日期不是今天 ⇒ estimated（次日凌晨/非交易日保守处理）", () => {
    expect(
      isConfirmedQuote({
        type: "fund",
        priceDate: "2026-11-05",
        now: new Date(today)
      })
    ).toBe(false);
  });

  it("场内：日期==今天 且 时刻 ≥ 15:00 ⇒ confirmed（当日收盘价已定）", () => {
    expect(
      isConfirmedQuote({
        type: "stock",
        priceDate: today,
        priceTime: "15:00",
        now: new Date(today)
      })
    ).toBe(true);
    expect(
      isConfirmedQuote({
        type: "stock",
        priceDate: today,
        priceTime: "15:01",
        now: new Date(today)
      })
    ).toBe(true);
  });

  it("场内：日期==今天 但 时刻 < 15:00 ⇒ estimated（盘中，仍是估值）", () => {
    expect(
      isConfirmedQuote({
        type: "stock",
        priceDate: today,
        priceTime: "14:59",
        now: new Date(today)
      })
    ).toBe(false);
  });

  it("日期缺失 / 非今天 ⇒ estimated（绝不把昨天的收盘价当今天的确认值）", () => {
    expect(
      isConfirmedQuote({ type: "stock", priceDate: null, now: new Date(today) })
    ).toBe(false);
    expect(
      isConfirmedQuote({
        type: "stock",
        priceDate: "2026-11-05",
        priceTime: "15:00",
        now: new Date(today)
      })
    ).toBe(false);
  });
});

describe("resolveQuotePrice：确认态取官方价、回落估值价", () => {
  it("confirmed 且官方价有效 ⇒ 用官方价", () => {
    expect(
      resolveQuotePrice({
        estimatedPrice: 110,
        officialPrice: 105,
        confirmed: true
      })
    ).toBe(105);
  });

  it("confirmed 但官方价缺失/非正 ⇒ 保守回落估值价", () => {
    expect(
      resolveQuotePrice({
        estimatedPrice: 110,
        officialPrice: null,
        confirmed: true
      })
    ).toBe(110);
    expect(
      resolveQuotePrice({
        estimatedPrice: 110,
        officialPrice: 0,
        confirmed: true
      })
    ).toBe(110);
  });

  it("estimated ⇒ 一律用估值价（即便带着官方价也不取）", () => {
    expect(
      resolveQuotePrice({
        estimatedPrice: 110,
        officialPrice: 105,
        confirmed: false
      })
    ).toBe(110);
  });
});
