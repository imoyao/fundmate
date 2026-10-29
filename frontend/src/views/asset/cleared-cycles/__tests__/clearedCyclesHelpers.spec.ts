// src/views/asset/cleared-cycles/__tests__/clearedCyclesHelpers.spec.ts
/**
 * 清仓周期复盘（#2131）展示助手单测。
 *
 * 覆盖纪律：null = 不可算 → "--"（**禁止画 0**）；部分配对周期不进汇总样本时
 * 样本说明必须显式降级。数值计算不在此层（后端唯一口径）。
 */
import { describe, expect, it } from "vitest";
import {
  cycleRowKey,
  fmtHoldingDays,
  fmtHoldingDaysValue,
  fmtRatio,
  pnlTotalCaption,
  sampleNote
} from "../helpers";
import type { ClearedCycle, ClearedCyclesSummary } from "@/api/summary";

const emptySummary: ClearedCyclesSummary = {
  cycle_count: 0,
  sample_count: 0,
  win_count: 0,
  loss_count: 0,
  win_rate: null,
  profit_loss_ratio: null,
  avg_holding_days: null,
  realized_pnl_total: null,
  total_trade_count: 0,
  caveats: []
};

const cycle = (over: Partial<ClearedCycle> = {}): ClearedCycle => ({
  symbol: "000001",
  name: "华夏成长",
  cycle_number: 1,
  first_buy_date: "2026-01-01",
  last_sell_date: "2026-02-01",
  buy_count: 1,
  sell_count: 1,
  trade_count: 2,
  total_buy_amount: 1000,
  total_sell_amount: 1050,
  realized_pnl: 50,
  pnl_pct: 5,
  avg_holding_days: 31,
  dividend_total: null,
  pnl_known: true,
  caveats: [],
  ...over
});

describe("fmtRatio", () => {
  it("null/undefined → '--'（不可算不是 0）", () => {
    expect(fmtRatio(null)).toBe("--");
    expect(fmtRatio(undefined)).toBe("--");
  });

  it("0 是合法样本值，画 0.00 而非占位", () => {
    expect(fmtRatio(0)).toBe("0.00");
    expect(fmtRatio(66.666)).toBe("66.67");
  });
});

describe("fmtHoldingDays", () => {
  it("null → '--'；有值带单位", () => {
    expect(fmtHoldingDays(null)).toBe("--");
    expect(fmtHoldingDays(365)).toBe("365 天");
  });

  it("小数天取整：后端份额加权平均会带一位小数，展示不保留", () => {
    // 真机数据（2026-10-29 复盘页）：109.1 / 27.9 / 39.6 / 89.5 / 120.3
    expect(fmtHoldingDays(109.1)).toBe("109 天");
    expect(fmtHoldingDays(27.9)).toBe("28 天");
    expect(fmtHoldingDays(39.6)).toBe("40 天");
    expect(fmtHoldingDays(120.3)).toBe("120 天");
  });

  it(".5 天向上取整（half-up），不能用 Python round 的银行家舍入口径", () => {
    // Python round(89.5) == 88，会出现「89.5 天显示 88 天」的诡异结果；
    // 取整放在展示层（Math.round）即天然 half-up。
    expect(fmtHoldingDays(89.5)).toBe("90 天");
    expect(fmtHoldingDays(546.5)).toBe("547 天");
  });

  it("0 天是合法值（当日买卖），画 0 而非占位", () => {
    expect(fmtHoldingDays(0)).toBe("0 天");
  });
});

describe("fmtHoldingDaysValue", () => {
  it("汇总卡不要单位：返回整数，null 透传", () => {
    expect(fmtHoldingDaysValue(null)).toBeNull();
    expect(fmtHoldingDaysValue(undefined)).toBeNull();
    expect(fmtHoldingDaysValue(132.7)).toBe(133);
    expect(fmtHoldingDaysValue(31)).toBe(31);
  });
});

describe("cycleRowKey", () => {
  it("同标的多轮周期键不冲突", () => {
    const a = cycleRowKey(cycle({ cycle_number: 1 }));
    const b = cycleRowKey(cycle({ cycle_number: 2 }));
    expect(a).toBe("000001#1");
    expect(b).toBe("000001#2");
    expect(a).not.toBe(b);
  });
});

describe("sampleNote", () => {
  it("无周期：引导文案", () => {
    expect(sampleNote(emptySummary)).toBe("录入卖出流水后自动归档");
  });

  it("全部可算：说明样本量", () => {
    expect(
      sampleNote({ ...emptySummary, cycle_count: 3, sample_count: 3 })
    ).toBe("基于 3 个已完结周期");
  });

  it("部分配对：显式降级说明", () => {
    expect(
      sampleNote({ ...emptySummary, cycle_count: 4, sample_count: 3 })
    ).toBe("基于 3/4 个周期（部分配对周期不可算，未计入）");
  });
});

describe("pnlTotalCaption", () => {
  it("无样本不显示笔数（避免误导成「赚了 0」）", () => {
    expect(pnlTotalCaption(emptySummary)).toBe("暂无可算周期");
  });

  it("有样本显示交易总笔数", () => {
    expect(
      pnlTotalCaption({
        ...emptySummary,
        sample_count: 2,
        total_trade_count: 7
      })
    ).toBe("共 7 笔交易");
  });
});
