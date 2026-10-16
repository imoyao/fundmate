// frontend/src/views/product/components/trendViewMetrics.ts
/**
 * 走势卡「视图」口径（#2171 后续）：场内提供 K 线与折线两个视图。
 *
 * ## 为什么场内要给折线视图
 *
 * 买卖点与成本线是「元/份」「元/股」的日序列，只能叠在**折线**上（与净值 / 收盘价同轴）。
 * K 线视图是未复权价 + `cross` tooltip + 双 grid（量能副图），叠加属另一套坐标语义 ——
 * 所以「场内也想看买卖点」的正解**不是往 K 线上硬叠**，而是给场内一个折线视图：
 * 复用同一套叠加层与成本线口径，不新写坐标。
 *
 * 场外基金只有净值一条线，**不给**视图切换：只有一个选项的切换器是假选择。
 */

export type TrendView = "candle" | "line";

export interface TrendViewOption {
  label: string;
  value: TrendView;
}

/** 切换器选项；**K 线在前**（场内默认视图，保证既有观感不变） */
export const TREND_VIEW_OPTIONS: TrendViewOption[] = [
  { label: "K线", value: "candle" },
  { label: "折线", value: "line" }
];

/**
 * 是否提供视图切换：**有 OHLCV 才谈得上「K 线」**（取 ≥2 根——1 根画不出形态，
 * 与 `isCandle` 的判据一致）。场外基金 / 指数只有一条序列，给切换器是假选择。
 */
export function showViewToggle(ohlcLength: number): boolean {
  return ohlcLength >= 2;
}

/**
 * 成交量副图只在 **K 线视图**渲染。
 *
 * 折线视图里它没有读法（读者没有「阳线阴线」这个概念），留着只会让图多一个空网格。
 * 「有量能数据」与「当前视图该不该显示量能」是两件事，必须分开判——把它们合成一个
 * 条件，就会出现「切到折线后剩一个空格子」这种半吊子状态。
 */
export function showVolumeSeries(
  view: TrendView,
  hasAnyVolume: boolean
): boolean {
  return view === "candle" && hasAnyVolume;
}

/** 买卖点 / 成本线叠加层只在**折线视图**可用（K 线视图属另一套坐标语义，见文件头） */
export function overlayAvailable(view: TrendView): boolean {
  return view === "line";
}
