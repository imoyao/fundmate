/**
 * 「我的持仓」区块的计算口径（#2005）。
 *
 * 缺陷背景（实测本机真实库）：旧组件 `pnlRatio = pnl / cost` 算出的是**比值**，
 * 却被直接交给默认 `suffix="%"` 的 `RiseFallText`。于是一笔亏 22.43% 的持仓
 * （中泰化学 SZ002092：成本 8140.02 / 盈亏 -1826.02）在屏上显示成 `-0.22%`。
 *
 * 为什么值得单独立锚点：**颜色是对的**。负数走跌绿，用户看到的是一个「颜色正常、
 * 数值温和」的收益率，没有任何线索提示它小了 100 倍——这类错不会被肉眼发现，
 * 只能被断言拦住。
 */
import { describe, it, expect } from "vitest";
import {
  sumUp,
  pnlRate,
  dayPnlRate,
  daysText
} from "../productPositionMetrics";
import type { Position } from "@/api/types";

/** 本机真实持仓的最小构造；只填计算用到的字段，其余给占位 */
const position = (over: Partial<Position>): Position =>
  ({
    id: 1,
    symbol: "SZ002092",
    name: "中泰化学",
    market: "CN_A",
    type: "stock",
    account_name: "同花顺——银河",
    currency: "CNY",
    current_price: 0,
    trade_date: "2026-05-12",
    notes: null,
    created_at: "2026-05-12T00:00:00",
    updated_at: "2026-05-12T00:00:00",
    quantity: 0,
    avg_price: 0,
    ...over
  }) as Position;

describe("pnlRate：盈亏率口径", () => {
  it("返回百分数而非比值 —— 旧实现小了 100 倍（#2005 回归锚点）", () => {
    // 真实数据：中泰化学 SZ002092
    const t = sumUp([
      position({
        quantity: 1400,
        avg_price: 5.8143,
        market_value: 6314,
        pnl: -1826.02
      })
    ]);

    expect(t.cost).toBeCloseTo(8140.02, 2);
    // 真值 -22.43%；旧实现会给出 -0.2243，配上 "%" 后显示成 -0.22%
    expect(pnlRate(t)).toBeCloseTo(-22.43, 2);
    expect(pnlRate(t)).not.toBeCloseTo(-0.2243, 4);
  });

  it("盈利方向同样是百分数", () => {
    // 真实数据：023456 示例现金添利，成本 50000 / 盈亏 510 → 1.02%
    const t = sumUp([
      position({
        quantity: 50000,
        avg_price: 1,
        market_value: 50510,
        pnl: 510
      })
    ]);
    expect(pnlRate(t)).toBeCloseTo(1.02, 2);
  });

  it("成本为 0 → 退化为 0，不产生 Infinity / NaN", () => {
    expect(pnlRate({ cost: 0, pnl: 100 })).toBe(0);
    expect(pnlRate({ cost: 0, pnl: -100 })).toBe(0);
    expect(pnlRate({ cost: 0, pnl: 0 })).toBe(0);
  });

  it("盈亏为 0 → 0（RiseFallText 走零值灰，不显示假涨假跌）", () => {
    expect(pnlRate({ cost: 1234.56, pnl: 0 })).toBe(0);
  });
});

describe("sumUp：同渠道多笔加总", () => {
  it("单笔：各口径与该笔一致", () => {
    const t = sumUp([
      position({
        quantity: 1400,
        avg_price: 5.8143,
        market_value: 6314,
        pnl: -1826.02,
        holding_days: 152
      })
    ]);
    expect(t.quantity).toBe(1400);
    expect(t.cost).toBeCloseTo(8140.02, 2);
    expect(t.marketValue).toBe(6314);
    expect(t.pnl).toBe(-1826.02);
    expect(t.avgPrice).toBeCloseTo(5.8143, 4);
    expect(t.holdingDays).toBe(152);
  });

  it("多笔：份额与金额相加，成本按 Σ(单价×数量)", () => {
    const t = sumUp([
      position({ quantity: 1000, avg_price: 2, market_value: 2400, pnl: 400 }),
      position({ quantity: 500, avg_price: 4, market_value: 1800, pnl: -200 })
    ]);
    expect(t.quantity).toBe(1500);
    expect(t.cost).toBe(1000 * 2 + 500 * 4); // 2000 + 2000 = 4000
    expect(t.marketValue).toBe(4200);
    expect(t.pnl).toBe(200);
  });

  it("avgPrice 是加权成本，不是各笔单价的算术平均", () => {
    // 1000×2 与 500×4：算术平均是 3，加权是 4000/1500 = 2.6667
    const t = sumUp([
      position({ quantity: 1000, avg_price: 2 }),
      position({ quantity: 500, avg_price: 4 })
    ]);
    expect(t.avgPrice).toBeCloseTo(2.6667, 4);
    expect(t.avgPrice).not.toBe(3);
  });

  it("持仓天数取最短（最早建仓），不做平均", () => {
    // 「这个账户拿了多久」= 第一笔；平均会把后来补仓的天数摊进来
    const t = sumUp([
      position({ quantity: 1, avg_price: 1, holding_days: 300 }),
      position({ quantity: 1, avg_price: 1, holding_days: 45 })
    ]);
    expect(t.holdingDays).toBe(45);
  });

  it("缺字段时不炸：null/undefined 一律按 0 参与运算", () => {
    const t = sumUp([
      position({
        quantity: 100,
        avg_price: 2,
        market_value: undefined,
        pnl: undefined,
        holding_days: undefined
      })
    ]);
    expect(t.cost).toBe(200);
    expect(t.marketValue).toBe(0);
    expect(t.pnl).toBe(0);
    expect(t.holdingDays).toBeNull();
  });

  it("空数组：全零且 holdingDays 为 null（不是 0，0 会被读成「今天建仓」）", () => {
    const t = sumUp([]);
    expect(t).toEqual({
      quantity: 0,
      marketValue: 0,
      pnl: 0,
      cost: 0,
      avgPrice: 0,
      holdingDays: null,
      // 当日盈亏（#2007）：无基准 → null（不是 0），基准金额为 0、基准日为 null
      dayPnl: null,
      dayBase: 0,
      dayBasisDate: null
    });
  });
});

describe("当日盈亏：只累计有基准的行（#2007）", () => {
  it("有基准：金额与率各自正确，率是百分数（显示 10% 而不是 0.1%）", () => {
    // 1000 份 × 上一确认价 1.00 元 → 基准金额 1000 元；当日涨了 100 元 → 10%
    const t = sumUp([
      position({
        quantity: 1000,
        prev_close: 1.0,
        day_pnl: 100,
        price_date: "2026-10-09"
      })
    ]);

    expect(t.dayPnl).toBe(100);
    expect(t.dayBase).toBeCloseTo(1000, 6);
    expect(dayPnlRate(t)).toBeCloseTo(10, 6);
    expect(t.dayBasisDate).toBe("2026-10-09");
  });

  it("**没有基准的行既不进分子也不进分母**（本卡的核心口径）", () => {
    // 若把无基准那行按 0 计入，会同时犯两个错：分子被摊薄、分母被撑大，
    // 出来的率比真值小——而屏幕上看不出任何异常
    const t = sumUp([
      position({ quantity: 1000, prev_close: 1.0, day_pnl: 100 }),
      position({ quantity: 5000, day_pnl: null, prev_close: null })
    ]);

    expect(t.dayPnl).toBe(100); // 不是 100 + 0 之外的东西，也不含无基准那行
    expect(t.dayBase).toBeCloseTo(1000, 6); // 5000 份没有基准 → 不进分母
    expect(dayPnlRate(t)).toBeCloseTo(10, 6);
  });

  it("全部没有基准 → dayPnl / 率 / 基准日都是 null，而不是 0", () => {
    const t = sumUp([
      position({ quantity: 1000, day_pnl: null, prev_close: null }),
      position({ quantity: 2000, day_pnl: null, prev_close: null })
    ]);

    expect(t.dayPnl).toBeNull();
    expect(t.dayBasisDate).toBeNull();
    // 0 会被读成「今天没涨没跌」——那是**结论**，我们没有依据下它
    expect(dayPnlRate(t)).toBeNull();
  });

  it("基准金额为 0 → 率给 null，不产生 Infinity", () => {
    expect(dayPnlRate({ dayPnl: 100, dayBase: 0 })).toBeNull();
    // 金额本身仍在：分母为零只是「率算不出来」，不影响我们知道今天赚了多少
    const t = sumUp([position({ quantity: 0, prev_close: 1.0, day_pnl: 100 })]);
    expect(t.dayPnl).toBe(100);
    expect(dayPnlRate(t)).toBeNull();
  });

  it("基准日取组内最新（ISO 串字典序即时间序）", () => {
    const t = sumUp([
      position({
        quantity: 1,
        prev_close: 1,
        day_pnl: 1,
        price_date: "2026-10-08"
      }),
      position({
        quantity: 1,
        prev_close: 1,
        day_pnl: 1,
        price_date: "2026-10-09"
      })
    ]);
    expect(t.dayBasisDate).toBe("2026-10-09");
  });

  it("有金额但缺 price_date → 基准日给 null，不编一个日期", () => {
    const t = sumUp([position({ quantity: 1, prev_close: 1, day_pnl: 1 })]);
    expect(t.dayPnl).toBe(1);
    expect(t.dayBasisDate).toBeNull();
  });
});

describe("daysText：持仓天数展示", () => {
  it("有值时带单位", () => {
    expect(daysText(59)).toBe("59 天");
    expect(daysText(0)).toBe("0 天");
  });

  it("无值时给占位，不显示成「0 天」", () => {
    expect(daysText(null)).toBe("—");
  });
});
