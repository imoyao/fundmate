/**
 * 自选页「当日盈亏」口径（#2640）。
 *
 * ## 这个文件钉什么
 *
 * 1. **缺昨收给 null，不给 0**——这是本次最核心的判据。给 0 的写法
 *    （`prevClose ?? price`）算出来**恒等于 0**，而列看起来完全正常，
 *    比空白贵得多：它让人相信「今天没赚没亏」（探市页就这么错过，见 dayPnl.ts 头部）。
 * 2. **零持仓时金额不成立、涨跌幅仍成立**——自选里大量标的只是「看着」，
 *    它们的当日涨跌幅有意义，当日赚了多少钱没有。
 * 3. **汇总比例是市值加权，不是算术平均**——一元仓与百万仓同涨幅，对账户的影响
 *    差五个数量级；算术平均会给出一个谁都不是的数。
 * 4. **缺数据的行同时从分子分母剔除**——让它以 0 参与分子，等于把「缺数据」
 *    稀释成「没涨没跌」。
 * 5. **列定义**：当日盈亏默认可见，且与降为可选的 `created_at` 等宽（进一出一）。
 * 6. **排序能力不随列删除而丢失**（#2641）：「今日涨跌幅」独立列已删，排序由当日盈亏列
 *    代理到后端 `change_pct`；口径是**涨跌幅而非金额**（两者顺序不同，见列定义注释）。
 * 7. **指数行仍有涨跌幅**：指数无持仓 → 金额 `—`，但百分比成立，故它必须留在
 *    `appliesTo` 里——否则删列后指数行连涨跌都看不到。
 *
 * ⚠️ 为什么测纯模块而不是直接调渲染器：vitest 环境是 node（无 DOM），
 * `columnRenderers.tsx` 会一路 import `.vue` 组件（见 `bondFormats.spec.ts` 的说明）。
 */
import { describe, expect, it } from "vitest";

import {
  computeDayPnl,
  resolveDayPnl,
  resolveDayPnlInput,
  sumDayPnl
} from "../dayPnl";
import { watchlistColumnDefs } from "../columnDefs";
import { toEastmoneySecid } from "@/utils/realtimeDataSources";

function colDef(key: string) {
  const def = watchlistColumnDefs.find(d => d.key === key);
  if (!def) throw new Error(`${key} 列定义缺失`);
  return def;
}

describe("computeDayPnl：有价 + 有昨收才算得出来", () => {
  it("正常情形：金额按持仓数量、比例按昨收", () => {
    expect(
      computeDayPnl({ price: 1.1, prevClose: 1.0, quantity: 1000 })
    ).toEqual({ value: 100, ratio: 10 });
  });

  it("缺昨收 → 两项都是 null（不是 0）", () => {
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

describe("resolveDayPnl：价格实时优先，昨收可跨源", () => {
  const row = {
    symbol: "600519",
    current_price: 100,
    prev_close: 98,
    holding_quantity: 10
  };

  it("实时行情可用时用实时价", () => {
    expect(
      resolveDayPnl(row, {
        currentPrice: 110,
        prevClose: 98,
        source: "realtime"
      })
    ).toEqual({ value: 120, ratio: 12.24 });
  });

  it("实时源标记 static（引擎回退后端静态价）时不当作实时价", () => {
    // static 的 currentPrice 就是后端那一份，用它覆盖 row.current_price 只会原地踏步；
    // 这里显式给一个不同的值，确认它**没有**被采用
    expect(
      resolveDayPnl(row, {
        currentPrice: 999,
        prevClose: null,
        source: "static"
      })
    ).toEqual({ value: 20, ratio: 2.04 });
  });

  it("实时价 + 实时源缺昨收 → 回落后端昨收（腾讯基金格式即此）", () => {
    expect(
      resolveDayPnlInput(row, { currentPrice: 110, source: "realtime" })
    ).toEqual({ price: 110, prevClose: 98, quantity: 10 });
  });

  it("无行情、无昨收 → null 而非拿现价顶替", () => {
    expect(
      resolveDayPnl({ symbol: "x", current_price: 100, prev_close: null })
    ).toEqual({ value: null, ratio: null });
  });
});

describe("sumDayPnl：比例按昨日市值加权", () => {
  it("大仓小涨 + 小仓暴涨 → 接近大仓的涨幅（算术平均会得到中间值）", () => {
    const summary = sumDayPnl([
      { price: 101, prevClose: 100, quantity: 100000 }, // +1%，昨日市值 10,000,000
      { price: 110, prevClose: 100, quantity: 100 } // +10%，昨日市值 10,000
    ]);
    expect(summary.value).toBe(101000);
    // (100000 + 1000) / 10010000 ≈ 1.0090%，算术平均则是 5.5%
    expect(summary.ratio).toBe(1.01);
  });

  it("缺昨收 / 无持仓的行同时从分子分母剔除", () => {
    const withMissing = sumDayPnl([
      { price: 101, prevClose: 100, quantity: 1000 }, // +1000
      { price: 999, prevClose: null, quantity: 1000 }, // 缺昨收：不得以 0 参与
      { price: 1.1, prevClose: 1.0, quantity: 0 } // 无持仓：不参与
    ]);
    expect(withMissing).toEqual({ value: 1000, ratio: 1 });
  });

  it("一条都算不出 → 两项 null（不是 0）", () => {
    expect(sumDayPnl([])).toEqual({ value: null, ratio: null });
    expect(sumDayPnl([{ price: 1.1, prevClose: null, quantity: 10 }])).toEqual({
      value: null,
      ratio: null
    });
  });
});

describe("列定义：当日盈亏默认可见，且与添加自选日等宽交换", () => {
  it("当日盈亏列存在、走派生渲染、默认可见", () => {
    const def = colDef("day_pnl");
    expect(def.renderer).toBe("moneyRatio");
    expect(def.derived).toBe("dayPnl");
    expect(def.scope).toBe("mixed");
    expect(def.defaultHidden).toBeFalsy();
  });

  it("添加自选日降为可选列（腾出宽度）", () => {
    expect(colDef("created_at").defaultHidden).toBe(true);
  });

  it("进一出一等量：两列 minWidth 相同", () => {
    // 铁律 1「加一列必须减等量」。用「两列等宽」而不是硬写总宽做判据：
    // 总宽会随趋势列等历史问题变动，钉死它只会制造假红。
    expect(colDef("day_pnl").minWidth).toBe(colDef("created_at").minWidth);
  });

  it("当日盈亏只对「有行情」的品类出现，且**包含指数**（无持仓 → 只有百分比）", () => {
    // 指数不可买，但有点位与昨收：金额渲染 `—`、涨跌幅成立。
    // #2641 删掉「今日涨跌幅」独立列后，指数行的涨跌全靠这一列，故必须留在 appliesTo。
    expect(colDef("day_pnl").appliesTo).toEqual([
      "stock",
      "etf",
      "fund",
      "money_fund",
      "bond",
      "crypto",
      "reverse_repo",
      "index"
    ]);
  });
});

describe("列定义：删掉「今日涨跌幅」列后，排序能力仍在（#2641）", () => {
  it("独立列已不存在（它的百分比行并入当日盈亏）", () => {
    expect(watchlistColumnDefs.some(d => d.key === "change_pct")).toBe(false);
  });

  it("当日盈亏可排序，并把 sort_by 代理到后端既有白名单字段 change_pct", () => {
    const def = colDef("day_pnl");
    expect(def.sortable).toBe("custom");
    expect(def.sortBy).toBe("change_pct");
    // 实时路径要按实时涨跌幅排（客户端、仅当前页），故也带 realtimeField
    expect(def.realtimeField).toBe("changePct");
  });

  it("代理字段必须是可交易的「行字段」，不是派生列 key", () => {
    // 反例守卫：写成 sortBy: "day_pnl" 会让后端按不存在的列静默失效——
    // 这正是 #1331「标了 sortable 却查不到白名单」的形态。
    const def = colDef("day_pnl");
    expect(def.sortBy).not.toBe(def.key);
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
