/**
 * PnlCalendar 三种「空」的判定与文案（#1812 上线首日的教训；#980 拆 `index.vue` 时抽出）。
 *
 * 为什么必须单独一个模块：空态判据是**三处**共用的——组件自己决定画什么、合计行决定
 * 是否给「去看看有数据那期」的按钮、以及单测。判据与文案一旦写在 `.vue` 里，就只能靠
 * 端到端观察，而「把数据缺口说成持仓有问题」正是这条判据写反时的产物。
 *
 * 文案纪律：区分**数据缺口**（每日快照任务没跑，用户可处置）与**无估值序列**
 * （理财 / 投顾 / 实物的产品属性，用户无事可做）。混成一句「没有历史价格序列」，
 * 前一种就被说成了用户的持仓有问题。
 */

import type { PnlCalendarGranularity, PnlCalendarSeries } from "@/api/summary";

/** 持仓按日无估值序列——产品属性，不是故障，也没有可处置的动作 */
export const EMPTY_NO_VALUATION =
  "账户里的产品按日没有估值序列（银行理财、投顾组合、实物资产等），" +
  "因此没有每日收益。";

/** 该区间一条价格都没有——通常是每日快照任务没跑，说清「别处有」并给出去处 */
export function emptyDataGapHint(lastDate: string, scope: string): string {
  return (
    `${scope}还没有每日估值数据。最近一次估值：${lastDate}。` +
    "通常是每日快照任务未运行所致，并非账户异常。"
  );
}

/** 空态里的「哪儿没数据」——粒度不同说法不同，别在年视图里说「本月」 */
export function emptyScopeFor(granularity: PnlCalendarGranularity): string {
  if (granularity === "day") return "本月";
  if (granularity === "month") return "本年";
  // 年视图的区间就是「投资以来」，说「该区间」不如直说
  return "投资以来";
}

/**
 * 是否属于**数据缺口**（而非「持仓本身没有估值序列」）。
 *
 * 完全没有覆盖 ⇒ 缺口；有覆盖但 priced=0 ⇒ 持仓按日无估值序列。
 * `coverage` 缺失时按「不是缺口」处理：没有诊断信息就不该断言任务没跑。
 */
export function isDataGap(series: PnlCalendarSeries | null): boolean {
  const cov = series?.coverage;
  if (!cov) return false;
  return cov.priced_positions === 0 && !series?.latest_price_date;
}

/** 空态正文：缺口说缺口，否则说产品属性 */
export function emptyHintFor(
  series: PnlCalendarSeries | null,
  granularity: PnlCalendarGranularity
): string {
  if (!isDataGap(series)) return EMPTY_NO_VALUATION;
  return emptyDataGapHint(
    series?.latest_price_date ?? "—",
    emptyScopeFor(granularity)
  );
}

/**
 * 有数据的最近一期（已正在看则回空串，跳转按钮随之隐藏）。
 *
 * 年视图恒回空串：它的区间固定为「投资以来 → 今年」，最新数据必然落在区间内，
 * 跳了也不会换区间——那种按钮是骗人的。
 */
export function latestPriceLabelFor(
  series: PnlCalendarSeries | null,
  granularity: PnlCalendarGranularity,
  cursor: Date
): string {
  const d = series?.latest_price_date;
  if (!d) return "";
  const year = d.slice(0, 4);
  if (granularity === "year") return "";
  if (granularity === "month") {
    return year === String(cursor.getFullYear()) ? "" : `${year} 年`;
  }
  const monthKey = d.slice(0, 7);
  const curKey =
    `${cursor.getFullYear()}-` + String(cursor.getMonth() + 1).padStart(2, "0");
  return monthKey === curKey ? "" : monthKey.replace("-", " 年 ") + " 月";
}

/** 跳转按钮文案：日粒度跳到「月份」，月 / 年粒度跳到「年份」 */
export function jumpButtonTextFor(
  latestPriceLabel: string,
  granularity: PnlCalendarGranularity
): string {
  return `查看 ${latestPriceLabel} 有数据的${
    granularity === "day" ? "月份" : "年份"
  }`;
}
