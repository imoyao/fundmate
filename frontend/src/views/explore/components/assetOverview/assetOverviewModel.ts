// 大类资产观察区块的展示口径（#1436 / #1444 / #1545 / #1546 收口）。
// 这里只放纯函数：颜色令牌映射、异动扁平化、计数派生——都不依赖响应式，
// 因而可以直接用单测钉住口径，不必挂载组件。
import { ASSET_CATEGORY_TOKEN } from "@/constants/market";
import type { MarketAnomaly, MarketAsset, MarketGroup } from "@/api/market";

/** 命中异动的资产（扁平化后供区块底部「异动解读」渲染） */
export interface AnomalyAsset {
  asset: MarketAsset;
  anomaly: MarketAnomaly;
}

/** 分类色点：未知分类退到次级文字色，不编造颜色 */
export function categoryColor(category: string): string {
  return ASSET_CATEGORY_TOKEN[category] || "var(--text-secondary)";
}

// 相对位置分位 → 温度三色（偏低绿 / 适中沙 / 偏高红）
// #1545 拆两族：游标等「图形 / 实色」用 --temp-*；
// 标签文字必须用 --temp-*-ink（实色作文字对比度不足，白底仅 1.68–3.96:1）。
export function positionColor(asset: MarketAsset): string {
  const label = asset.position?.label;
  if (label === "偏低") return "var(--temp-low)";
  if (label === "偏高") return "var(--temp-high)";
  return "var(--temp-mid)";
}

export function positionLabelColor(asset: MarketAsset): string {
  const label = asset.position?.label;
  if (label === "偏低") return "var(--temp-low-ink)";
  if (label === "偏高") return "var(--temp-high-ink)";
  return "var(--temp-mid-ink)";
}

/** 收益率变动(bp) 用中性色，不套用涨红跌绿（§3.4 纪律） */
export function yieldTone(_bp?: number): string {
  return "var(--text-secondary)";
}

/** 把 6 组资产拍平，只留带异动的（anomaly 为 null 的直接丢弃） */
export function flattenAnomalies(groups: MarketGroup[]): AnomalyAsset[] {
  return groups
    .flatMap(group => group.assets)
    .map(asset => ({ asset, anomaly: asset.anomaly }))
    .filter((x): x is AnomalyAsset => x.anomaly !== null);
}

/** 已加载数据时的分组标的数；未加载返回 null（折叠态就不显示数字，避免编造） */
export function groupCountOf(
  groups: MarketGroup[],
  category: string
): number | null {
  const group = groups.find(g => g.category === category);
  return group ? group.assets.length : null;
}

/** 已加载的标的总数；尚未加载时回退到区块标称的 20 个，仅用于按钮文案 */
export function loadedAssetCountOf(groups: MarketGroup[]): number {
  const total = groups.reduce((n, g) => n + g.assets.length, 0);
  return total > 0 ? total : 20;
}

/** 折叠摘要里的计数文案：有数据才给「N 个标的」，否则返回 null 不渲染 */
export function collapsedCountText(
  groups: MarketGroup[],
  category: string
): string | null {
  const n = groupCountOf(groups, category);
  return n === null ? null : `${n} 个标的`;
}
