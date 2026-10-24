// frontend/src/views/product/components/fundRatingFormat.ts
/**
 * 晨星评级文案口径（#1440）。
 *
 * 数据源：东财评级总汇页（晨星授权内容），**晨星 3 年期**星级；
 * 采集与口径实证见 `docs/dev/fund-rating-collection.md`。
 *
 * ## 为什么收口在纯函数里
 *
 * 两条口径都是「**写错了没人发现**」型——模板里内联 `v-if` 时没人能钉住它们：
 *
 * 1. **期限口径必须写在值里**（「3 星（3年期）」）。晨星评级**本身含风险调整维度**，
 *    不是纯收益评级；只显示「3」或 ★ 符号，读者会读成「收益星级」——这是误读，
 *    不是排版问题。值里带「3年期」是把**机构 + 期限**一并交代清楚。
 * 2. **缺失 ≠ 0 星**。货基 / 新基金常态无晨星评级，显示「0 星」是**编造数据**；
 *    必须整格显示「—」。
 *
 * ## delta 的表达边界
 *
 * 只表达**方向与幅度**。上期值**不展示**——当期值列不存历史，无从取上期星级，
 * 能说的只有「升/降几星」。delta = 0（与上期持平）无信息量，不展示。
 */

/** 评级期限口径：晨星官方 `starRatingDetails.ratingPeriod = 36`（3 年期） */
export const RATING_PERIOD_LABEL = "3年期";

/**
 * 评级值文案，如「3 星（3年期）」。
 *
 * @param rating 1~5 的星级；null / undefined = 该基金无晨星评级
 * @returns 文案；无评级（或值越域）时返回 null（调用方显示「—」，**不得**显示 0 星）
 */
export function formatRatingText(
  rating: number | null | undefined
): string | null {
  // 值域守卫：晨星星级只有 1~5，「0 星」在晨星语境**不存在**。
  // 后端 adapter 已在落库前抛错拦截（_parse_rating_star），这里是第二道——
  // 前端渲染的是**读库值**，不该假设库里永远干净（历史脏数据 / 手工改库都可能）。
  if (rating == null) return null;
  if (!Number.isInteger(rating) || rating < 1 || rating > 5) return null;
  return `${rating} 星（${RATING_PERIOD_LABEL}）`;
}

/**
 * 评级变化文案，如「较上期 升1星」/「较上期 降1星」。
 *
 * @param delta 较上期变化（-4~4）；null / undefined = 未知；0 = 持平
 * @returns 文案；未知或持平时返回 null（**不展示**）
 */
export function formatRatingDeltaText(
  delta: number | null | undefined
): string | null {
  if (!delta) return null;
  return delta > 0 ? `较上期 升${delta}星` : `较上期 降${Math.abs(delta)}星`;
}
