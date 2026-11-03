/**
 * 盘中「价格替换」的判据（纯函数，node 环境可测）。
 *
 * 这里钉的是一条容易被写错的边界：**只换价，不重算盈亏**。
 * 一旦有人改成「前端拿实时价 × 份额自己算当日盈亏」，下面第 3 条会先红——
 * 它会多出/少掉「后端已算好但前端不知道」的部分（当日建仓、卖出、外币、估值定格），
 * 而收盘那一刻数字还会「跳」一下才对上。
 */
import { describe, expect, it } from "vitest";
import type { TodayPnlData } from "@/api/summary";
import {
  applyPriceOverlay,
  formatMonthDay,
  shanghaiTodayIso,
  todayPnlSubtitle
} from "../todayPnlOverlay";

function makeData(overrides: Partial<TodayPnlData> = {}): TodayPnlData {
  return {
    date: "2026-11-03",
    is_today: true,
    state: "updown",
    status: "confirmed",
    total_pnl: 200,
    total_rate: 10,
    invested_value: 2200,
    other_value: 0,
    classes: [
      {
        key: "stock",
        label: "股票",
        pnl: 100,
        rate: 10,
        market_value: 1100,
        status: "confirmed"
      },
      {
        key: "fund",
        label: "基金",
        pnl: 100,
        rate: 10,
        market_value: 1100,
        status: "confirmed"
      }
    ],
    holdings: [
      { symbol: "SH600519", class: "stock", quantity: 100, price: 11 },
      { symbol: "000001", class: "fund", quantity: 1000, price: 1.1 }
    ],
    ...overrides
  };
}

describe("applyPriceOverlay", () => {
  it("没有实时价时原样返回，不改任何数字", () => {
    const data = makeData();
    const result = applyPriceOverlay(data, new Map());

    expect(result.applied).toBe(false);
    expect(result.data).toBe(data);
  });

  it("实时价与后端当日价相等时不算替换（增量必须恒为 0）", () => {
    const data = makeData();
    const result = applyPriceOverlay(
      data,
      new Map([
        ["SH600519", 11],
        ["000001", 1.1]
      ])
    );

    expect(result.applied).toBe(false);
    expect(result.data.total_pnl).toBe(200);
  });

  it("股票每份涨 1 元 × 100 份 ⇒ 分项与合计同步 +100，且状态转 estimated", () => {
    const data = makeData();
    const result = applyPriceOverlay(data, new Map([["SH600519", 12]]));

    expect(result.applied).toBe(true);
    const classes = Object.fromEntries(
      result.data.classes.map(item => [item.key, item])
    );
    expect(classes.stock.pnl).toBe(200); // 后端 100 + 增量 100
    expect(classes.stock.market_value).toBe(1200);
    expect(classes.fund.pnl).toBe(100); // 未替换的大类不动
    expect(result.data.total_pnl).toBe(300);
    expect(result.data.invested_value).toBe(2300);
    // 卡内自洽：分项之和 ≡ 合计（替换后仍成立）
    expect(
      result.data.classes.reduce((sum, item) => sum + (item.pnl ?? 0), 0)
    ).toBe(result.data.total_pnl);
    expect(result.data.status).toBe("estimated");
  });

  it("分项原本为 null（今天没报价）时，替换后等于增量本身，而不是凭空 0", () => {
    const data = makeData({
      status: "partial",
      total_pnl: 0,
      classes: [
        {
          key: "stock",
          label: "股票",
          pnl: null,
          rate: null,
          market_value: 1100,
          status: "partial"
        }
      ]
    });
    const result = applyPriceOverlay(data, new Map([["SH600519", 12]]));

    expect(result.applied).toBe(true);
    expect(result.data.classes[0].pnl).toBe(100);
    expect(result.data.classes[0].status).toBe("estimated");
  });

  it("后端是「最近交易日」时，实时增量替换当日收益而不是叠加（不把两天叠成一天）", () => {
    const data = makeData({
      date: "2026-11-02",
      is_today: false,
      total_pnl: 200, // 昨天的收益
      classes: [
        {
          key: "stock",
          label: "股票",
          pnl: 100,
          rate: 10,
          market_value: 1100,
          status: "confirmed"
        },
        {
          key: "fund",
          label: "基金",
          pnl: 100,
          rate: 10,
          market_value: 1100,
          status: "confirmed"
        }
      ]
    });

    const result = applyPriceOverlay(data, new Map([["SH600519", 12]]), {
      replaceBase: true,
      todayIso: "2026-11-03"
    });

    expect(result.applied).toBe(true);
    expect(result.data.total_pnl).toBe(100); // 只有今天的 100，不是 200 + 100
    expect(result.data.date).toBe("2026-11-03");
    expect(result.data.is_today).toBe(true);
    expect(result.data.invested_value).toBe(2300); // 昨日市值 + 今日增量

    const classes = Object.fromEntries(
      result.data.classes.map(item => [item.key, item])
    );
    // 基金今天一笔行情都没有 ⇒ 是「没数」而不是「0.00」
    expect(classes.fund.pnl).toBeNull();
    expect(classes.fund.status).toBe("partial");
    // 合计仍等于已出价分项之和
    expect(
      result.data.classes.reduce((sum, item) => sum + (item.pnl ?? 0), 0)
    ).toBe(result.data.total_pnl);
  });

  it("忽略非法价 / 无份额持仓 / 行情里多出来的标的，不让脏值污染合计", () => {
    const data = makeData({
      holdings: [
        { symbol: "SH600519", class: "stock", quantity: 100, price: 11 },
        { symbol: "000001", class: "fund", quantity: 0, price: 1.1 },
        { symbol: "999999", class: "fund", quantity: 10, price: 0 }
      ]
    });
    const result = applyPriceOverlay(
      data,
      new Map([
        ["000001", 1.2],
        ["999999", 1.3],
        ["NOT_IN_CARD", 5]
      ])
    );

    expect(result.applied).toBe(false);
    expect(result.data.total_pnl).toBe(200);
  });
});

describe("shanghaiTodayIso", () => {
  it("按上海时区取日期（UTC 16:30 已跨日到上海的次日）", () => {
    expect(shanghaiTodayIso(new Date("2026-11-02T16:30:00Z"))).toBe(
      "2026-11-03"
    );
    expect(shanghaiTodayIso(new Date("2026-11-02T15:59:00Z"))).toBe(
      "2026-11-02"
    );
  });
});

describe("todayPnlSubtitle / formatMonthDay", () => {
  it("盘中替换过 ⇒ 带上更新时间；收盘估值 ⇒ 说明会自动确认", () => {
    expect(
      todayPnlSubtitle({
        status: "estimated",
        isToday: true,
        date: "2026-11-03",
        updateTime: "14:32"
      })
    ).toContain("14:32");
    expect(
      todayPnlSubtitle({
        status: "estimated",
        isToday: true,
        date: "2026-11-03"
      })
    ).toContain("自动确认");
  });

  it("今天还没有当日价 ⇒ 明写「最近交易日」，不拿昨天的数当今天", () => {
    expect(
      todayPnlSubtitle({
        status: "confirmed",
        isToday: false,
        date: "2026-11-02"
      })
    ).toContain("最近交易日");
    expect(formatMonthDay("2026-11-02")).toBe("11月2日");
  });

  it("已确认 ⇒ 安静态文案（不挂「估」）", () => {
    expect(
      todayPnlSubtitle({
        status: "confirmed",
        isToday: true,
        date: "2026-11-03"
      })
    ).toBe("官方净值已确认");
  });
});
