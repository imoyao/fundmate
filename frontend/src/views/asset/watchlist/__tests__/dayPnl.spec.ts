/**
 * 自选页盈亏口径（2026-11-05 拆列：「今日估算」/「昨日盈亏」）。
 *
 * ## 这个文件钉什么
 *
 * 1. **两列口径互不混用**：今日估算是 `(T 实时价 − T-1 确认价)`、昨日盈亏是
 *    `(T-1 确认价 − T-2 确认价)`。后端 `compute_latest_quote` 只回填到 T-1（#824），
 *    所以 `row.current_price` 是 T-1、`row.prev_close` 是 T-2 —— 旧实现把后者减前者
 *    叫「当日盈亏」，盘中显示的是**昨天的真实值**（用户实测反馈）。
 * 2. **今日估算只认 `source === "realtime"`**：引擎行情不可达时回退静态价（就是 T-1），
 *    拿它当今日价会算出「今日 = 昨日」的假象；此时整组必须给 `null`。
 * 3. **实时源缺 T-1 基准时兜底 `row.current_price`，绝不兜底 `row.prev_close`**（T-2）：
 *    后者等于「今天的价格减前天的价格」，多算一天（腾讯基金格式走这条）。
 * 4. **拿不到实时行情就空白，绝不回落昨日数字**：这一列宁可 `—`，也不能把真实值
 *    冒充估算值；也不显示 `0.00`（会被读成「今天没赚没亏」）。
 * 5. **缺基准给 null，不给 0**（`prevClose ?? price` 恒等于 0 的假 0）。
 * 6. **零持仓时金额不成立、涨跌幅仍成立**：自选里大量标的只是「看着」。
 * 7. **汇总比例是市值加权，不是算术平均**，缺数据的行同时从分子分母剔除。
 * 8. **列定义**：两列常驻、命名不撞车、各带自己的 `derived`、都覆盖指数
 *    （指数无持仓 → 金额 `—`，但涨跌幅成立）。
 * 9. **排序能力不随改名丢失**：两列都走客户端整组排序，两行数各排各的
 *    （金额 / 涨幅，口径见 `sortMetric.ts`）；后端只有上一交易日收盘。
 *
 * ⚠️ 为什么测纯模块而不是直接调渲染器：vitest 环境是 node（无 DOM），
 * `columnRenderers.tsx` 会一路 import `.vue` 组件（见 `bondFormats.spec.ts` 的说明）。
 */
import { describe, expect, it } from "vitest";

import {
  computeDayPnl,
  resolveTodayEstimate,
  resolveTodayEstimateInput,
  resolveYesterdayPnl,
  resolveYesterdayPnlInput,
  sumDayPnl
} from "../dayPnl";
import { watchlistColumnDefs } from "../columnDefs";
import { toEastmoneySecid } from "@/utils/realtimeDataSources";

function colDef(key: string) {
  const def = watchlistColumnDefs.find(d => d.key === key);
  if (!def) throw new Error(`${key} 列定义缺失`);
  return def;
}

/** T-1 = 100（确认价）、T-2 = 98（确认价）、份额 10 */
const row = {
  symbol: "600519",
  current_price: 100,
  prev_close: 98,
  holding_quantity: 10
};

describe("computeDayPnl：有价 + 有基准才算得出来", () => {
  it("正常情形：金额按持仓数量、比例按基准", () => {
    expect(
      computeDayPnl({ price: 1.1, prevClose: 1.0, quantity: 1000 })
    ).toEqual({ value: 100, ratio: 10 });
  });

  it("缺基准 → 两项都是 null（不是 0）", () => {
    for (const prevClose of [null, undefined, 0, -1, NaN]) {
      expect(computeDayPnl({ price: 1.1, prevClose, quantity: 1000 })).toEqual({
        value: null,
        ratio: null
      });
    }
  });

  it("缺现价 → 两项都是 null", () => {
    expect(
      computeDayPnl({ price: null, prevClose: 1, quantity: 1000 })
    ).toEqual({ value: null, ratio: null });
  });

  it("无持仓：金额 null，但涨跌幅照给", () => {
    expect(computeDayPnl({ price: 1.1, prevClose: 1.0, quantity: 0 })).toEqual({
      value: null,
      ratio: 10
    });
    expect(
      computeDayPnl({ price: 1.1, prevClose: 1.0, quantity: null })
    ).toEqual({ value: null, ratio: 10 });
  });

  it("下跌给负号（金额与比例同号）", () => {
    expect(
      computeDayPnl({ price: 0.9, prevClose: 1.0, quantity: 1000 })
    ).toEqual({ value: -100, ratio: -10 });
  });

  it("比例保留两位（四舍五入）", () => {
    expect(computeDayPnl({ price: 1.0123, prevClose: 1.0 }).ratio).toBe(1.23);
  });
});

describe("resolveYesterdayPnl：已确认真实值（T-1 vs T-2），完全不读实时行情", () => {
  it("用 T-1 确认价减 T-2 确认价，份额照乘", () => {
    expect(resolveYesterdayPnlInput(row)).toEqual({
      price: 100,
      prevClose: 98,
      quantity: 10
    });
    expect(resolveYesterdayPnl(row)).toEqual({ value: 20, ratio: 2.04 });
  });

  it("就是 #2640 那列**实际算出来的数**（此前被误命名为「当日盈亏」）", () => {
    // 旧口径 (100 − 98) × 10 = 20；今日估算在同一行应是另一个数（下方断言）。
    expect(resolveYesterdayPnl(row).value).toBe(20);
  });

  it("缺 prev_close → null 而非拿现价顶替", () => {
    expect(
      resolveYesterdayPnl({ symbol: "x", current_price: 100, prev_close: null })
    ).toEqual({ value: null, ratio: null });
  });

  it("即使有实时行情，昨日盈亏也不变（函数根本不接收 quote）", () => {
    // 拆列前「开了实时就换价」正是两列串数的根源：盘中同一格忽而是昨天、忽而是今天。
    // 现在昨日盈亏是纯静态值，签名上就没有 quote 参数。
    const before = resolveYesterdayPnl(row);
    const after = resolveYesterdayPnl(row);
    expect(after).toEqual(before);
    expect(after).toEqual({ value: 20, ratio: 2.04 });
  });
});

describe("resolveTodayEstimate：只吃 realtime，基准恒为 T-1", () => {
  it("实时源自带 T-1 基准 → 用今日实时价减它", () => {
    expect(
      resolveTodayEstimateInput(row, {
        currentPrice: 110,
        prevClose: 100,
        source: "realtime"
      })
    ).toEqual({ price: 110, prevClose: 100, quantity: 10 });
    expect(
      resolveTodayEstimate(row, {
        currentPrice: 110,
        prevClose: 100,
        source: "realtime"
      })
    ).toEqual({ value: 100, ratio: 10 });
  });

  it("实时源缺基准 → 兜底 row.current_price(T-1)，**绝不**碰 row.prev_close(T-2)", () => {
    // 腾讯基金格式不给昨收。若错误兜底 prev_close(98)，会算出 120 / 12.24
    // ——「今天的价格减前天的价格」，多算一天。这是本次拆列修掉的引擎隐患。
    const input = resolveTodayEstimateInput(row, {
      currentPrice: 110,
      source: "realtime"
    });
    expect(input).toEqual({ price: 110, prevClose: 100, quantity: 10 });
    expect(input.prevClose).not.toBe(98);
    expect(
      resolveTodayEstimate(row, { currentPrice: 110, source: "realtime" })
    ).toEqual({ value: 100, ratio: 10 });
  });

  it("source=static（引擎回退静态价）→ 整组 null，不把 T-1 冒充今日", () => {
    // 静态价的 currentPrice 就是后端 T-1 确认价；给它配 T-1 基准会算出恒 0，
    // 配 T-2 则是昨天的数。两种都是「盘中看到昨天」，故直接空白。
    expect(
      resolveTodayEstimateInput(row, {
        currentPrice: 999,
        prevClose: 100,
        source: "static"
      })
    ).toEqual({ price: null, prevClose: null, quantity: 10 });
    expect(
      resolveTodayEstimate(row, {
        currentPrice: 999,
        prevClose: 100,
        source: "static"
      })
    ).toEqual({ value: null, ratio: null });
  });

  it("无行情 / 实时价非正 → null（宁可 `—`，不回落昨日数字）", () => {
    expect(resolveTodayEstimate(row)).toEqual({ value: null, ratio: null });
    expect(
      resolveTodayEstimate(row, { currentPrice: 0, source: "realtime" })
    ).toEqual({ value: null, ratio: null });
    expect(
      resolveTodayEstimate(row, { currentPrice: NaN, source: "realtime" })
    ).toEqual({ value: null, ratio: null });
  });

  it("同一行两列给出**不同**的数：估算不冒充真实值、真实值不冒充估算", () => {
    const today = resolveTodayEstimate(row, {
      currentPrice: 110,
      prevClose: 100,
      source: "realtime"
    });
    const yesterday = resolveYesterdayPnl(row);
    expect(today).toEqual({ value: 100, ratio: 10 });
    expect(yesterday).toEqual({ value: 20, ratio: 2.04 });
    expect(today.value).not.toBe(yesterday.value);
  });
});

describe("sumDayPnl：两列共用，比例按基准市值加权", () => {
  it("大仓小涨 + 小仓暴涨 → 接近大仓的涨幅（算术平均会得到中间值）", () => {
    const summary = sumDayPnl([
      { price: 101, prevClose: 100, quantity: 100000 }, // +1%，基准市值 10,000,000
      { price: 110, prevClose: 100, quantity: 100 } // +10%，基准市值 10,000
    ]);
    expect(summary.value).toBe(101000);
    // (100000 + 1000) / 10010000 ≈ 1.0090%，算术平均则是 5.5%
    expect(summary.ratio).toBe(1.01);
  });

  it("缺基准 / 无持仓的行同时从分子分母剔除", () => {
    const withMissing = sumDayPnl([
      { price: 101, prevClose: 100, quantity: 1000 }, // +1000
      { price: 999, prevClose: null, quantity: 1000 }, // 缺基准：不得以 0 参与
      { price: 1.1, prevClose: 1.0, quantity: 0 } // 无持仓：不参与
    ]);
    expect(withMissing).toEqual({ value: 1000, ratio: 1 });
  });

  it("今日估算缺行情的行（price=null）整组剔除，不稀释成「没涨没跌」", () => {
    expect(
      sumDayPnl([
        { price: null, prevClose: 100, quantity: 10 }, // 未开实时 → 今日估算无值
        { price: 110, prevClose: 100, quantity: 10 } // 有行情 +10%
      ])
    ).toEqual({ value: 100, ratio: 10 });
  });

  it("一条都算不出 → 两项 null（不是 0）", () => {
    expect(sumDayPnl([])).toEqual({ value: null, ratio: null });
    expect(sumDayPnl([{ price: 1.1, prevClose: null, quantity: 10 }])).toEqual({
      value: null,
      ratio: null
    });
    // 未开实时时汇总条「今日估算」就是这一形态 → 整块不渲染
    expect(sumDayPnl([{ price: null, prevClose: null, quantity: 10 }])).toEqual(
      { value: null, ratio: null }
    );
  });
});

describe("列定义：今日估算 / 昨日盈亏 两列常驻，各带各的口径", () => {
  it("day_pnl 改名为「今日估算」，派生 todayEstimate，默认可见", () => {
    const def = colDef("day_pnl");
    expect(def.label).toBe("今日估算");
    expect(def.renderer).toBe("moneyRatio");
    expect(def.derived).toBe("todayEstimate");
    expect(def.scope).toBe("mixed");
    expect(def.defaultHidden).toBeFalsy();
  });

  it("新增 yesterday_pnl「昨日盈亏」，派生 yesterdayPnl，默认可见", () => {
    const def = colDef("yesterday_pnl");
    expect(def.label).toBe("昨日盈亏");
    expect(def.renderer).toBe("moneyRatio");
    expect(def.derived).toBe("yesterdayPnl");
    expect(def.scope).toBe("mixed");
    expect(def.defaultHidden).toBeFalsy();
  });

  it("命名不撞车：两列 label 不同，且都不再叫「当日盈亏」", () => {
    const today = colDef("day_pnl").label;
    const yesterday = colDef("yesterday_pnl").label;
    expect(today).not.toBe(yesterday);
    for (const label of [today, yesterday]) {
      expect(label).not.toContain("当日盈亏");
    }
    expect(today).toContain("估算"); // 「估算」二字必须出现在列名里
    expect(yesterday).toContain("昨日");
  });

  it("两列等宽（104），与降为可选的 created_at 等宽", () => {
    expect(colDef("created_at").defaultHidden).toBe(true);
    expect(colDef("day_pnl").minWidth).toBe(104);
    expect(colDef("yesterday_pnl").minWidth).toBe(104);
    expect(colDef("day_pnl").minWidth).toBe(colDef("created_at").minWidth);
    expect(colDef("yesterday_pnl").minWidth).toBe(
      colDef("created_at").minWidth
    );
  });

  it("两列都覆盖指数（无持仓 → 金额 `—`，涨跌幅成立）", () => {
    // #2641 删掉「今日涨跌幅」独立列后，指数行的涨跌全靠这两列，故必须留在 appliesTo。
    const quoteTypes = [
      "stock",
      "etf",
      "fund",
      "money_fund",
      "bond",
      "crypto",
      "reverse_repo",
      "index"
    ];
    expect(colDef("day_pnl").appliesTo).toEqual(quoteTypes);
    expect(colDef("yesterday_pnl").appliesTo).toEqual(quoteTypes);
  });

  it("两列都默认降序优先 + 两档循环 + 口径徽标常驻", () => {
    for (const key of ["day_pnl", "yesterday_pnl"]) {
      const def = colDef(key);
      expect(def.sortOrders).toEqual(["descending", "ascending"]);
      expect(def.sortMetrics).toEqual({
        labels: { amount: "金额", ratio: "涨幅" }
      });
    }
  });
});

describe("列定义：两列都走客户端整组排序，不再靠后端代理", () => {
  it("「今日涨跌幅」独立列已不存在（#2641）", () => {
    expect(watchlistColumnDefs.some(d => d.key === "change_pct")).toBe(false);
  });

  it("两列都可排序，但**都不设** sortBy：后端只有上一交易日收盘", () => {
    for (const key of ["day_pnl", "yesterday_pnl"]) {
      const def = colDef(key);
      expect(def.sortable).toBe("custom");
      // 反例守卫：#2641 曾写 sortBy: "change_pct"，于是「按金额排序」在实现上不存在，
      // 且实时开启时只排当前页（跨页顺序乱）。现在两列都走客户端整组（clientSort.ts）。
      expect(def.sortBy).toBeUndefined();
      expect(def.sortMetrics?.ratioSortBy).toBeUndefined();
      // 派生值由 derived 链路取，不走 realtimeField 覆盖（后者只服务 money renderer）
      expect(def.realtimeField).toBeUndefined();
    }
    expect(colDef("day_pnl").derived).toBe("todayEstimate");
    expect(colDef("yesterday_pnl").derived).toBe("yesterdayPnl");
  });
});

describe("toEastmoneySecid：内部代码 → 东财 secid", () => {
  it("有 market 时直接映射（1=沪 / 0=深）", () => {
    expect(toEastmoneySecid("600519", "SH")).toBe("1.600519");
    expect(toEastmoneySecid("000001", "SZ")).toBe("0.000001");
    // 带前缀的代码也能认（去掉 SH/SZ 再判）
    expect(toEastmoneySecid("SH600519", "SH")).toBe("1.600519");
  });

  it("缺 market 时按代码段兜底", () => {
    expect(toEastmoneySecid("600519")).toBe("1.600519"); // 沪A
    expect(toEastmoneySecid("000001")).toBe("0.000001"); // 深A
    expect(toEastmoneySecid("510300")).toBe("1.510300"); // 沪基金
    expect(toEastmoneySecid("159915")).toBe("0.159915"); // 深基金
    expect(toEastmoneySecid("110000")).toBe("1.110000"); // 沪可转债
  });

  it("非 6 位数字码返回 null（经理 / 组合行没有分时）", () => {
    expect(toEastmoneySecid("")).toBeNull();
    expect(toEastmoneySecid("ABC")).toBeNull();
  });
});
