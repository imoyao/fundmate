// src/views/asset/__tests__/breakEven.spec.ts
/**
 * 「回本需涨」派生单测（2026-11-27）。
 *
 * 重点不是算对一次，而是钉住三条边界：盈利不回本、市值 0 不算、缺价不算——
 * 这三种都不能回 0（0% 的含义是「刚好回到原点」，会被读成「不用涨」）。
 */
import { describe, expect, it } from "vitest";
import type { Position } from "@/api/types";
import { breakEvenGainPct, buildBreakEven, toBreakEvenRow } from "../breakEven";

const pos = (over: Partial<Position> = {}): Position =>
  ({
    id: 1,
    symbol: "SH600027",
    name: "华电国际",
    account_name: "账户A",
    quantity: 1000,
    avg_price: 1.1,
    current_price: 1.0,
    market_value: 1000,
    pnl: -100,
    ...over
  }) as Position;

describe("breakEvenGainPct", () => {
  it("浮亏：要涨的钱 ÷ 当前市值（不是 ÷ 成本）", () => {
    // 成本 1100、现值 1000 ⇒ 要涨 100/1000 = 10%（÷成本会得 9.09%，那是「已跌多少」）
    expect(breakEvenGainPct(-100, 1000)).toBe(10);
  });

  it("深亏不对称：−50% 要涨 100%", () => {
    expect(breakEvenGainPct(-500, 500)).toBe(100);
  });

  it("盈利 / 不亏 / 无市值 / 缺值一律 null（不是 0）", () => {
    expect(breakEvenGainPct(100, 1000)).toBeNull();
    expect(breakEvenGainPct(0, 1000)).toBeNull();
    expect(breakEvenGainPct(-100, 0)).toBeNull();
    expect(breakEvenGainPct(null, 1000)).toBeNull();
    expect(breakEvenGainPct(-100, undefined)).toBeNull();
    expect(breakEvenGainPct(Number.NaN, 1000)).toBeNull();
  });
});

describe("toBreakEvenRow", () => {
  it("浮亏持仓成行，带 key / 名称 / 回本需涨", () => {
    const row = toBreakEvenRow(pos());
    expect(row).toEqual({
      key: "1",
      name: "华电国际",
      symbol: "SH600027",
      pnl: -100,
      marketValue: 1000,
      gainPct: 10
    });
  });

  it("盈利持仓不成行（返回 null，由调用方过滤）", () => {
    expect(toBreakEvenRow(pos({ pnl: 50 }))).toBeNull();
  });

  it("名称为空时退回 symbol，不留空标题", () => {
    expect(toBreakEvenRow(pos({ name: null }))?.name).toBe("SH600027");
  });
});

describe("buildBreakEven", () => {
  it("只统计浮亏标的，按浮亏额降序（钱最多的坑在前）", () => {
    const { rows, summary } = buildBreakEven([
      pos({ id: 1, name: "小亏", pnl: -20, market_value: 980 }),
      pos({ id: 2, name: "大亏", pnl: -3000, market_value: 7000 }),
      pos({ id: 3, name: "盈利", pnl: 500, market_value: 1500 }),
      pos({ id: 4, name: "中亏", pnl: -200, market_value: 1800 })
    ]);
    expect(rows.map(r => r.name)).toEqual(["大亏", "中亏", "小亏"]);
    expect(summary.lossCount).toBe(3);
    expect(summary.totalLoss).toBe(3220);
    expect(summary.totalMarketValue).toBe(9780);
    // 加权（3220 / 9780），不是各标的百分比的简单平均
    expect(summary.overallGainPct).toBe(32.92);
  });

  it("无浮亏：空行 + 汇总归零，overallGainPct 为 null（不是 0%）", () => {
    const { rows, summary } = buildBreakEven([
      pos({ id: 1, pnl: 100 }),
      pos({ id: 2, pnl: 0 })
    ]);
    expect(rows).toEqual([]);
    expect(summary.lossCount).toBe(0);
    expect(summary.totalLoss).toBe(0);
    expect(summary.overallGainPct).toBeNull();
  });

  it("空列表不炸", () => {
    expect(buildBreakEven([]).summary.lossCount).toBe(0);
  });
});
