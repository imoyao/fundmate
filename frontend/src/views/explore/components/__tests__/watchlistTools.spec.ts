/**
 * 深度分析站点清单（#980 批 B5 拆出 `watchlistTools.ts` 时补的网）。
 *
 * 规则很简单，但它是「基金 / ETF 多一个天天基金」这类**类型特判**的典型：
 * 写在 `.vue` 里时改一个 `===` 就能悄悄把股票也塞进天天基金入口，
 * 而界面上只会多一个点了 404 的菜单项，没有任何报错。
 */
import { describe, expect, it } from "vitest";
import { getAvailableTools } from "../watchlistTools";

describe("getAvailableTools", () => {
  it("股票 / 债券 / 指数：两个通用站点", () => {
    for (const type of ["stock", "bond", "index"]) {
      expect(getAvailableTools(type).map(t => t.key)).toEqual([
        "xueqiu",
        "eastmoney"
      ]);
    }
  });

  it("基金 / ETF：多一个天天基金（唯一能查持仓明细的地方）", () => {
    for (const type of ["fund", "etf"]) {
      expect(getAvailableTools(type).map(t => t.key)).toEqual([
        "xueqiu",
        "eastmoney",
        "tiantian"
      ]);
    }
  });

  it("未知类型按通用处理，不抛错也不给天天基金", () => {
    expect(getAvailableTools("").map(t => t.key)).toEqual([
      "xueqiu",
      "eastmoney"
    ]);
    expect(getAvailableTools("convertible").map(t => t.key)).toEqual([
      "xueqiu",
      "eastmoney"
    ]);
  });

  it("每次返回新数组：调用方 push 不会污染下一次（原先两处共用会串味）", () => {
    const mine = getAvailableTools("stock");
    mine.push({ key: "x", label: "污染" });
    expect(getAvailableTools("stock")).toHaveLength(2);
  });

  it("标签是中文站名，不是 key", () => {
    expect(getAvailableTools("fund").map(t => t.label)).toEqual([
      "雪球社区",
      "东方财富",
      "天天基金"
    ]);
  });
});
