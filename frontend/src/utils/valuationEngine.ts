import { batchFetchQuotes } from "./realtimeDataSources";
import { isConfirmedQuote } from "./quoteStatus";

export interface Holding {
  symbol: string;
  type: "stock" | "fund";
  quantity: number;
  costPrice: number;
}

export interface ValuationItem extends Holding {
  currentPrice: number;
  changePct: number;
  updateTime: string;
  source: "realtime" | "static";
  marketValue: number;
  pnl: number;
  pnlPercent: number;
  /**
   * **实时链路的 T-1 基准**（腾讯 `parts[4]` 昨收 / 天天 `dwjz` 昨净值 /
   * 批量 `NAV`），只由 `source === "realtime"` 的分支产出；静态回退分支恒为 null。
   *
   * ⚠️ 它与后端 `row.prev_close` **同名不同日**：后者是 T-2（后端 `close` 本身
   * 才是 T-1，见 #824「T 日不回填」）。早期实现会在实时源缺基准时用静态
   * `prev_close` 补位，把「今天的实时价 − 前天的价」当成今日盈亏，
   * 2026-11-05「今日估算 / 昨日盈亏」拆列时删除。
   *
   * 因此「当日盈亏」只消费 `source === "realtime"` 的这一份；实时源缺值时由
   * `dayPnl.ts` 兜底 `row.current_price`（T-1 已确认价），与实时价同源同日。
   *
   * `null` = 该来源没给；展示层降级 `—`，不要用 `currentPrice` 顶替
   * （那会把盈亏算成恒 0，#2640 修的就是这个）。
   */
  prevClose: number | null;
  /**
   * 这份实时报价是否已是「今日确认价」（收盘 / 官方净值已公布）。
   * 由 `quoteStatus.isConfirmedQuote` 按数据源自带日期/时刻判定，不靠本地时钟。
   * `source === "static"`（引擎回退）恒为 false（那是 T-1 已确认价，不是今天的）。
   */
  confirmed?: boolean;
  /** 官方确认价：基金=已公布单位净值（NAV/dwjz）；股票=无（null）。仅 confirmed 时有意义。 */
  officialPrice?: number | null;
}

export interface ValuationSummary {
  totalMarketValue: number;
  totalCost: number;
  totalPnl: number;
  totalPnlPercent: number;
  updateTime: string;
  source: "realtime" | "static";
}

export interface ValuationResult {
  items: ValuationItem[];
  summary: ValuationSummary | null;
}

/**
 * 静态兜底数据（由外部注入，可以从后端已加载的数据中获取）。
 *
 * ⚠️ `prevClose` 只应在调用方能给出**T-1 昨收**时填写。后端 `prev_close` 是 T-2，
 * 不要把它塞进这里——自选页已因此不再传该字段（2026-11-05）。
 */
export interface StaticPriceProvider {
  (
    symbol: string
  ):
    | { currentPrice?: number; changePct?: number; prevClose?: number | null }
    | undefined;
}

export async function calculateHoldingsValuation(
  holdings: Holding[],
  staticPriceProvider: StaticPriceProvider
): Promise<ValuationResult> {
  // 1. 批量获取实时行情
  const codes = holdings.map(h => ({ symbol: h.symbol, type: h.type }));
  const quoteMap = await batchFetchQuotes(codes);

  const items: ValuationItem[] = [];
  let totalMarketValue = 0;
  let totalCost = 0;
  let hasRealtime = false;
  let lastUpdateTime = "";

  for (const h of holdings) {
    const quote = quoteMap.get(h.symbol);
    let currentPrice: number;
    let changePct: number;
    let prevClose: number | null = null;
    let source: "realtime" | "static" = "static";

    let quoteConfirmed = false;
    let quoteOfficial: number | null = null;
    if (quote && quote.currentPrice > 0) {
      currentPrice = quote.currentPrice;
      changePct = quote.changePct;
      // 只认实时源自带的 T-1 基准；缺失就留 null（下一步也不补）
      prevClose = quote.prevClose ?? null;
      source = "realtime";
      hasRealtime = true;
      if (!lastUpdateTime) lastUpdateTime = quote.updateTime;
      // 确认态：按数据源自带日期/时刻判定「今日收盘价 / 官方净值已定」
      quoteConfirmed = isConfirmedQuote({
        type: h.type,
        priceDate: quote.priceDate ?? null,
        priceTime: quote.priceTime ?? null
      });
      quoteOfficial = quote.officialPrice ?? null;
    } else {
      // 降级：使用后端静态数据（T-1 已确认价）
      const staticData = staticPriceProvider(h.symbol);
      currentPrice = staticData?.currentPrice ?? 0;
      changePct = staticData?.changePct ?? 0;
      prevClose = staticData?.prevClose ?? null;
    }

    // ⚠️ 不要在实时源缺 prevClose 时用静态 prevClose 补位（2026-11-05 拆列时删除）。
    // 注入的 staticPriceProvider.prevClose 曾是后端 `prev_close`（T-2），而实时
    // currentPrice 是今天（T）——补进去等于「今天减前天」，多算一天。
    // 缺基准一律留 null：由 `dayPnl.ts` 兜底 `row.current_price`（T-1 已确认价），
    // 展示层在完全算不出时降级 `—`。宁可空白，也不能拿两个不同日子的价相减。
    //
    // 非正数基准没有意义（0 会算出 Infinity），一律降到 null。
    if (prevClose != null && !(prevClose > 0)) prevClose = null;

    const marketValue = currentPrice * h.quantity;
    const cost = h.costPrice * h.quantity;
    const pnl = marketValue - cost;
    const pnlPercent = cost > 0 ? (pnl / cost) * 100 : 0;

    totalMarketValue += marketValue;
    totalCost += cost;

    items.push({
      ...h,
      currentPrice,
      changePct,
      updateTime: quote?.updateTime || "",
      source,
      marketValue,
      pnl,
      pnlPercent,
      prevClose,
      confirmed: source === "realtime" ? quoteConfirmed : false,
      officialPrice: source === "realtime" ? quoteOfficial : null
    });
  }

  const totalPnl = totalMarketValue - totalCost;
  const totalPnlPercent = totalCost > 0 ? (totalPnl / totalCost) * 100 : 0;

  const summary: ValuationSummary | null =
    items.length > 0
      ? {
          totalMarketValue,
          totalCost,
          totalPnl,
          totalPnlPercent,
          updateTime: lastUpdateTime,
          source: hasRealtime ? "realtime" : "static"
        }
      : null;
  // 在 return items 之前，对浮点数做四舍五入
  items.forEach(item => {
    item.pnl = Math.round(item.pnl * 100) / 100;
    item.pnlPercent = Math.round(item.pnlPercent * 100) / 100;
    item.marketValue = Math.round(item.marketValue * 100) / 100;
  });
  // 汇总也处理一下
  summary.totalPnl = Math.round(totalPnl * 100) / 100;
  summary.totalPnlPercent = Math.round(totalPnlPercent * 100) / 100;
  summary.totalMarketValue = Math.round(totalMarketValue * 100) / 100;
  summary.totalCost = Math.round(totalCost * 100) / 100;
  return { items, summary };
}
