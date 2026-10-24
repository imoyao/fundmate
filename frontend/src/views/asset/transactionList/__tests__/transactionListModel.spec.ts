/**
 * TransactionList 拆分时抽出的纯函数口径（#980）。
 *
 * 重点盯三处容易静默出错的地方：日汇总的正负号、自定义时间范围的 UTC 取日、
 * 「近 30 天默认展开」的边界与基准日是否被改写。
 */
import { describe, expect, it } from "vitest";
import {
  buildTransactionParams,
  dayBalanceOf,
  defaultFilters,
  groupByDate,
  isDateInLast30Days,
  recentDatesOf,
  signedAmount,
  statusLabel,
  statusTag,
  timelineDotClass,
  timelineIcon,
  typeTag
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

describe("groupByDate", () => {
  it("按 trade_date 分组并保持首次出现顺序", () => {
    const groups = groupByDate([
      txn({ id: 1, trade_date: "2026-03-11" }),
      txn({ id: 2, trade_date: "2026-03-10" }),
      txn({ id: 3, trade_date: "2026-03-11" })
    ]);
    expect(Object.keys(groups)).toEqual(["2026-03-11", "2026-03-10"]);
    expect(groups["2026-03-11"].map(t => t.id)).toEqual([1, 3]);
    expect(groups["2026-03-10"].map(t => t.id)).toEqual([2]);
  });

  it("空列表返回空对象", () => {
    expect(groupByDate([])).toEqual({});
  });
});

describe("dayBalanceOf", () => {
  it("卖出 / 分红 / 存入算流入，其余算流出", () => {
    const groups = groupByDate([
      txn({ id: 1, type: "sell", amount: 300 }),
      txn({ id: 2, type: "dividend", amount: 20 }),
      txn({ id: 3, type: "deposit", amount: 1000 }),
      txn({ id: 4, type: "buy", amount: 200 }),
      txn({ id: 5, type: "withdraw", amount: 50 })
    ]);
    expect(dayBalanceOf(groups)["2026-03-10"]).toBe(300 + 20 + 1000 - 200 - 50);
  });

  it("金额是字符串也按数值累加", () => {
    const groups = groupByDate([
      txn({ id: 1, type: "sell", amount: "123.45" }),
      txn({ id: 2, type: "buy", amount: "23.45" })
    ]);
    expect(dayBalanceOf(groups)["2026-03-10"]).toBeCloseTo(100, 6);
  });

  it("按日期分别汇总", () => {
    const groups = groupByDate([
      txn({ id: 1, type: "buy", amount: 10, trade_date: "2026-03-11" }),
      txn({ id: 2, type: "sell", amount: 30, trade_date: "2026-03-10" })
    ]);
    expect(dayBalanceOf(groups)).toEqual({
      "2026-03-11": -10,
      "2026-03-10": 30
    });
  });
});

describe("isDateInLast30Days", () => {
  // 基准日与日期串都用 UTC 零点，避免本地时区把边界挪走一天
  const now = new Date("2026-03-31T00:00:00Z");

  it("当天算在范围内", () => {
    expect(isDateInLast30Days("2026-03-31", now)).toBe(true);
  });

  it("第 30 天算在范围内（含边界）", () => {
    expect(isDateInLast30Days("2026-03-01", now)).toBe(true);
  });

  it("第 31 天不算", () => {
    expect(isDateInLast30Days("2026-02-28", now)).toBe(false);
  });

  it("不修改调用方传入的基准日（原实现在此处每调一次就前移 30 天）", () => {
    const base = new Date("2026-03-31T00:00:00Z");
    const before = base.getTime();
    isDateInLast30Days("2026-01-01", base);
    isDateInLast30Days("2026-01-01", base);
    expect(base.getTime()).toBe(before);
  });
});

describe("recentDatesOf", () => {
  it("只挑最近 30 天的日期，并保持原有顺序", () => {
    const groups = groupByDate([
      txn({ id: 1, trade_date: "2026-03-31" }),
      txn({ id: 2, trade_date: "2026-02-01" }),
      txn({ id: 3, trade_date: "2026-03-15" })
    ]);
    expect(recentDatesOf(groups, new Date("2026-03-31T00:00:00Z"))).toEqual([
      "2026-03-31",
      "2026-03-15"
    ]);
  });

  it("空分组返回空数组", () => {
    expect(recentDatesOf({}, new Date("2026-03-31T00:00:00Z"))).toEqual([]);
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
