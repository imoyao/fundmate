/**
 * PnlCalendar 空态判据（#980 批 B4 拆出 `emptyState.ts` 时补的网）。
 *
 * 这些判据以前埋在 `index.vue` 的 computed 里，只能靠「打开页面看看」验证；
 * 而它们一旦写反，界面不报错、只是把「快照任务没跑」说成「你的持仓没有估值」——
 * 正是 #1812 上线首日踩的坑。抽成纯函数后逐条钉住。
 */
import { describe, expect, it } from "vitest";
import type { PnlCalendarSeries } from "@/api/summary";
import {
  EMPTY_NO_VALUATION,
  emptyDataGapHint,
  emptyHintFor,
  emptyScopeFor,
  isDataGap,
  jumpButtonTextFor,
  latestPriceLabelFor
} from "../emptyState";

/** 只给判据用到的字段，其余用最小占位并整体断言为载荷类型 */
function series(over: Partial<PnlCalendarSeries>): PnlCalendarSeries {
  return {
    ledger_id: null,
    scope: "family",
    start_date: "2026-10-01",
    end_date: "2026-10-31",
    month_total: 0,
    range_rate: null,
    granularity: "day",
    has_any_price: true,
    coverage: {
      total_positions: 0,
      priced_positions: 0,
      unpriced_positions: 0
    },
    latest_price_date: null,
    first_txn_date: null,
    days: [],
    periods: [],
    ...over
  } as PnlCalendarSeries;
}

describe("isDataGap", () => {
  it("无 coverage 诊断时不下断言（不是缺口）", () => {
    expect(
      isDataGap(
        series({
          coverage: undefined as unknown as PnlCalendarSeries["coverage"]
        })
      )
    ).toBe(false);
  });

  it("一条价都没取到 ⇒ 数据缺口", () => {
    expect(
      isDataGap(
        series({
          coverage: {
            total_positions: 3,
            priced_positions: 0,
            unpriced_positions: 3
          },
          latest_price_date: null
        })
      )
    ).toBe(true);
  });

  it("priced=0 但有价格数据 ⇒ 不是缺口（是持仓本身按日无估值）", () => {
    expect(
      isDataGap(
        series({
          coverage: {
            total_positions: 3,
            priced_positions: 0,
            unpriced_positions: 3
          },
          latest_price_date: "2026-09-30"
        })
      )
    ).toBe(false);
  });

  it("有计价持仓 ⇒ 不是缺口", () => {
    expect(
      isDataGap(
        series({
          coverage: {
            total_positions: 3,
            priced_positions: 2,
            unpriced_positions: 1
          },
          latest_price_date: null
        })
      )
    ).toBe(false);
  });
});

describe("emptyScopeFor", () => {
  it("按粒度说「本月 / 本年 / 投资以来」", () => {
    expect(emptyScopeFor("day")).toBe("本月");
    expect(emptyScopeFor("month")).toBe("本年");
    expect(emptyScopeFor("year")).toBe("投资以来");
  });
});

describe("emptyHintFor", () => {
  it("数据缺口：带上粒度对应的范围与「任务没跑」的归因", () => {
    const text = emptyHintFor(
      series({
        coverage: {
          total_positions: 1,
          priced_positions: 0,
          unpriced_positions: 1
        },
        latest_price_date: null
      }),
      "month"
    );
    expect(text).toContain("本年还没有每日估值数据");
    expect(text).toContain("并非账户异常");
  });

  // ⚠️ 口径备忘（本批只搬运、不改行为，故先把它钉住）：
  // 判据是「priced=0 **且** latest_price_date 为空」，所以「是缺口」⇒ latest 必然为空
  // ⇒ 文案里那个日期位**恒为 —**。`emptyDataGapHint` 的日期参数目前是死参数
  // （函数本身可测，见最后一个 describe）。要让它有值，得先改判据
  // （例如「缺口 = 区间内无价但历史上有价」），那是口径改动，须单独出 PR。
  it("是缺口时日期位恒为 —（判据决定了 latest 必为空）", () => {
    const text = emptyHintFor(
      series({
        coverage: {
          total_positions: 1,
          priced_positions: 0,
          unpriced_positions: 1
        },
        latest_price_date: null
      }),
      "day"
    );
    expect(text).toContain("最近一次估值：—");
    expect(text).not.toContain("undefined");
  });

  it("非缺口 ⇒ 说产品属性，一个字都不提数据任务", () => {
    // 有计价持仓（priced>0）即使区间内没取到最新价，也不算「数据缺口」
    const text = emptyHintFor(
      series({
        has_any_price: false,
        coverage: {
          total_positions: 2,
          priced_positions: 1,
          unpriced_positions: 1
        },
        latest_price_date: null
      }),
      "day"
    );
    expect(text).toBe(EMPTY_NO_VALUATION);
    expect(text).not.toContain("快照");
  });
});

describe("latestPriceLabelFor", () => {
  const p = (d: string | null) => series({ latest_price_date: d });

  it("没有最新价 ⇒ 空串（跳转按钮随之隐藏）", () => {
    expect(latestPriceLabelFor(p(null), "day", new Date(2026, 9, 1))).toBe("");
  });

  it("年视图不给去处：区间恒定，跳了也不换区间", () => {
    expect(
      latestPriceLabelFor(p("2025-03-04"), "year", new Date(2026, 9, 1))
    ).toBe("");
  });

  it("月视图：同年不给按钮，跨年给「2025 年」", () => {
    expect(
      latestPriceLabelFor(p("2026-03-04"), "month", new Date(2026, 9, 1))
    ).toBe("");
    expect(
      latestPriceLabelFor(p("2025-12-31"), "month", new Date(2026, 9, 1))
    ).toBe("2025 年");
  });

  it("日视图：已在同月不给按钮，跨月给「YYYY 年 MM 月」", () => {
    expect(
      latestPriceLabelFor(p("2026-10-08"), "day", new Date(2026, 9, 1))
    ).toBe("");
    expect(
      latestPriceLabelFor(p("2026-08-08"), "day", new Date(2026, 9, 1))
    ).toBe("2026 年 08 月");
  });

  it("日视图跨年同样给出可读年月（补零不能丢）", () => {
    expect(
      latestPriceLabelFor(p("2025-01-05"), "day", new Date(2026, 9, 1))
    ).toBe("2025 年 01 月");
  });
});

describe("jumpButtonTextFor", () => {
  it("日粒度跳「月份」，月 / 年粒度跳「年份」", () => {
    expect(jumpButtonTextFor("2026 年 08 月", "day")).toBe(
      "查看 2026 年 08 月 有数据的月份"
    );
    expect(jumpButtonTextFor("2025 年", "month")).toBe(
      "查看 2025 年 有数据的年份"
    );
  });
});

describe("emptyDataGapHint", () => {
  it("范围 + 日期 + 归因三件套齐全", () => {
    expect(emptyDataGapHint("2026-09-30", "投资以来")).toBe(
      "投资以来还没有每日估值数据。最近一次估值：2026-09-30。" +
        "通常是每日快照任务未运行所致，并非账户异常。"
    );
  });
});
