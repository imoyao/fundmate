import { batchFetchQuotes } from "./realtimeDataSources";

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

// 静态兜底数据（由外部注入，可以从后端已加载的数据中获取）
export interface StaticPriceProvider {
  (symbol: string): { currentPrice?: number; changePct?: number } | undefined;
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
    let source: "realtime" | "static" = "static";

    if (quote && quote.currentPrice > 0) {
      currentPrice = quote.currentPrice;
      changePct = quote.changePct;
      source = "realtime";
      hasRealtime = true;
      if (!lastUpdateTime) lastUpdateTime = quote.updateTime;
    } else {
      // 降级：使用后端静态数据
      const staticData = staticPriceProvider(h.symbol);
      currentPrice = staticData?.currentPrice ?? 0;
      changePct = staticData?.changePct ?? 0;
    }

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
      pnlPercent
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
