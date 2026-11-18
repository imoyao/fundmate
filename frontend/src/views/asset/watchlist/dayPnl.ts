/**
 * 自选页盈亏口径（2026-11-05 拆列：#2640 的「当日盈亏」一分为二）。
 *
 * 抽成纯模块而不是内联进 composable / renderer：
 * 「分子减的是谁」这件事只有一处能定义，表格列与顶部汇总条必须共用同一份，
 * 否则两处各写一遍 `(price - prev) * qty` 迟早算出两个数（#980 拆出来的一贯做法）。
 *
 * ## 为什么必须拆成两套口径
 *
 * 后端 `compute_latest_quote` 取 `price_history` 最近**两根已确认价**，而回填止于 T-1
 * （#824：T 日不回填）。于是自选行里：
 *
 * | 字段 | 实际是哪天 | 来源 |
 * |---|---|---|
 * | `row.current_price` | **T-1**（昨天）已确认收盘价 / 确认净值 | `close`，最近一根 |
 * | `row.prev_close` | **T-2**（前天）已确认价 | `prev_close`，第二根 |
 * | `quote.currentPrice` | **T**（今天盘中）实时价 / 估算净值 `gsz` | 天天 / 腾讯行情 |
 * | `quote.prevClose` | **T-1**（昨天）昨收 / 昨净值 `dwjz` | 实时源自带 |
 *
 * 旧实现把「T-1 − T-2」叫「当日盈亏」，盘中显示的是**昨天的真实值**；开了实时后又把
 * 「T − T-2」混在一起（实时价配后端 `prev_close`），等于多算一天。两个都要修：
 *
 * - **当日盈亏（真实值优先、估值兜底）** = `(T 价 − T-1 已确认价) × 份额`，
 *   T 价取「今天的真实值」：股票盘后=收盘价、基金净值公布后=官方净值（`NAV`/`dwjz`）；
 *   拿不到真实值就用盘中估值价（股票实时价 / 基金估算净值 `GSZ`）填充，并挂「估」徽章。
 *   只在 `quote.source === "realtime"` 时成立，盘中随轮询跳动；拿不到实时行情一律
 *   `null`（渲染 `—`），**绝不回落昨日数字**，且基准恒为 `row.current_price`（T-1）。
 * - **昨日盈亏（confirmed）** = `(T-1 确认价 − T-2 确认价) × 份额`，
 *   是已确认的**真实值**，与实时通道是否开启无关，永不跳动。
 *
 * ## 基准（分母）必须同源同日
 *
 * 实时源不提供昨收时（腾讯基金格式等），基准回落 `row.current_price`（T-1 已确认价）——
 * **不能**回落 `row.prev_close`（T-2）：那会拿今天的价格去减前天的价格。
 * 这也是 `valuationEngine.ts` 删掉「实时源缺 prevClose → 补静态 prev_close」的原因：
 * 静态的 `prev_close` 是 T-2，实时链路里补它就是把两个不同日子接在一起。
 *
 * ⚠️ 两侧 `prev_close` 都是**未复权**口径，除权除息日「昨日盈亏」会虚报（分红那天
 * 看上去像暴跌）。这是既有口径，不在本模块单独修，修它要动 `price_history` 的取数口径。
 *
 * ## 为什么不能拿现价顶替缺失的昨收
 *
 * 探市页就是这么写的（`useExploreWatchlist.ts`：`prevClose = quote?.prevClose ?? price`），
 * 于是 `(price - price) * qty` **恒等于 0**，而列看起来完全正常——这类「假 0」比空白更贵，
 * 因为它会让人相信「今天没赚没亏」。所以缺失一律返回 `null`，由展示层降级 `—`。
 */
import { roundToCents } from "@/utils/currency";

export interface DayPnlInput {
  /** 期末价点（今日估算＝实时估值价；昨日盈亏＝T-1 确认价） */
  price?: number | null;
  /** 基准价点（今日估算＝T-1 确认价；昨日盈亏＝T-2 确认价） */
  prevClose?: number | null;
  /** 持仓数量；<=0 表示没有持仓 → 金额不成立（涨跌幅仍然成立） */
  quantity?: number | null;
}

export interface DayPnlResult {
  /** 盈亏（元）；null = 算不出（无价 / 无基准 / 无持仓） */
  value: number | null;
  /** 涨跌幅（%）；null = 算不出（无价 / 无基准） */
  ratio: number | null;
  /**
   * 这一行「当日盈亏」的确认态：
   * - `confirmed` = 用的是今天已确认价（股票收盘价 / 基金已公布净值），不挂「估」；
   * - `estimated` = 用的是盘中估值（股票实时价 / 基金估算净值 GSZ），挂「估」；
   * - null = 算不出（无实时行情 / 无基准），单元格渲染 `—`。
   */
  status: "confirmed" | "estimated" | null;
}

// ── 排序口径已上提到 `sortMetric.ts`（2026-10-30 二次优化）──
// 「金额 / 比例」不是盈亏列的私有概念：持仓市值（金额 / 占比）与持仓收益
// （金额 / 收益率）同样是复合列，共用 `SortMetric` 与 `pickSortMetric`。

/** 行里参与盈亏计算的字段（`WatchlistItem` 的子集，便于单测直接构造） */
export interface DayPnlRow {
  symbol?: string | null;
  /** T-1：最近一根已确认收盘价 / 确认净值 */
  current_price?: number | null;
  /** T-2：上一根已确认价（后端 `compute_latest_quote` 的第二根） */
  prev_close?: number | null;
  holding_quantity?: number | null;
}

/**
 * 实时估值项的相关字段（`ValuationItem` 的子集）。
 *
 * `source` 必须一起传：引擎在行情不可达时会回退后端静态价，那份值就是
 * **T-1 已确认价**，把它当成今日估值只会得到「今日 = 昨日」的假象（同 #1104 守卫）。
 *
 * `prevClose` 在实时链路里是**实时源自带的 T-1 基准**（腾讯 `parts[4]` 昨收 /
 * 天天 `dwjz` 昨净值 / 批量 `NAV`）；它和后端的 `prev_close`（T-2）**同名不同日**，
 * 切勿互换。
 */
export interface DayPnlQuote {
  currentPrice?: number;
  prevClose?: number | null;
  source?: "realtime" | "static";
  /** 官方确认价（基金已公布净值）；股票为 null（确认价即收盘实时价本身） */
  officialPrice?: number | null;
  /** 这份实时报价是否已确认（收盘 / 官方净值已公布） */
  confirmed?: boolean;
}

function positive(v: number | null | undefined): number | null {
  return typeof v === "number" && isFinite(v) && v > 0 ? v : null;
}

/** 纯计算：有价 + 有基准才有涨跌幅；再有持仓数量才有金额。
 * 确认态由调用方按口径填入（`computeDayPnl` 本身不感知 confirmed/estimated）。 */
export function computeDayPnl(input: DayPnlInput): DayPnlResult {
  const price = positive(input.price);
  const prev = positive(input.prevClose);
  if (price == null || prev == null)
    return { value: null, ratio: null, status: null };

  const ratio = Math.round(((price - prev) / prev) * 100 * 100) / 100;
  const quantity = positive(input.quantity);
  if (quantity == null) return { value: null, ratio, status: null };
  return {
    value: roundToCents((price - prev) * quantity),
    ratio,
    status: null
  };
}

// ── 口径 A：昨日盈亏（已确认，T-1 vs T-2）──

/**
 * 行 → 「昨日盈亏」的输入。**完全不读实时行情**：这一列是已确认的真实值，
 * 开关、轮询、盘中休市都不该让它变化。
 *
 * 单独导出是因为汇总条要的是「输入」而不是「结果」——它必须拿到
 * `prevClose × quantity` 自己去加权（见 `sumDayPnl`），不能用逐行结果反算。
 */
export function resolveYesterdayPnlInput(row: DayPnlRow): DayPnlInput {
  return {
    price: row.current_price ?? null,
    prevClose: row.prev_close ?? null,
    quantity: row.holding_quantity ?? null
  };
}

/** 行 → 「昨日盈亏」（表格列用）。已确认真实值，status 恒为 "confirmed"。 */
export function resolveYesterdayPnl(row: DayPnlRow): DayPnlResult {
  return {
    ...computeDayPnl(resolveYesterdayPnlInput(row)),
    status: "confirmed"
  };
}

// ── 口径 B：当日盈亏（真实值优先、估值兜底，T vs T-1）──

/**
 * 行 → 「当日盈亏」的输入。两条硬规则，任何一条被绕过都会把昨天的数冒充今天：
 *
 * 1. **只有 `source === "realtime"` 且拿到正价才成立**。引擎回退静态价时
 *    `currentPrice` 就是 T-1 确认价，拿它当 T 会算出「今日 = 0」；此时整组返回 `null`。
 * 2. **基准恒为 `row.current_price`（T-1 已确认价）**，绝不兜底 `row.prev_close`（T-2）。
 *    且**绝不拿 `quote.prevClose` 当基准**——基金 `NAV`/`dwjz` 在净值公布后已是 T 日值，
 *    当基准会算成 `0`（见下方 `estimatedPrice`/`officialPrice` 的选择）。
 *
 * 期末价（price）的取舍（真实值优先、估值兜底）：
 * - 确认态（`quote.confirmed`）：股票用收盘实时价本身、基金用已公布官方净值
 *   `officialPrice`（`NAV`/`dwjz`）；官方价缺失时保守回落估值价。
 * - 估值态：用盘中估值价（股票实时价 / 基金 `GSZ`）。
 *
 * 拿不到实时行情时返回 `price: null / prevClose: null`，展示层渲染 `—`：
 * 宁可空白，也不能用昨日盈亏把这一列填满。
 */
export function resolveTodayEstimateInput(
  row: DayPnlRow,
  quote?: DayPnlQuote
): DayPnlInput {
  const live =
    quote && quote.source === "realtime" ? positive(quote.currentPrice) : null;
  if (live == null) {
    return {
      price: null,
      prevClose: null,
      quantity: row.holding_quantity ?? null
    };
  }
  // 真实值优先：确认态用 officialPrice（基金已公布净值 / 股票无官方价则回落现价），
  // 否则用盘中估值价。两者都减 T-1 已确认价（row.current_price）。
  const price = quote?.confirmed
    ? (positive(quote?.officialPrice) ?? live)
    : live;
  const prev = positive(row.current_price);
  return {
    price,
    prevClose: prev,
    quantity: row.holding_quantity ?? null
  };
}

/** 行 → 「当日盈亏」（表格列用），附带确认态供「估」徽章决策 */
export function resolveTodayEstimate(
  row: DayPnlRow,
  quote?: DayPnlQuote
): DayPnlResult {
  const input = resolveTodayEstimateInput(row, quote);
  const result = computeDayPnl(input);
  const live =
    quote && quote.source === "realtime" ? positive(quote.currentPrice) : null;
  let status: "confirmed" | "estimated" | null = null;
  if (live != null && (result.value != null || result.ratio != null)) {
    status = quote?.confirmed ? "confirmed" : "estimated";
  }
  return { ...result, status };
}

export interface DayPnlSummary {
  /** 盈亏合计（元）；一条都算不出 → null（不是 0） */
  value: number | null;
  /** 涨跌幅合计(%) = ΣΔ / Σ基准市值；分母为 0 → null */
  ratio: number | null;
  /**
   * 汇总确认态：混入任一估值行 → `estimated`（挂「估」）；
   * 全部为已确认真实值 → `confirmed`（隐藏徽章）；无有效行 → null。
   */
  status: "confirmed" | "estimated" | null;
}

/**
 * 汇总条口径（两列共用）：金额按行累加，比例用**基准市值加权**（Σ(基准×份额) 作分母）。
 *
 * 为什么不用「各行涨跌幅的算术平均」：一元钱的仓和一百万的仓涨幅相同，
 * 对账户的影响差五个数量级，算术平均会给出一个谁都不是的数。
 *
 * 无基准 / 无持仓的行**同时从分子分母剔除**：让它以 0 参与分子会把「缺数据」
 * 稀释成「没涨没跌」。
 */
/**
 * 汇总入口：每行带各自的确认态（`status`）。
 * 混入任一估值行 → 汇总挂「估」；全部为已确认真实值 → 隐藏徽章；无有效行 → null。
 */
export interface DayPnlEntry {
  input: DayPnlInput;
  status?: "confirmed" | "estimated" | null;
}

export function sumDayPnl(entries: DayPnlEntry[]): DayPnlSummary {
  let amount = 0;
  let base = 0;
  let anyValid = false;
  let anyEstimated = false;
  for (const e of entries) {
    const price = positive(e.input.price);
    const prev = positive(e.input.prevClose);
    const quantity = positive(e.input.quantity);
    if (price == null || prev == null || quantity == null) continue;
    anyValid = true;
    amount += (price - prev) * quantity;
    base += prev * quantity;
    // 仅当行被明确标记为「已确认」才不挂「估」；estimated / null / 缺省一律按
    // 估值处理（保守口径：宁可标「估」，也不把不确定的值当成确认值而隐藏徽章）。
    if (e.status !== "confirmed") anyEstimated = true;
  }
  if (base <= 0 || !anyValid) return { value: null, ratio: null, status: null };
  // 任一估值行混入即按估值呈现（保守口径）；全确认才隐藏徽章
  const status = anyEstimated ? "estimated" : "confirmed";
  return {
    value: roundToCents(amount),
    ratio: Math.round((amount / base) * 100 * 100) / 100,
    status
  };
}
