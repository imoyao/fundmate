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

/** 能画 K 线所需的最少 OHLCV 根数：1 根画不出形态（与 `isCandle` 判据同源，只此一处） */
const MIN_OHLC_FOR_CANDLE = 2;

/**
 * 是否提供视图切换：**有 OHLCV 才谈得上「K 线」**。
 * 场外基金 / 指数只有一条序列，给切换器是假选择。
 */
export function showViewToggle(ohlcLength: number): boolean {
  return ohlcLength >= MIN_OHLC_FOR_CANDLE;
}

/**
 * 当前**实际**是不是在画 K 线。
 *
 * 这是「有 K 线能力」与「选了 K 线视图」的合取，也是所有视图相关判定的唯一入口——
 * 组件里任何需要「现在画的是什么」的地方都必须走它，不要自己再拼一次
 * `isCandle && view === 'candle'`（拼漏一处就是叠不上去的叠加层，见 `overlayAvailable`）。
 */
export function effectiveUseCandle(
  ohlcLength: number,
  view: TrendView
): boolean {
  return showViewToggle(ohlcLength) && view === "candle";
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

/**
 * 买卖点 / 成本线叠加层是否可用：**只有真的在画 K 线时才不可用**
 * （K 线是未复权价 + cross tooltip + 双 grid，属另一套坐标语义，见文件头）。
 *
 * ## ⚠️ 判据必须是「实际在画什么」，不能是「切换器选中了什么」(#2453)
 *
 * 参数是 `useCandle`（当前是否正在画 K 线），**不是** `TrendView`。两者的区别在场外基金上
 * 会炸：场外没有 OHLCV → 切换器不渲染（`showViewToggle` 为 false）→ 而视图状态的初值是
 * `'candle'` → 按选中值判得到「画的是折线，叠加层却判定不可用」。
 *
 * 后果是**勾选框可见、买卖点永远不画**（勾选框走 `hasMarkers`，不含这条判定）。
 * 一个不可见的切换器，它的选中值没有任何语义，不能拿来做判据。
 */
export function overlayAvailable(useCandle: boolean): boolean {
  return !useCandle;
}
