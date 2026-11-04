import { describe, expect, it } from "vitest";
import type { BenchmarkExcessResult } from "@/api/summary";
import {
  benchmarkCaptionOf,
  benchmarkLabelOf,
  excessCaptionOf,
  excessColorOf,
  excessValueText,
  ledgerTypeLabel,
  slicePage,
  sortHoldings,
  unwrapList,
  type PortfolioHolding
} from "../portfolioDetailModel";

const RANGE = "近 90 天";

/** 造一份区间超额结果（只覆盖断言用到的字段） */
function excess(
  patch: Partial<BenchmarkExcessResult> = {},
  bench: Partial<NonNullable<BenchmarkExcessResult["benchmark"]>> = {}
): BenchmarkExcessResult {
  return {
    scope: "portfolio",
    ledger_id: null,
    portfolio_id: 7,
    start_date: "2026-07-26",
    end_date: "2026-10-24",
    range_rate: null,
    range_pnl: null,
    range_baseline: null,
    range_reason: null,
    benchmark: {
      code: "000300",
      name: "沪深300",
      range_return: null,
      bench_start_date: null,
      bench_end_date: null,
      reason: null,
      ...bench
    },
    excess_return: null,
    // #2685：曲线是接口必出字段（空数组 = 没有可画的日数据），夹具给默认值
    series: [],
    ...patch
  };
}

/** 造一条持仓 */
function holding(patch: PortfolioHolding = {}): PortfolioHolding {
  return { symbol: "110011", name: "某基金", market_value: 100, ...patch };
}

describe("接口信封解包", () => {
  it("扁平信封 { data: [...] } 直接取出", () => {
    expect(unwrapList<number>({ data: [1, 2] })).toEqual([1, 2]);
  });

  it("嵌套信封 { data: { data: [...] } } 也能取出", () => {
    expect(unwrapList<number>({ data: { data: [3] } })).toEqual([3]);
  });

  it("data 为 null / 非数组 / 整个响应为空时给空数组（不抛错）", () => {
    expect(unwrapList(null)).toEqual([]);
    expect(unwrapList({ data: null })).toEqual([]);
    expect(unwrapList({ data: { message: "ok" } })).toEqual([]);
    expect(unwrapList(undefined)).toEqual([]);
  });
});

describe("持仓排序", () => {
  const rows = [
    holding({ symbol: "A", market_value: 300 }),
    holding({ symbol: "B", market_value: 100 }),
    holding({ symbol: "C", market_value: 200 })
  ];

  it("没有排序字段时保持后端原序，且返回新数组（不就地改 props）", () => {
    const out = sortHoldings(rows, null, null);
    expect(out.map(r => r.symbol)).toEqual(["A", "B", "C"]);
    expect(out).not.toBe(rows);
  });

  it("升降序各按数值比较", () => {
    expect(
      sortHoldings(rows, "market_value", "descending").map(r => r.symbol)
    ).toEqual(["A", "C", "B"]);
    expect(
      sortHoldings(rows, "market_value", "ascending").map(r => r.symbol)
    ).toEqual(["B", "C", "A"]);
  });

  it("排序键缺值按 0 处理（否则 undefined 参与比较会得到 NaN、顺序随机）", () => {
    const mixed = [
      holding({ symbol: "X", market_value: undefined }),
      holding({ symbol: "Y", market_value: 50 })
    ];
    expect(
      sortHoldings(mixed, "market_value", "descending").map(r => r.symbol)
    ).toEqual(["Y", "X"]);
  });

  it("只给 prop 不给 order 时视为未排序", () => {
    expect(sortHoldings(rows, "market_value", null).map(r => r.symbol)).toEqual(
      ["A", "B", "C"]
    );
  });
});

describe("前端分页切片", () => {
  const list = [1, 2, 3, 4, 5];

  it("第一页取前 pageSize 条", () => {
    expect(slicePage(list, 1, 2)).toEqual([1, 2]);
  });

  it("末页不足时只返回剩余条目", () => {
    expect(slicePage(list, 3, 2)).toEqual([5]);
  });

  it("越界页返回空数组", () => {
    expect(slicePage(list, 9, 2)).toEqual([]);
  });
});

describe("账户类型文案", () => {
  it("现金 / 家庭 / 其它（含未知值）各归其位", () => {
    expect(ledgerTypeLabel("cash")).toBe("现金账户");
    expect(ledgerTypeLabel("family")).toBe("家庭账户");
    expect(ledgerTypeLabel("general")).toBe("通用账户");
    expect(ledgerTypeLabel("")).toBe("通用账户");
  });
});

describe("基准名与降级说明", () => {
  it("基准名优先后端归一后的宽基名，其次代码", () => {
    expect(benchmarkLabelOf(excess(), "用户原文")).toBe("沪深300");
    expect(benchmarkLabelOf(excess({}, { name: null }), "用户原文")).toBe(
      "000300"
    );
  });

  it("后端还没回来时回落用户所设原文，都没有则为 null", () => {
    expect(benchmarkLabelOf(null, "中证500")).toBe("中证500");
    expect(benchmarkLabelOf(null, null)).toBeNull();
  });

  it("基准同期收益有值时说明是「同期 x% · 近 90 天」", () => {
    expect(benchmarkCaptionOf(excess({}, { range_return: 1.2 }), RANGE)).toBe(
      "同期 +1.20% · 近 90 天"
    );
  });

  it("基准同期缺值时退到降级原因", () => {
    expect(
      benchmarkCaptionOf(excess({ range_reason: "no_members" }), RANGE)
    ).toBe("组合暂无关联账户 · 近 90 天");
  });

  it("既无数据也无原因时只给区间", () => {
    expect(benchmarkCaptionOf(null, RANGE)).toBe(RANGE);
    expect(benchmarkCaptionOf(excess(), RANGE)).toBe(RANGE);
  });
});

describe("超额收益数值与配色", () => {
  it("有值时保留两位小数（字符串交给 MetricCard）", () => {
    expect(excessValueText(excess({ excess_return: 2.345 }))).toBe("2.35");
  });

  it("缺值返回 null（MetricCard 显示 --，不造 0）", () => {
    expect(excessValueText(null)).toBeNull();
    expect(excessValueText(excess())).toBeNull();
  });

  it("正涨负跌，0 与缺值不上色", () => {
    expect(excessColorOf(excess({ excess_return: 1 }))).toBe(
      "var(--color-rise)"
    );
    expect(excessColorOf(excess({ excess_return: -1 }))).toBe(
      "var(--color-fall)"
    );
    expect(excessColorOf(excess({ excess_return: 0 }))).toBe("");
    expect(excessColorOf(null)).toBe("");
  });
});

describe("超额收益说明", () => {
  it("三条数据齐全时给对比式", () => {
    expect(
      excessCaptionOf(
        excess({ range_rate: 2, excess_return: 1 }, { range_return: 1 }),
        RANGE
      )
    ).toBe("近 90 天 · +2.00% vs +1.00%");
  });

  it("任一侧缺值就退到降级说明，不硬凑对比式", () => {
    expect(
      excessCaptionOf(
        excess(
          { range_rate: null, range_reason: "no_position" },
          { range_return: 1 }
        ),
        RANGE
      )
    ).toBe("区间内无持仓");
  });

  it("完全没有数据时只给区间", () => {
    expect(excessCaptionOf(null, RANGE)).toBe(RANGE);
  });

  it("未知降级原因给兜底文案", () => {
    expect(
      excessCaptionOf(excess({ range_reason: "baseline_missing" }), RANGE)
    ).toBe("暂无可比数据");
  });
});
