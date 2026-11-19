/**
 * 记一笔「买入数量」字段的品种口径（2026-11-16，用户报「股票买入怎么也是按份额算」）。
 *
 * 钉住三件事：
 * 1. 基金 / 货基仍是「确认份额、金额为主量」（2 位精度，金额→份额）；
 * 2. 股票 / ETF / 可转债是「成交数量、数量为主量」（0 位、一手为步进，金额派生）；
 * 3. 投顾组合没有这个字段（D70），未选标的时按账户类型兜底。
 *
 * 一手数量来自 utils/trading.getStep（与卖出侧同一份），故科创板 200、可转债 10 一并钉住——
 * 这是「按整手申报」的判据，后端 validate_buy 用的也是同一组数字。
 */
import { describe, expect, it } from "vitest";
import { buyQuantityMeta, buyQuantityMode } from "../buyQuantityMeta";

describe("buyQuantityMode", () => {
  it("基金 / 货币基金走 fund（金额为主量）", () => {
    expect(buyQuantityMode({ type: "fund" })).toBe("fund");
    expect(buyQuantityMode({ type: "money_fund" })).toBe("fund");
  });

  it("股票 / ETF / 可转债走 trade（数量为主量）", () => {
    expect(buyQuantityMode({ type: "stock" })).toBe("trade");
    expect(buyQuantityMode({ type: "etf" })).toBe("trade");
    expect(buyQuantityMode({ type: "bond" })).toBe("trade");
  });

  it("投顾组合没有份额与价格，整块不渲染（D70）", () => {
    expect(buyQuantityMode({ type: "portfolio" })).toBe("none");
  });

  it("银行理财同样没有份额与价格，整块不渲染（D121）", () => {
    // 不拦住的话它会落到 trade 口径：显示「成交数量」并要求整手，用户被迫
    // 给一笔没有份额的理财填一个「手数」。
    expect(buyQuantityMode({ type: "bank_wealth" })).toBe("none");
  });

  it("未选标的时按账户类型兜底：证券账户先按 trade，其余按 fund", () => {
    expect(buyQuantityMode({ ledgerType: "stock" })).toBe("trade");
    expect(buyQuantityMode({ ledgerType: "fund" })).toBe("fund");
    expect(buyQuantityMode({ ledgerType: "bank" })).toBe("fund");
    expect(buyQuantityMode({})).toBe("fund");
  });
});

describe("buyQuantityMeta", () => {
  it("基金：确认份额、2 位精度、金额是主量", () => {
    const meta = buyQuantityMeta({ type: "fund" });
    expect(meta.label).toBe("确认份额");
    expect(meta.precision).toBe(2);
    expect(meta.amountDerived).toBe(false);
    expect(meta.label).not.toContain("成交数量");
  });

  it("货币基金同样是份额口径（此前按 0 位精度展示，会把 1000.5 份写成 1001 份）", () => {
    const meta = buyQuantityMeta({ type: "money_fund" });
    expect(meta.label).toBe("确认份额");
    expect(meta.precision).toBe(2);
  });

  it("股票：成交数量、0 位精度、一手 100 股、金额由数量派生", () => {
    const meta = buyQuantityMeta({
      type: "stock",
      market: "CN_A",
      symbol: "SH600519"
    });
    expect(meta.label).toBe("成交数量");
    expect(meta.precision).toBe(0);
    expect(meta.step).toBe(100);
    expect(meta.min).toBe(100);
    expect(meta.unit).toBe("股");
    expect(meta.amountDerived).toBe(true);
    expect(meta.hint).toContain("整手");
  });

  it("科创板一手 200 股（与后端 validate_buy 的 min_unit 同源）", () => {
    const meta = buyQuantityMeta({
      type: "stock",
      market: "CN_A",
      symbol: "SH688981"
    });
    expect(meta.step).toBe(200);
    expect(meta.min).toBe(200);
  });

  it("可转债按张计数、一手 10 张", () => {
    const meta = buyQuantityMeta({ type: "bond", market: "CN_A" });
    expect(meta.label).toBe("成交数量");
    expect(meta.unit).toBe("张");
    expect(meta.step).toBe(10);
  });

  it("投顾组合不产出可用字段（组件按 mode !== 'none' 整块隐藏）", () => {
    expect(buyQuantityMeta({ type: "portfolio" }).mode).toBe("none");
  });

  it("银行理财不产出可用字段（同上，D121）", () => {
    expect(buyQuantityMeta({ type: "bank_wealth" }).mode).toBe("none");
  });
});
