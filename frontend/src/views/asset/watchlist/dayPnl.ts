/**
 * 自选页「当日盈亏」口径（#2640）。
 *
 * 抽成纯模块而不是内联进 composable / renderer：
 * 「分母是谁」这件事只有一处能定义，表格列与顶部汇总条必须共用同一份，
 * 否则两处各写一遍 `(price - prev) * qty` 迟早算出两个数（#980 拆出来的一贯做法）。
 *
 * ## 口径
 *
 * - **当日盈亏（元）** = (现价 − 上一价点) × 持仓数量
 * - **当日涨跌幅（%）** = (现价 − 上一价点) / 上一价点 × 100
 *
 * 「上一价点」= 场内**上一交易日收盘价** / 场外基金**上一确认日单位净值**——
 * 与持仓页 #2007 的 `day_pnl` 同义，来源不同：那边读 `position_price` job 落在
 * `positions.prev_close` 的快照（只有**持仓**标的才有），这边用自选行后端下发的
 * `prev_close`（`compute_latest_quote` 由最近两根历史价算得，未持仓自选也有）。
 *
 * ⚠️ 与持仓页**同源同病**：两侧 `prev_close` 都是**未复权**口径，除权除息日
 * 「当日盈亏」会虚报（分红那天看上去像暴跌）。这是既有口径，不在本模块单独修，
 * 修它要动 `price_history` 的取数口径（影响面远大于自选页）。
 *
 * ## 为什么不能拿现价顶替缺失的昨收
 *
 * 探市页就是这么写的（`useExploreWatchlist.ts`：`prevClose = quote?.prevClose ?? price`），
 * 于是 `(price - price) * qty` **恒等于 0**，而列看起来完全正常——这类「假 0」比空白更贵，
 * 因为它会让人相信「今天没赚没亏」。（本次补齐了三个解析器对 `prevClose` 的下发，
 * 探市页因此恢复真实值；它自己那句 `?? price` 兜底与 `?? 0` 展示留给探市页单独处理。）
 * 所以缺失一律返回 `null`，由展示层降级 `—`。
 */
import { roundToCents } from "@/utils/currency";

export interface DayPnlInput {
  /** 现价（实时价优先，调用方负责挑） */
  price?: number | null;
  /** 上一价点：昨收 / 上一确认净值 */
  prevClose?: number | null;
  /** 持仓数量；<=0 表示没有持仓 → 金额不成立（涨跌幅仍然成立） */
  quantity?: number | null;
}

export interface DayPnlResult {
  /** 当日盈亏（元）；null = 算不出（无价 / 无昨收 / 无持仓） */
  value: number | null;
  /** 当日涨跌幅（%）；null = 算不出（无价 / 无昨收） */
  ratio: number | null;
}

/**
 * 「当日盈亏」列的排序口径（2026-10-30，用户反馈「盈亏率也要能排」）。
 *
 * 这一列是**复合列**：金额（主行）+ 涨跌幅（副行），两行是**两个不同的量**——
 * 同样涨 1%，一万仓与百万仓的当日盈亏差两个数量级。所以「今天谁赚得最多」与
 * 「今天谁涨得最凶」必须能各排各的，不能拿一个代理另一个（#2641 以前是代理到
 * `change_pct`，等于金额列永远排不出金额序）。
 */
export type DayPnlMetric = "amount" | "pct";

/** 按口径取列里的可比数（金额 / 涨跌幅）；用于表头排序，不参与渲染 */
export function pickDayPnlMetric(
  result: DayPnlResult,
  metric: DayPnlMetric
): number | null {
  return metric === "amount" ? result.value : result.ratio;
}

/** 行里参与当日盈亏的字段（`WatchlistItem` 的子集，便于单测直接构造） */
export interface DayPnlRow {
  symbol?: string | null;
  current_price?: number | null;
  prev_close?: number | null;
  holding_quantity?: number | null;
}

/**
 * 实时估值项的当日盈亏相关字段（`ValuationItem` 的子集）。
 *
 * `source` 必须一起传：引擎在行情不可达时会回退后端静态价，那份值就是
 * 「已确认」口径本身，把它当实时价只会得到两行一样的数（同 #1104 的守卫）。
 */
export interface DayPnlQuote {
  currentPrice?: number;
  prevClose?: number | null;
  source?: "realtime" | "static";
}

function positive(v: number | null | undefined): number | null {
  return typeof v === "number" && isFinite(v) && v > 0 ? v : null;
}

/** 纯计算：有价 + 有昨收才有涨跌幅；再有持仓数量才有金额 */
export function computeDayPnl(input: DayPnlInput): DayPnlResult {
  const price = positive(input.price);
  const prev = positive(input.prevClose);
  if (price == null || prev == null) return { value: null, ratio: null };

  const ratio = Math.round(((price - prev) / prev) * 100 * 100) / 100;
  const quantity = positive(input.quantity);
  if (quantity == null) return { value: null, ratio };
  return { value: roundToCents((price - prev) * quantity), ratio };
}

/**
 * 行 → 当日盈亏的**输入**（实时价优先，且必须真拿到行情；否则回落后端静态价）。
 *
 * 单独导出是因为汇总条要的是「输入」而不是「结果」——它必须拿到
 * `prevClose × quantity` 自己去加权（见 `sumDayPnl`），不能用逐行结果反算。
 *
 * 昨收的优先级与价格**不必同源**：腾讯基金格式不提供昨收，实时价 + 后端昨收
 * 是合法组合（两边都是「最近一个已确认交易日」，同日同口径）。
 */
export function resolveDayPnlInput(
  row: DayPnlRow,
  quote?: DayPnlQuote
): DayPnlInput {
  const realtimePrice =
    quote && quote.source === "realtime" ? positive(quote.currentPrice) : null;
  return {
    price: realtimePrice ?? row.current_price ?? null,
    prevClose: quote?.prevClose ?? row.prev_close ?? null,
    quantity: row.holding_quantity ?? null
  };
}

/** 行 → 当日盈亏（表格列用）：`resolveDayPnlInput` + `computeDayPnl` */
export function resolveDayPnl(
  row: DayPnlRow,
  quote?: DayPnlQuote
): DayPnlResult {
  return computeDayPnl(resolveDayPnlInput(row, quote));
}

export interface DayPnlSummary {
  /** 当日盈亏合计（元）；一条都算不出 → null（不是 0） */
  value: number | null;
  /** 当日涨跌幅合计(%) = ΣΔ / Σ昨收市值；分母为 0 → null */
  ratio: number | null;
}

/**
 * 汇总条口径：金额按行累加，比例用**昨日市值加权**（Σ(昨收×份额) 作分母）。
 *
 * 为什么不用「各行涨跌幅的算术平均」：一元钱的仓和一百万的仓涨幅相同，
 * 对账户的影响差五个数量级，算术平均会给出一个谁都不是的数。
 * 与 `productPositionMetrics.dayPnlRate`（持仓页）同口径。
 *
 * 无昨收 / 无持仓的行**同时从分子分母剔除**：让它以 0 参与分子会把「缺数据」
 * 稀释成「没涨没跌」。
 */
export function sumDayPnl(rows: DayPnlInput[]): DayPnlSummary {
  let amount = 0;
  let base = 0;
  for (const row of rows) {
    const price = positive(row.price);
    const prev = positive(row.prevClose);
    const quantity = positive(row.quantity);
    if (price == null || prev == null || quantity == null) continue;
    amount += (price - prev) * quantity;
    base += prev * quantity;
  }
  if (base <= 0) return { value: null, ratio: null };
  return {
    value: roundToCents(amount),
    ratio: Math.round((amount / base) * 100 * 100) / 100
  };
}
