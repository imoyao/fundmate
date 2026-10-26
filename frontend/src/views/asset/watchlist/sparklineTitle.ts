/**
 * 走势列（sparkline）的 `title` 口径（#2651）。
 *
 * ## 为什么单独成模块
 *
 * #2640 的实现里，`title` 只在「有折线」的分支生成，而「无数据」分支提前 return
 * 一个裸 `--`——于是场外基金那句「无盘中估值分时」的说明**永远走不到**。
 * 偏偏是无数据的行最需要解释：用户看到空白，没有任何线索指向「这只基金没有分时源」
 * 还是「数据没回填 / 页面坏了」。
 *
 * 抽成纯函数后，四类输入的文案可以在 node 环境直接断言（`columnRenderers.tsx`
 * 一路 import `.vue` 组件，vitest node 环境里不能直接测渲染器，见 `dayPnl.spec.ts` 的说明）。
 *
 * ## 文案约定
 *
 * | 分时点数 | 日线点数 | 文案 |
 * |---|---|---|
 * | ≥2 | — | `当日分时走势（盘中实时）` |
 * | <2 | ≥2 | 场外：`场外基金无盘中估值分时，显示近 60 日净值走势`；其余：`近 60 日收盘价走势` |
 * | 1 | <2 | `当日分时暂无数据（盘中刚开盘）` |
 * | 0 | <2 | 场外：`场外基金无盘中估值分时，暂无净值数据`；其余：`暂无走势数据` |
 *
 * 无数据时**场外与场内必须不同句**：两者缺数据的原因不同（无分时源 vs 未回填），
 * 同一句话会让用户把「场外基金本来就没有分时」误读成「所有数据都缺」。
 *
 * ⚠️ 改文案同步 `__tests__/sparklineTitle.spec.ts`——那里钉住了 #2651 的验收判据。
 */

/** 场外基金：无盘中估值分时，有日线时看的是净值走势 */
const OTC_WITH_TREND = "场外基金无盘中估值分时，显示近 60 日净值走势";
/** 场外基金：连净值序列都没有（未回填 / 新标的） */
const OTC_NO_DATA = "场外基金无盘中估值分时，暂无净值数据";
/** 场内：回落近 60 日收盘价 */
const WITH_TREND = "近 60 日收盘价走势";
/** 场内：完全没有走势数据 */
const NO_DATA = "暂无走势数据";
/** 分时正在采集（点数不足 2，画不出线） */
const INTRADAY_INCOMPLETE = "当日分时暂无数据（盘中刚开盘）";
/** 当日分时（≥2 点） */
const INTRADAY = "当日分时走势（盘中实时）";

export interface SparklineTitleInput {
  /** 是否场外基金（`venue === "OTC"`）——场外没有盘中估值分时源 */
  isOtc: boolean;
  /** 当日分时点数；未取到分时给 `0`（`ctx.intraday` 里没有该码） */
  intradayPoints?: number | null;
  /** 近 60 日走势点数；未回填给 `0` */
  trendPoints?: number | null;
}

/**
 * 解析走势列的 `title`。
 *
 * 只依赖点数，不依赖数据本身——渲染器算完点数后调用，保证「有线的分支」与
 * 「`--` 的分支」共用同一套口径，不会再次出现某条分支漏写 `title`。
 */
export function resolveSparklineTitle(input: SparklineTitleInput): string {
  const intradayPoints = input.intradayPoints ?? 0;
  const trendPoints = input.trendPoints ?? 0;

  if (intradayPoints >= 2) return INTRADAY;
  if (trendPoints >= 2) return input.isOtc ? OTC_WITH_TREND : WITH_TREND;
  // 分时有对象但点数不足：不是「没有分时源」，而是「还在采集」，两种说法要分开
  if (intradayPoints === 1) return INTRADAY_INCOMPLETE;
  return input.isOtc ? OTC_NO_DATA : NO_DATA;
}
