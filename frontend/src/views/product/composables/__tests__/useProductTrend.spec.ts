// 走势卡：默认区间跟「建仓」+ 买卖点落不下时必须说话（#2857）。
//
// ## WHY 有这份文件
//
// 这条链路的失效方式在本轮真机里完整演过一遍：默认 3M 把 3 个月以前的交易整批裁掉
// → `markerData` 一个点都产不出 → `hasMarkers` 为 false → **连「买卖点」勾选框都
// 一起消失**。用户在折线视图里找来找去，看到的是一个「没有这个功能」的界面，
// 而代码侧没有任何报错。这类缺陷只有把「区间是怎么定的」「落不下时说了什么」
// 这两条断言钉住，才不会下次再被当成「用户没找到」。
import { describe, it, expect, vi } from "vitest";
import { ref } from "vue";

const mocks = vi.hoisted(() => ({
  getProductTrend: vi.fn(),
  getTradeTimeline: vi.fn()
}));

vi.mock("@/api/products", () => ({
  getProductTrend: mocks.getProductTrend,
  getTradeTimeline: mocks.getTradeTimeline
}));

import { useProductTrend } from "../useProductTrend";

/** 让 watch 的异步回调与两次请求都跑完（node 环境下没有 flushPromises 依赖） */
const flush = async () => {
  for (let i = 0; i < 4; i++) await new Promise(r => setTimeout(r, 0));
};

function trendPayload(dates: string[]) {
  return {
    data: {
      symbol: "SZ002726",
      kind: "close",
      dates,
      values: dates.map((_, i) => 10 + i * 0.1),
      source: "测试源",
      basis: "前复权收盘价",
      range: "3M",
      requested_days: 90,
      available_days: 90,
      ohlc: dates.map((d, i) => ({
        date: d,
        open: 10 + i * 0.1,
        close: 10 + i * 0.1,
        high: 10.2 + i * 0.1,
        low: 9.8 + i * 0.1,
        volume: 1000
      }))
    }
  };
}

function timelinePayload(tradeDates: string[]) {
  const points = tradeDates.map((date, i) => ({
    txn_id: i + 1,
    date,
    side: "buy" as const,
    amount_yuan: 1550,
    quantity: 1000,
    price_yuan: 15.5,
    fee_yuan: 5,
    confirm_date: date,
    account_name: "测试账户",
    cost_before_avg_yuan: null,
    cost_after_yuan: 1550,
    closed: false
  }));
  return {
    data: {
      symbol: "SZ002726",
      points,
      cost_line: tradeDates.map(d => ({
        date: d,
        avg_cost_yuan: 15.5,
        cost_yuan: 1550
      })),
      contributions: [],
      profit_line: tradeDates.map((d, i) => ({
        date: d,
        realized_yuan: 0,
        invested_yuan: 1550 * (i + 1)
      })),
      summary: {
        buy_count: points.length,
        sell_count: 0,
        dividend_count: 0,
        total_buy_amount_yuan: 1550 * points.length,
        total_sell_amount_yuan: 0,
        total_dividend_yuan: 0,
        total_fee_yuan: 5 * points.length,
        total_invested_yuan: 1550 * points.length,
        realized_pnl_yuan: 0,
        first_trade_date: tradeDates[0] ?? null,
        last_trade_date: tradeDates.at(-1) ?? null,
        current_quantity: 1000 * points.length,
        current_cost_yuan: 1550 * points.length,
        current_avg_cost_yuan: 15.5,
        ignored_count: 0,
        ignored_types: {}
      }
    }
  };
}

async function boot(trendDates: string[], tradeDates: string[]) {
  mocks.getProductTrend.mockResolvedValue(trendPayload(trendDates));
  mocks.getTradeTimeline.mockResolvedValue(timelinePayload(tradeDates));
  const state = useProductTrend({
    symbol: ref("SZ002726"),
    hasPosition: ref(true),
    assetType: ref("stock")
  });
  await flush();
  return state;
}

/** 最近一次走势请求带的参数（区间自动切换后看它） */
function lastTrendArgs() {
  return mocks.getProductTrend.mock.calls.at(-1)?.[0];
}

describe("默认区间跟建仓（#2857）", () => {
  it("首笔买入日在 3M 之外 → 区间自动切到「建仓」，并用首笔日作 start", async () => {
    const state = await boot(
      ["2026-09-01", "2026-09-02", "2026-09-03"],
      ["2026-07-07", "2026-07-13"]
    );

    expect(state.range.value).toBe("HOLDING");
    expect(lastTrendArgs()).toMatchObject({ start: "2026-07-07" });
  });

  it("用户手动选过区间后不再自动改（只帮他选一次，不替他每次决定）", async () => {
    const state = await boot(["2026-09-01", "2026-09-02"], ["2026-07-07"]);
    state.pickRange("3M");
    await flush();

    expect(state.range.value).toBe("3M");
    expect(lastTrendArgs()).not.toHaveProperty("start");
  });

  it("没有流水（未持有）时保持 3M —— 没有建仓期可言", async () => {
    mocks.getProductTrend.mockResolvedValue(
      trendPayload(["2026-09-01", "2026-09-02"])
    );
    mocks.getTradeTimeline.mockResolvedValue(timelinePayload([]));
    const state = useProductTrend({
      symbol: ref("SZ002726"),
      hasPosition: ref(false),
      assetType: ref("stock")
    });
    await flush();

    expect(state.range.value).toBe("3M");
    expect(mocks.getTradeTimeline).not.toHaveBeenCalled();
  });
});

describe("买卖点落不下时必须说话（#2857）", () => {
  it("交易全在走势起点之前 → 报「行情自哪天起」，不报「本区间无买卖」", async () => {
    const state = await boot(
      ["2026-09-01", "2026-09-02"],
      ["2026-07-07", "2026-07-13"]
    );
    state.candleView.value = "line";
    await flush();

    // 数据被完全裁掉：这正是真机上「勾选框消失」的那个状态
    expect(state.hasMarkers.value).toBe(false);
    expect(state.markersHint.value).toContain("2026-09-01");
    expect(state.markersHint.value).toContain("2 笔");
  });

  it("交易落在轴上 → 正常出点，提示为空", async () => {
    const state = await boot(
      ["2026-07-07", "2026-07-10", "2026-07-13"],
      ["2026-07-07"]
    );
    state.candleView.value = "line";
    await flush();

    expect(state.sizedMarkers.value.buy.length).toBe(1);
    expect(state.markersHint.value).toBe("");
  });

  it("K 线视图下不说话（另有「折线视图才叠加」那句，不能两句互相打架）", async () => {
    const state = await boot(["2026-09-01", "2026-09-02"], ["2026-07-07"]);
    // 默认就是 K 线视图

    expect(state.markersHint.value).toBe("");
  });
});
