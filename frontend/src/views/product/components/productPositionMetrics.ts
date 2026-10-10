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
  /**
   * 当日盈亏（元，#2007）；**整组都没有基准价时为 null**（不是 0）。
   * 只累计「有基准」的行——把没有当日数据的行算成 0，等于替它宣布「今天没涨没跌」。
   */
  dayPnl: number | null;
  /**
   * 当日盈亏的基准金额（元）= Σ(上一确认价 × 数量)，**只累计有基准的行**。
   * 分母必须与分子的口径一致，否则率会算在一个不存在的基数上。
   */
  dayBase: number;
  /**
   * 基准日（`YYYY-MM-DD`）：组内**最新**的一个 `price_date`，用于告诉用户这个
   * 「当日」到底是哪一天（场外基金是 T-1 净值、场内是最近收盘日，两者不总是今天）。
   * 整组都没有基准时为 null。
   */
  dayBasisDate: string | null;
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
  let dayPnl: number | null = null;
  let dayBase = 0;
  let dayBasisDate: string | null = null;

  for (const row of groupRows) {
    const q = row.quantity || 0;
    quantity += q;
    // 成本用「单价 × 数量」自算，不信后端可能缺的派生字段
    cost += (row.avg_price || 0) * q;
    marketValue += row.market_value ?? 0;
    pnl += row.pnl ?? 0;

    // 当日盈亏（#2007）：**只累计有基准价的行**。没有基准的行既不能进分子、也不能进分母
    // ——把它按 0 计入，等于替它宣布「今天没涨没跌」，那正是这张卡要消灭的假数据。
    if (row.day_pnl != null && row.prev_close != null) {
      dayPnl = (dayPnl ?? 0) + row.day_pnl;
      dayBase += row.prev_close * q;
    }
    const basisDate = row.price_date ?? null;
    if (
      basisDate != null &&
      (dayBasisDate === null || basisDate > dayBasisDate)
    ) {
      // ISO 日期串字典序即时间序，取最新的那一天作为「当日」的锚点
      dayBasisDate = basisDate;
    }

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
    holdingDays: minDays,
    dayPnl,
    dayBase,
    dayBasisDate: dayPnl == null ? null : dayBasisDate
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

/**
 * 当日盈亏率，**返回百分数**（与 `pnlRate` 同单位），**无基准时返回 null**。
 *
 * 与 `pnlRate` 的一处刻意不同：`pnlRate` 无成本时退化 0（那是「没有收益率可算」的
 * 零值显示），而当日盈亏的 0 会被读成**事实判断**「今天没涨没跌」。所以这里返回
 * null，让调用方显式降级「—」——展示层不替用户下结论。
 */
export function dayPnlRate(
  totals: Pick<ChannelTotals, "dayPnl" | "dayBase">
): number | null {
  if (totals.dayPnl == null || !totals.dayBase) return null;
  return (totals.dayPnl / totals.dayBase) * 100;
}

/** 持仓天数的展示文本；后端没给该字段时给占位，不显示成「0 天」 */
export function daysText(days: number | null): string {
  return days == null ? "—" : `${days} 天`;
}
