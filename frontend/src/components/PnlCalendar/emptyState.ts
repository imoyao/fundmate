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

/**
 * 空态里的「哪儿没数据」——粒度不同说法不同，别在年视图里说「本月」。
 *
 * 月粒度跟着**游标所在年**走（`rangeFor` 的月区间是 `cursor.getFullYear()` 那一年）：
 * 用户把区间翻到 2025 年还再说「本年」，就是把去年说成了今年。
 */
export function emptyScopeFor(
  granularity: PnlCalendarGranularity,
  cursor: Date
): string {
  if (granularity === "day") return "本月";
  if (granularity === "month") {
    const year = cursor.getFullYear();
    return year === new Date().getFullYear() ? "本年" : `${year} 年`;
  }
  // 年视图的区间就是「投资以来」，说「该区间」不如直说
  return "投资以来";
}

/**
 * 区间里**还没有「已经发生」的交易日**（#2793）——「还没到」，不是故障。
 *
 * 未来日与周末同待遇、不占格之后，月初打开日历常常只剩下极少格子、甚至一格不剩
 * （2026-11-01 是周日 ⇒ 11 月暂时 0 格），`has_any_price` 随之必然为 false。
 * 若沿用数据缺口的文案（「通常是每日快照任务未运行所致」），就把「还没到」说成了
 * 「出故障了」——用户会去查一个根本不用跑的同步任务。
 *
 * 判据只看日历、不看数据：
 *   · 年粒度区间是「投资以来 → 今年」，恒有已过去的交易日 ⇒ false；
 *   · 月粒度看**游标所在年** 1 月 1 日起，日粒度看游标所在月 1 日起；
 *   · 起点到现在之间有任何一个工作日 ⇒ 已经「开始」了。周末固定休市，
 *     所以按周一~周五判；节假日会让它比真实交易日早一天结束，但方向是
 *     「已开始」，不会把「还没到」误判成「已开始」。
 *
 * ⚠️ 月粒度的起点必须跟**游标**走，不能写死「今年 1 月 1 日」：
 * 月区间是游标所在年（`rangeFor` 用 `cursor.getFullYear()`），用户翻到未来
 * 年份时整段区间都在未来——写死「今年」会把「整段还没到」误判成「已开始」。
 */
export function isNotStartedYet(
  granularity: PnlCalendarGranularity,
  cursor: Date
): boolean {
  if (granularity === "year") return false;
  const today = new Date();
  const from =
    granularity === "day"
      ? new Date(cursor.getFullYear(), cursor.getMonth(), 1)
      : new Date(cursor.getFullYear(), 0, 1);
  if (from > today) return true; // 整段区间都在未来
  for (const d = new Date(from); d <= today; d.setDate(d.getDate() + 1)) {
    const wd = d.getDay();
    if (wd >= 1 && wd <= 5) return false;
  }
  return true;
}

/** 「还没开始」的空态正文：说清是日历事实，别指去同步任务 */
export function emptyNotStartedHint(
  granularity: PnlCalendarGranularity,
  cursor: Date
): string {
  return (
    `${emptyScopeFor(granularity, cursor)}还没有已发生的交易日。` +
    "未来的日期与周末同待遇、不占格，每个交易日结束后才会有当日收益。"
  );
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

/**
 * 空态正文：**还没开始**说还没开始，缺口说缺口，否则说产品属性。
 *
 * 优先判「还没开始」（#2793）：它由日历决定，与数据无关。放在最前面是因为
 * 月初的 `coverage` 必然是 0/0（窗口里还没净值行），会被 `isDataGap` 误判成
 * 数据缺口——那正是本次要避免的误导。
 */
export function emptyHintFor(
  series: PnlCalendarSeries | null,
  granularity: PnlCalendarGranularity,
  cursor: Date
): string {
  if (isNotStartedYet(granularity, cursor))
    return emptyNotStartedHint(granularity, cursor);
  if (!isDataGap(series)) return EMPTY_NO_VALUATION;
  return emptyDataGapHint(
    series?.latest_price_date ?? "—",
    emptyScopeFor(granularity, cursor)
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
