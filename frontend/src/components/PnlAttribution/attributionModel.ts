/**
 * PnlAttribution 的纯计算（#980 从 `index.vue` 抽出）。
 *
 * 这里只做**展示层的型变换**：载荷 → 行、行的贡献条宽度归一。
 * 盈亏本身一律由后端算（`services/pnl_calendar.py: compute_range_attribution`），
 * 前端**不二次计算、不对账**——`Σ positions[].pnl ≡ 同窗 pnl-calendar 的 month_total`
 * 是后端构造保证的。
 *
 * 区间不再由本模块定义（#3107）：档位与「档位 → 日期」的换算统一在
 * `utils/chartRange.ts`，与组合页「超额走势」「资金流动」共用一份，
 * 避免同一个「近1年」在三处落在不同起点。本模块只剩「空态该说哪句话」这类纯展示派生
 * ——它必须能单测，所以仍留在 `.vue` 之外。
 */

import type { PnlAttributionPayload } from "@/api/summary";

export type Dimension = "position" | "category";

/** 归因维度（SegmentedControl 入参）；品种 ⇄ 大类是纯前端切换 */
export const DIMENSION_OPTIONS: ReadonlyArray<{
  label: string;
  value: Dimension;
}> = [
  { label: "品种", value: "position" },
  { label: "大类", value: "category" }
];

/** 视图行：品种行与大类行统一成同一种形态，列表与贡献条只认这个 */
export type ViewRow = {
  key: string;
  name: string;
  sub: string;
  pnl: number;
  pct: number | null;
};

/**
 * 载荷 + 维度 → 视图行。两种维度在各行文案上的差异集中在这一处：
 * 大类行说明「由几只组成」，品种行说明「代码 · 类型」。
 *
 * `assetTypeLabel` **必须由调用方传入**，不在本模块 import：
 * `useEnumLabels` 一路牵到 `utils/http → router`，模块级 import 会让这支纯函数的单测
 * 连带上整棵运行时依赖（实测报 supabase 环境变量缺失），纯函数也就不纯了。
 */
export function buildRows(
  payload: PnlAttributionPayload | null,
  dimension: Dimension,
  assetTypeLabel: (type: string | undefined | null) => string
): ViewRow[] {
  if (!payload) return [];
  if (dimension === "category") {
    return payload.categories.map(c => ({
      key: c.asset_type,
      name: assetTypeLabel(c.asset_type),
      sub: `${c.positions_count} 只`,
      pnl: c.pnl,
      pct: c.pct
    }));
  }
  return payload.positions.map(r => ({
    key: String(r.position_id),
    name: r.name || r.symbol,
    sub: r.asset_type
      ? `${r.symbol} · ${assetTypeLabel(r.asset_type)}`
      : r.symbol,
    pnl: r.pnl,
    pct: r.pct
  }));
}

/** 贡献条的分母：当前视图内最大 |pnl|（纯视觉，不影响数值展示） */
export function computeMaxAbs(rows: ViewRow[]): number {
  return rows.reduce((m, r) => Math.max(m, Math.abs(r.pnl)), 0);
}

/** 贡献条宽度：按最大 |pnl| 归一；全零时全部 0%（不留一条满格假条） */
export function barWidthFor(pnl: number, maxAbs: number): string {
  if (maxAbs <= 0) return "0%";
  return `${(Math.abs(pnl) / maxAbs) * 100}%`;
}

/** 标题旁的 ⓘ：把「这个数是哪一段」和「为什么不等于逐日相加」说清楚 */
export function sectionInfoFor(payload: PnlAttributionPayload | null): string {
  return (
    "选定区间内各持仓对总盈亏的贡献拆解" +
    (payload ? `（${payload.start_date} ~ ${payload.end_date}）` : "") +
    "；逐品种贡献之和与区间合计一致，已实现盈亏含在对应品种内。"
  );
}

/**
 * 列表为空时说哪句话。
 *
 * 两句必须分开：`has_any_computable=false` 是**整窗算不了**（没有可算日），
 * 而「没有可归因的持仓」是**这个区间确实没有持仓贡献**。混成一句会把
 * 「数据不足」说成「你没持仓」，用户会去翻持仓而不是去补数据。
 */
export function emptyTextFor(payload: PnlAttributionPayload | null): string {
  return payload && !payload.has_any_computable
    ? "数据不足，无法计算区间贡献"
    : "区间内没有可归因的持仓";
}
