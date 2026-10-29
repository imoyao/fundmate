import type { WatchlistItem } from "@/api/watchlist";
import type { AdvisorAdjustItem } from "@/api/funds";
import { advisorOpTone, advisorRatioText } from "@/utils/advisorAdjust";

/** 非交易实体（组合 / 经理）：不展示代码、不展示「持有」区 */
export const COMPOSITE_TYPES = new Set(["manager", "portfolio"]);
/** 不可持有品类：与 columnDefs.TRADABLE_TYPES 互补 */
export const NON_HOLDABLE_TYPES = new Set(["index", "manager", "portfolio"]);

export function normalizeAssetType(t?: string | null): string {
  return (t || "").toLowerCase();
}

export function isCompositeType(t?: string | null): boolean {
  return COMPOSITE_TYPES.has(normalizeAssetType(t));
}

export function isHoldableType(t?: string | null): boolean {
  return !NON_HOLDABLE_TYPES.has(normalizeAssetType(t));
}

/** 投顾组合：额外展示策展元数据与策略简介（#1468） */
export function isPortfolioType(t?: string | null): boolean {
  return normalizeAssetType(t) === "portfolio";
}

/** 且慢平台的调仓靠持仓快照推导，空态要额外说明（不是故障） */
export function isQiemanPlatform(platform?: string | null): boolean {
  return (platform || "").toUpperCase() === "QIEMAN";
}

/** 组合净值 + 净值日期，合并成「1.2345（截至 2026-09-11）」 */
export function navTextOf(
  nav: number | null | undefined,
  date?: string | null
): string {
  if (nav == null) return "";
  const d = date;
  return d ? `${nav.toFixed(4)}（截至 ${d}）` : nav.toFixed(4);
}

/** 只放行 http(s)：外部站点 url 直接插 href 有注入风险 */
export function safeHttpUrl(raw?: string | null): string {
  if (!raw) return "";
  try {
    const u = new URL(raw);
    return u.protocol === "http:" || u.protocol === "https:" ? raw : "";
  } catch {
    return "";
  }
}

/** 组合类标的的分层信息（平台 · 主理人 · 策略；经理为所属公司） */
export function compositeMetaOf(
  item: WatchlistItem | null,
  assetType?: string | null
): string {
  if (!item) return "";
  if (isPortfolioType(assetType)) {
    return [
      item.advisor_platform,
      item.advisor_host,
      item.advisor_strategy_type
    ]
      .filter(Boolean)
      .join(" · ");
  }
  if (normalizeAssetType(assetType) === "manager") {
    return item.manager_company || "";
  }
  return "";
}

export function groupTextOf(names?: string[] | null): string {
  const list = names ?? [];
  return list.length ? list.join("、") : "—";
}

/** tag_ids → 名称；查不到的 id 直接丢掉（标签被删时不应显示空白项） */
export function tagTextOf(
  ids: number[] | null | undefined,
  allTags?: { id: number; name: string; color?: string | null }[] | null
): string {
  const names = (ids ?? [])
    .map(id => allTags?.find(t => t.id === id)?.name)
    .filter((n): n is string => !!n);
  return names.length ? names.join("、") : "—";
}

/**
 * 加仓/减仓用涨跌语义色，新增/持平/建仓用中性色（不是「行情」，别误导）。
 * 方向判定与比例文案收口在 `@/utils/advisorAdjust`（#2740：详情页持仓区块也要用同一口径），
 * 这里只负责映射成本抽屉自己的类名。
 */
export function opClassOf(op: string | null): string {
  const tone = advisorOpTone(op);
  if (tone === "add") return "wqv-op wqv-op--add";
  if (tone === "cut") return "wqv-op wqv-op--cut";
  return "wqv-op";
}

/** 调仓比例：只有一侧有值时也要说清是哪一侧（「→ —」而不是空） */
export function ratioTextOf(it: AdvisorAdjustItem): string {
  return advisorRatioText(it);
}

/** 有行情价才算「最新价」（0 是脏值，与缺失同处理） */
export function hasPriceOf(item: WatchlistItem | null): boolean {
  return item?.current_price != null && item.current_price !== 0;
}

export function hasChangeOf(item: WatchlistItem | null): boolean {
  return item?.change_pct != null;
}

/** http 拦截器可能已拆信封也可能没拆（仓库里两种写法并存），这里都兜住 */
export function unwrap<T>(res: unknown): T | null {
  if (!res) return null;
  const r = res as { data?: unknown };
  return ((r.data ?? res) as T) ?? null;
}
