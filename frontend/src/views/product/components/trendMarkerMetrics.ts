// frontend/src/views/product/components/trendMarkerMetrics.ts
/**
 * 走势图买卖点的大小口径（#2171 §4.2「点大小规则」）。
 *
 * 从 SFC 里抽出来，是为了能被 vitest 钉住：这是一组**映射公式**（开方 + 上下限 +
 * 密度降档），算错了只会让点「看起来差不多」，肉眼几乎发现不了——正是纯函数该覆盖的形态。
 *
 * ## 规格（#2171 定稿，改动需同步改这里）
 *
 * - 金额权重 = 当日（同日多笔已聚合）金额 ÷ 同侧最大金额；
 * - 直径 = 最小直径 +（最大直径 − 最小直径）× **√权重** ——开方是刻意的：金额分布长尾，
 *   线性映射会让一笔大额买入把其余点全压成米粒；
 * - 直径区间 **6–16px**；
 * - 区间内交易点 **> 20** 个 → 自动压低上限（不按周/月聚合：聚合会改变「哪天操作的」
 *   这个最重要的事实，而降上限只损失一点视觉分辨力）；
 * - **卖点比买点小一号**（上限乘 0.8）：买卖同大时画面重心会偏向卖出，而买方视角里
 *   「我买了多少」才是主线；
 * - 提供「统一大小」开关（默认关 = 弱金额权重）：只看**在哪买**、不看**买了多少**的用户
 *   需要一条安静得下来的曲线。
 *
 * ## 为什么权重按「当日聚合金额」而不是「单笔金额」
 *
 * 同日多笔在渲染前已聚合成一个点（`markerData`），若分子用聚合额、分母用单笔最大值，
 * 权重会系统性 > 1、点全部顶到上限。两处必须同口径。
 */

/** 直径下限（px）：再小就点不中了，触摸屏尤其 */
export const MARKER_MIN_SIZE = 6;
/** 直径上限（px） */
export const MARKER_MAX_SIZE = 16;
/** 卖点上限相对买点的比例（「小一号」） */
export const SELL_SIZE_RATIO = 0.8;
/** 超过这个点数就降低上限，避免密集处糊成一片 */
export const DENSE_POINT_THRESHOLD = 20;
/** 密集时的买点上限 */
export const DENSE_MAX_SIZE = 11;
/** 「统一大小」开关打开时的固定直径：取 6–16 的中间偏上，既点得中又不抢主线 */
export const UNIFIED_SIZE = 9;

/**
 * 本侧直径上限（按该侧点数量决定是否降档）。
 *
 * 分侧计算而不是看两侧总数：买点 30 个、卖点 2 个时，卖点不该被跟着压小。
 */
export function markerMaxSize(pointCount: number): number {
  return pointCount > DENSE_POINT_THRESHOLD ? DENSE_MAX_SIZE : MARKER_MAX_SIZE;
}

/**
 * 单点直径：`min + (max − min) × √权重`。
 *
 * `maxAmount <= 0`（全为 0 或空集）时一律取下限——分母为 0 会算出 `NaN`，
 * 而 ECharts 拿到 `NaN` 的表现是**默默不画这个点**，等于把交易记录藏了。
 */
export function markerSize(
  amount: number,
  maxAmount: number,
  maxSize: number,
  minSize: number = MARKER_MIN_SIZE
): number {
  if (!(maxAmount > 0) || !(amount > 0)) return minSize;
  const weight = Math.min(amount / maxAmount, 1);
  return +(minSize + (maxSize - minSize) * Math.sqrt(weight)).toFixed(2);
}

/** 一侧点集里的最大金额（权重分母）；空集为 0 */
export function maxAmountOf(points: { amount: number }[]): number {
  let max = 0;
  for (const p of points) {
    if (p.amount > max) max = p.amount;
  }
  return max;
}
