/**
 * 「回本需涨」派生（复盘页浮亏区块，2026-11-27）。
 *
 * ## 这个数回答什么
 *
 * 「我亏着的这些，还要涨多少才回到成本」。收益率回答不了它：−20% 要涨 25% 才回本，
 * −50% 要涨 100% —— 亏损与回本不是对称的，越亏越陡，所以必须单独算、单独展示。
 *
 * ## 公式与为什么用市值做分母
 *
 * ```
 * 回本需涨 = (成本 − 市值) / 市值 = −浮亏 / 市值
 * ```
 *
 * 浮亏 = 市值 − 成本（后端 `positions.pnl` 就是这个口径），所以 −pnl 即「要补回来的钱」，
 * 除以**现值**才是「从现在起要涨的百分比」。用成本做分母算出来的是「已经跌了多少」，
 * 那是收益率，不是回本需涨 —— 两者在 −50% 处相差整整一倍。
 *
 * ## 边界（都回 null，不回 0）
 *
 * - `pnl >= 0`：不亏，无需回本 ⇒ null（不是 0% —— 0% 的含义是「刚好回到原点」）；
 * - `market_value <= 0`：没有市值可涨，百分比无意义 ⇒ null；
 * - 非有限数（后端取不到价时可能给 null）⇒ null。
 */

import type { Position } from "@/api/types";

/** 一行「浮亏待回本」的持仓 */
export type BreakEvenRow = {
  key: string;
  name: string;
  symbol: string;
  /** 浮亏额（元，负数） */
  pnl: number;
  /** 当前市值（元，正数） */
  marketValue: number;
  /** 回本需涨 %（正数）；null = 不可算（见文件头的边界） */
  gainPct: number | null;
};

/** 汇总：只统计**浮亏**标的，盈利标的混进来会把「整体要涨多少」稀释成假数 */
export type BreakEvenSummary = {
  /** 浮亏标的数 */
  lossCount: number;
  /** 合计浮亏（元，正数，表示「要补回来的钱」） */
  totalLoss: number;
  /** 这些标的的市值合计（元） */
  totalMarketValue: number;
  /** 整体回本需涨 %：合计浮亏 / 合计市值；无浮亏时为 null */
  overallGainPct: number | null;
};

/** 回本需涨 %（2 位小数）；不可算返回 null，语义见文件头 */
export function breakEvenGainPct(
  pnl: number | null | undefined,
  marketValue: number | null | undefined
): number | null {
  if (typeof pnl !== "number" || typeof marketValue !== "number") return null;
  if (!Number.isFinite(pnl) || !Number.isFinite(marketValue)) return null;
  if (pnl >= 0 || marketValue <= 0) return null;
  return Math.round((-pnl / marketValue) * 10000) / 100;
}

/** 单条持仓 → 待回本行；不浮亏 / 无市值返回 null（调用方 filter 掉） */
export function toBreakEvenRow(pos: Position): BreakEvenRow | null {
  const pnl = typeof pos.pnl === "number" ? pos.pnl : null;
  const marketValue =
    typeof pos.market_value === "number" ? pos.market_value : null;
  const gainPct = breakEvenGainPct(pnl, marketValue);
  if (pnl === null || marketValue === null || gainPct === null) return null;
  return {
    key: String(pos.id),
    name: pos.name || pos.symbol,
    symbol: pos.symbol,
    pnl,
    marketValue,
    gainPct
  };
}

/**
 * 持仓（可按账户分组的扁平结果）→ 待回本行 + 汇总。
 *
 * 排序按**浮亏额降序**（亏得最多在前）：用户要处理的是「钱最多的那个坑」，
 * 不是「百分比最惨的那个」——100 元亏 90% 与 10 万元亏 30%，后者才是问题。
 */
export function buildBreakEven(positions: readonly Position[]): {
  rows: BreakEvenRow[];
  summary: BreakEvenSummary;
} {
  const rows: BreakEvenRow[] = [];
  for (const pos of positions) {
    const row = toBreakEvenRow(pos);
    if (row) rows.push(row);
  }
  rows.sort((a, b) => a.pnl - b.pnl);

  let totalLoss = 0;
  let totalMarketValue = 0;
  for (const row of rows) {
    totalLoss += -row.pnl;
    totalMarketValue += row.marketValue;
  }

  return {
    rows,
    summary: {
      lossCount: rows.length,
      totalLoss: Math.round(totalLoss * 100) / 100,
      totalMarketValue: Math.round(totalMarketValue * 100) / 100,
      overallGainPct:
        totalMarketValue > 0
          ? Math.round((totalLoss / totalMarketValue) * 10000) / 100
          : null
    }
  };
}
