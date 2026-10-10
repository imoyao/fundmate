// frontend/src/views/product/components/productPositionMetrics.ts
/**
 * 「我的持仓」区块的纯计算（#2005）。
 *
 * 从 SFC 里抽出来，是为了能被 vitest 钉住——下面那条 100× 教训，正是「算错却
 * 没人拦得住」的代价。
 *
 * ## 回归锚点：盈亏率必须是百分数，不是比值
 *
 * 旧实现 `pnlRatio = pnl / cost` 得到的是**比值**（例如 -0.2243），却被直接交给
 * 默认 `suffix="%"` 的 `RiseFallText`，于是屏上显示 `-0.22%`，而真值是 `-22.43%`
 * —— 小了整整 100 倍。更麻烦的是**颜色是对的**（负数走跌色），肉眼几乎发现不了：
 * 一个亏了 22% 的持仓被显示成「只亏了 0.22%」，用户不会去质疑一个看起来很温和的数。
 *
 * 故口径统一在这里 ×100 收口，展示层只负责拼 `%`，不再自己做单位换算。
 */
import type { Position } from "@/api/types";

/** 一个渠道（账户）内所有持仓行的合计口径 —— 单账户网格与多账户表格共用 */
export interface ChannelTotals {
  /** 持有份额 */
  quantity: number;
  /** 持有金额（市值） */
  marketValue: number;
  /** 持有盈亏 */
  pnl: number;
  /** 持仓成本 = Σ(单价 × 数量) */
  cost: number;
  /** 加权单位成本；无数量时退化为 0 */
  avgPrice: number;
  /** 最短持仓天数（最早建仓那笔）；整组都没有该字段时为 null */
  holdingDays: number | null;
}

/**
 * 把同一渠道下的多笔持仓加总成一组口径。
 *
 * `holding_days` 取**最短**而非平均：「这个账户拿了多久」的自然是第一笔，
 * 平均值会把后来补仓的天数摊进来，得到一个谁也不代表的数。
 */
export function sumUp(groupRows: Position[]): ChannelTotals {
  let quantity = 0;
  let marketValue = 0;
  let pnl = 0;
  let cost = 0;
  let minDays: number | null = null;

  for (const row of groupRows) {
    const q = row.quantity || 0;
    quantity += q;
    // 成本用「单价 × 数量」自算，不信后端可能缺的派生字段
    cost += (row.avg_price || 0) * q;
    marketValue += row.market_value ?? 0;
    pnl += row.pnl ?? 0;

    const days = row.holding_days ?? null;
    if (days != null && (minDays === null || days < minDays)) {
      minDays = days;
    }
  }

  return {
    quantity,
    marketValue,
    pnl,
    cost,
    avgPrice: quantity ? cost / quantity : 0,
    holdingDays: minDays
  };
}

/**
 * 持有盈亏率，**返回百分数**（-22.43 表示 -22.43%），不是比值。
 *
 * 成本为 0 时退化为 0：让 RiseFallText 走零值灰显示，既不显示 Infinity
 * 也不靠正负号去猜一个不存在的收益率。
 */
export function pnlRate(totals: Pick<ChannelTotals, "cost" | "pnl">): number {
  return totals.cost ? (totals.pnl / totals.cost) * 100 : 0;
}

/** 持仓天数的展示文本；后端没给该字段时给占位，不显示成「0 天」 */
export function daysText(days: number | null): string {
  return days == null ? "—" : `${days} 天`;
}
