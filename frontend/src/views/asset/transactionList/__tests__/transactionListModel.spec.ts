/**
 * TransactionList 拆分时抽出的纯函数口径（#980）。
 *
 * 重点盯四处容易静默出错的地方：月汇总的正负号、自定义时间范围的 UTC 取日、
 * 「默认展开最近两个月」数的是有记录的月还是日历月、月归属的日期兜底口径。
 */
import { describe, expect, it } from "vitest";
import {
  buildFilterParams,
  buildTransactionParams,
  defaultFilters,
  groupByMonth,
  monthLabel,
  monthSummaryOf,
  recentMonthsOf,
  signedAmount,
  statusLabel,
  statusTag,
  summaryRangeLabel,
  timelineDotClass,
  timelineIcon,
  typeTag,
  TXN_TYPE_OPTIONS
} from "../transactionListModel";

const txn = (over: Record<string, any> = {}) =>
  ({
    id: 1,
    type: "buy",
    amount: 100,
    fee: 1,
    status: "success",
    trade_date: "2026-03-10",
    account_name: "主账户",
    position_name: "沪深300",
    notes: null,
    ...over
  }) as any;

describe("defaultFilters", () => {
  it("每次返回新对象，不共享引用", () => {
    const a = defaultFilters();
    const b = defaultFilters();
    a.symbol = "000001";
    expect(b.symbol).toBe("");
    expect(b).toMatchObject({
      type: "",
      assetType: "",
      status: "",
      timeRange: "",
      customDate: null,
      symbol: ""
    });
  });
});

describe("buildTransactionParams", () => {
  it("空筛选项一律不下发（只留分页）", () => {
    expect(buildTransactionParams(defaultFilters(), 2, 20)).toEqual({
      page: 2,
      per_page: 20
    });
  });

  it("五个筛选项各自映射到后端字段名", () => {
    const params = buildTransactionParams(
      {
        ...defaultFilters(),
        type: "buy",
        assetType: "fund",
        status: "success",
        timeRange: "3m",
        symbol: "000001"
      },
      1,
      10
    );
    expect(params).toMatchObject({
      type: "buy",
      asset_type: "fund",
      status: "success",
      time_range: "3m",
      symbol: "000001"
    });
    // 前端 camelCase 不能漏到请求体里
    expect(params.assetType).toBeUndefined();
    expect(params.timeRange).toBeUndefined();
  });

  it("自定义时间范围按 UTC 取日（沿用 toISOString 口径）", () => {
    const params = buildTransactionParams(
      {
        ...defaultFilters(),
        timeRange: "custom",
        customDate: [
          new Date("2026-01-05T00:00:00Z"),
          new Date("2026-02-06T00:00:00Z")
        ]
      },
      1,
      10
    );
    expect(params.start_date).toBe("2026-01-05");
    expect(params.end_date).toBe("2026-02-06");
  });
});

describe("buildFilterParams", () => {
  it("只出筛选字段，不带分页（汇总条用同一份）", () => {
    const params = buildFilterParams({
      ...defaultFilters(),
      type: "sell",
      timeRange: "1y"
    });
    expect(params).toEqual({ type: "sell", time_range: "1y" });
    expect(params.page).toBeUndefined();
    expect(params.per_page).toBeUndefined();
  });

  it("buildTransactionParams = 筛选字段 + 分页（两个函数不能各写一份映射）", () => {
    const filters = { ...defaultFilters(), status: "success" };
    expect(buildTransactionParams(filters, 3, 50)).toEqual({
      page: 3,
      per_page: 50,
      ...buildFilterParams(filters)
    });
  });
});

describe("summaryRangeLabel", () => {
  it("没选时间范围时写「全部时间」——不写范围会被读成全历史", () => {
    expect(summaryRangeLabel(defaultFilters())).toBe("全部时间");
  });

  it("四个预设范围各自成文", () => {
    expect(summaryRangeLabel({ ...defaultFilters(), timeRange: "1m" })).toBe(
      "近一个月"
    );
    expect(summaryRangeLabel({ ...defaultFilters(), timeRange: "1y" })).toBe(
      "近一年"
    );
  });

  it("自定义范围按**本地日期**成文（不是 UTC：东八区会差一天）", () => {
    const label = summaryRangeLabel({
      ...defaultFilters(),
      timeRange: "custom",
      customDate: [new Date(2026, 0, 5), new Date(2026, 5, 30)]
    });
    expect(label).toBe("2026-01-05 至 2026-06-30");
  });

  it("选了自定义却没填日期时如实写「自定义时段」，不冒充全部时间", () => {
    expect(
      summaryRangeLabel({ ...defaultFilters(), timeRange: "custom" })
    ).toBe("自定义时段");
  });

  it("symbol 预筛必须进文案：从产品详情进来时汇总只覆盖那一个产品", () => {
    expect(
      summaryRangeLabel({
        ...defaultFilters(),
        symbol: "001937",
        timeRange: "1y"
      })
    ).toBe("001937 · 近一年");
  });
});

describe("groupByMonth", () => {
  it("按月份分组并保持首次出现顺序（后端已按有效交易日倒序返回）", () => {
    const groups = groupByMonth([
      txn({ id: 1, trade_date: "2026-03-11" }),
      txn({ id: 2, trade_date: "2026-02-10" }),
      txn({ id: 3, trade_date: "2026-03-02" })
    ]);
    expect(groups.map(g => g.month)).toEqual(["2026-03", "2026-02"]);
    expect(groups[0].records.map(t => t.id)).toEqual([1, 3]);
    expect(groups[1].records.map(t => t.id)).toEqual([2]);
  });

  it("空列表返回空数组", () => {
    expect(groupByMonth([])).toEqual([]);
  });

  it("交易日优先、确认日兜底（只有确认日的行也进正确的月份）", () => {
    const groups = groupByMonth([
      txn({ id: 1, trade_date: "2026-03-11", confirm_date: "2026-04-12" }),
      txn({ id: 2, trade_date: null, confirm_date: "2026-04-12" })
    ]);
    expect(groups.map(g => g.month)).toEqual(["2026-03", "2026-04"]);
    expect(groups[1].records.map(t => t.id)).toEqual([2]);
  });

  it("日期全缺的行进「未标注日期」桶，并沉到最后", () => {
    const groups = groupByMonth([
      txn({ id: 1, trade_date: null, confirm_date: null }),
      txn({ id: 2, trade_date: "2026-01-05" })
    ]);
    expect(groups.map(g => g.month)).toEqual(["2026-01", ""]);
    expect(groups[1].label).toBe("未标注日期");
  });
});

describe("monthSummaryOf", () => {
  const make = (id, type, amount, trade_date = "2026-03-10") =>
    txn({ id, type, amount, trade_date });

  it("笔数 / 买入 / 卖出 各自累加，净额按方向求和", () => {
    const summary = monthSummaryOf([
      make(1, "sell", 300),
      make(2, "dividend", 20),
      make(3, "deposit", 1000),
      make(4, "buy", 200),
      make(5, "withdraw", 50)
    ]);
    expect(summary).toEqual({
      count: 5,
      buy: 200,
      sell: 300,
      // 卖出 300 + 分红 20 + 存入 1000 − 买入 200 − 取出 50
      net: 1070
    });
  });

  it("金额是字符串也按数值累加", () => {
    const summary = monthSummaryOf([
      make(1, "sell", "123.45"),
      make(2, "buy", "23.45")
    ]);
    expect(summary.net).toBeCloseTo(100, 6);
    expect(summary.buy).toBeCloseTo(23.45, 6);
    expect(summary.sell).toBeCloseTo(123.45, 6);
  });

  it("金额缺失或非数值时按 0 处理，不产出 NaN", () => {
    const summary = monthSummaryOf([
      make(1, "buy", null),
      make(2, "sell", "abc")
    ]);
    expect(summary.buy).toBe(0);
    expect(summary.sell).toBe(0);
    expect(Number.isNaN(summary.net)).toBe(false);
  });

  it("空数组产出零值（月头不显示 NaN）", () => {
    expect(monthSummaryOf([])).toEqual({ count: 0, buy: 0, sell: 0, net: 0 });
  });
});

describe("recentMonthsOf", () => {
  it("取最近 N 个有记录的月，默认两个", () => {
    const groups = groupByMonth([
      txn({ id: 1, trade_date: "2026-03-31" }),
      txn({ id: 2, trade_date: "2026-02-01" }),
      txn({ id: 3, trade_date: "2026-01-15" })
    ]);
    expect(recentMonthsOf(groups)).toEqual(["2026-03", "2026-02"]);
    expect(recentMonthsOf(groups, 1)).toEqual(["2026-03"]);
  });

  it("「未标注日期」桶不占名额（它不是一个月）", () => {
    const groups = groupByMonth([
      txn({ id: 1, trade_date: null, confirm_date: null }),
      txn({ id: 2, trade_date: "2026-01-15" })
    ]);
    expect(recentMonthsOf(groups, 2)).toEqual(["2026-01"]);
  });

  it("空分组返回空数组", () => {
    expect(recentMonthsOf([])).toEqual([]);
  });
});

describe("monthLabel", () => {
  it("去掉补零（03 月要读成 3 月，不能出现「2026 年 03 月」）", () => {
    expect(monthLabel("2026-03")).toBe("2026 年 3 月");
    expect(monthLabel("2026-10")).toBe("2026 年 10 月");
  });

  it("空月份读作未标注日期", () => {
    expect(monthLabel("")).toBe("未标注日期");
  });
});

describe("TXN_TYPE_OPTIONS", () => {
  it("一级筛选是「全部 + 五种业务类型」，值是后端 txn_type 原值", () => {
    expect(TXN_TYPE_OPTIONS.map(o => o.value)).toEqual([
      "",
      "buy",
      "sell",
      "dividend",
      "deposit",
      "withdraw"
    ]);
  });
});

describe("timelineIcon / timelineDotClass", () => {
  it("五种操作各有图标与色点", () => {
    expect(timelineIcon("buy")).toBe("ep:arrow-down");
    expect(timelineIcon("sell")).toBe("ep:arrow-up");
    expect(timelineIcon("dividend")).toBe("ep:present");
    expect(timelineIcon("deposit")).toBe("ep:wallet");
    expect(timelineIcon("withdraw")).toBe("ep:money");
    expect(timelineDotClass("buy")).toBe("dot-buy");
    expect(timelineDotClass("sell")).toBe("dot-sell");
    expect(timelineDotClass("dividend")).toBe("dot-dividend");
    expect(timelineDotClass("deposit")).toBe("dot-deposit");
    expect(timelineDotClass("withdraw")).toBe("dot-withdraw");
  });

  it("未知类型落到默认档", () => {
    expect(timelineIcon("transfer")).toBe("ep:arrow-down");
    expect(timelineDotClass("transfer")).toBe("dot-default");
  });
});

describe("signedAmount", () => {
  it("流入为正、流出为负", () => {
    expect(signedAmount(txn({ type: "sell", amount: 100 }))).toBe(100);
    expect(signedAmount(txn({ type: "dividend", amount: 100 }))).toBe(100);
    expect(signedAmount(txn({ type: "deposit", amount: 100 }))).toBe(100);
    expect(signedAmount(txn({ type: "buy", amount: 100 }))).toBe(-100);
    expect(signedAmount(txn({ type: "withdraw", amount: 100 }))).toBe(-100);
  });

  it("金额缺失或非数值时按 0 处理，不产出 NaN", () => {
    expect(signedAmount(txn({ type: "buy", amount: null }))).toBe(-0);
    expect(signedAmount(txn({ type: "buy", amount: "abc" }))).toBe(-0);
    expect(signedAmount(txn({ type: "sell", amount: undefined }))).toBe(0);
  });
});

describe("typeTag / statusTag / statusLabel", () => {
  it("操作类型对应的标签色", () => {
    expect(typeTag("buy")).toBe("success");
    expect(typeTag("sell")).toBe("danger");
    expect(typeTag("dividend")).toBe("warning");
    expect(typeTag("deposit")).toBe("primary");
    expect(typeTag("withdraw")).toBe("info");
    expect(typeTag("unknown")).toBe("primary");
  });

  it("状态对应的标签色与文案", () => {
    expect(statusTag("success")).toBe("success");
    expect(statusTag("failed")).toBe("danger");
    expect(statusTag("cancelled")).toBe("info");
    expect(statusTag("pending")).toBe("warning");
    expect(statusTag("unknown")).toBe("primary");

    expect(statusLabel("success")).toBe("成功");
    expect(statusLabel("failed")).toBe("失败");
    expect(statusLabel("cancelled")).toBe("已撤单");
    expect(statusLabel("pending")).toBe("可撤单");
    // 未知状态原样透出，避免文案变空
    expect(statusLabel("weird")).toBe("weird");
  });
});
