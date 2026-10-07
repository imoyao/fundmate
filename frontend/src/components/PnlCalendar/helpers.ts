/**
 * PnlCalendar 的共享小工具（#1925 拆 `PnlCalendarGrid` 时抽出；#1942 扩为三个格子视图共用）。
 *
 * 日 / 月 / 年三粒度都要构造请求区间、格子日期、四态文案与色深档位。这些规则
 * **必须只有一份实现**：两处各写一份 `padStart` 迟早漏掉补零（后端只认 `YYYY-MM-DD`），
 * 两处各写一份状态文案则会出现「同一个状态在日历图叫未同步、在方格图叫没数据」。
 */

import type { PnlCalendarGranularity, PnlCalendarState } from "@/api/summary";

/**
 * 数字口径（#1942 ②）：看金额还是看收益率。
 *
 * 三视图（日历图 / 方格图 / 柱状图）共用同一个开关，切换时**不重新请求**——
 * `days[].rate` / `periods[].rate` 与 `range_rate` 后端早就一并下发了，
 * 前端只换显示口径，不做任何二次计算（这是本组件一贯的硬约束）。
 */
export type PnlCalendarValueMode = "amount" | "rate";

/** 口径选项（SegmentedControl 的入参；两个口径都要有中文名，别只放「元 / %」） */
export const VALUE_MODE_OPTIONS = [
  { label: "金额", value: "amount" },
  { label: "收益率", value: "rate" }
] as const;

/**
 * 取该单元在当前口径下的数值。
 *
 * 缺数据（`pnl == null`）时两个口径都回 `null`——**不许回 0**：
 * 「休市 / 未同步 / 无持仓」在收益率口径下同样不是 0.00%。
 * 收益率另有自己的 `null`（无前一日基准），故要按口径分别取。
 */
export function valueIn(
  mode: PnlCalendarValueMode,
  pnl: number | null,
  rate: number | null
): number | null {
  if (pnl == null) return null;
  return mode === "rate" ? rate : pnl;
}

/** 取该月首日（存 1 号，避免时区漂移） */
export function firstOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

/** `YYYY-MM-DD`（本地时区，月 / 日补零） */
export function ymd(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

/**
 * ISO 日期的星期（`Date.getDay()` 值：0=周日，1=周一 … 6=周六）。
 *
 * **必须按本地时区构造**：`new Date("2026-09-05")` 会被解析成 UTC 午夜，
 * 在东八区之外的时区取 `getDay()` 会错位一天（西半球直接退到前一天）。
 * 日历图的列归属全靠它，错一天就是整月错位。
 */
export function weekdayOf(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).getDay();
}

/** `Date.getDay()` 值 → 中文单字列头 */
const WEEKDAY_LABELS = ["日", "一", "二", "三", "四", "五", "六"] as const;

export function weekdayLabel(weekday: number): string {
  return WEEKDAY_LABELS[weekday] ?? "";
}

/**
 * 六态的**格内小标签**（#1942 从四态扩为六态）。
 *
 * 格子空间只放得下 3–4 个字，完整解释在 tooltip / aria（见 `stateDescription`）。
 * 关键是「休市」与「未同步」不能混用：#1942 之前两者共用一个状态码，
 * 于是一个月里凡净值没同步到的交易日全显示「休市」，用户看到的就是
 * 「9 月一半都是休市，和实际不符」——市场没关门，是数据没同步。
 */
const STATE_TAG: Record<PnlCalendarState, string> = {
  updown: "",
  zero: "0.00",
  // #1917：部分断档。数值照常显示，只是可信度低——用「※」标记，
  // 用户扫一眼就知道「这天有东西没更新到」，aria/tooltip 有完整说明。
  partial: "※",
  // 用户明确要求：不要说「无历史价格序列」——那是实现语言，用户看不懂，
  // 且会被误解成「我的理财出问题了」。产品语言是「暂无每日估值」。
  no_price: "暂无估值",
  // 开盘日却一个可用价都没有：净值还没发布，或每日同步任务没跑。用户能处置。
  no_data: "未同步",
  // 当天没有仓位（建仓前 / 清仓后）：与休市、缺数据都无关
  no_position: "无持仓",
  // 非 A 股开盘日：周末 / 法定节假日 / 调休补班的周末（真·休市）
  closed: "休市"
};

export function stateTag(state: PnlCalendarState): string {
  return STATE_TAG[state];
}

/**
 * 单元的可读名：日粒度传 `2026-01-05`，月粒度传 `2026-01`，年粒度传 `2026`。
 *
 * **键长即粒度**是后端定下的契约（见 `services/pnl_calendar._period_key`），
 * 前端据此说人话，不需要后端再传一个可能对不上的展示字段。
 */
export function readableName(name: string): string {
  if (name.length === 7)
    return `${name.slice(0, 4)} 年 ${Number(name.slice(5))} 月`;
  if (name.length === 4) return `${name} 年`;
  return name;
}

/**
 * 单元的完整描述（tooltip 与 `aria-label` 共用同一份文字）。
 *
 * 两处共用一份，是为了避免「鼠标悬停说是未同步、读屏说是休市」这类分叉。
 */
export function stateDescription(
  name: string,
  state: PnlCalendarState,
  pnl: number | null
): string {
  const label = readableName(name);
  // #1917：数值可信但该日有标的数据不全，必须说清「不全」而非「无」
  if (state === "partial") {
    return `${label}：收益 ${pnl ?? 0} 元（该日部分标的未更新估值，数据不完整）`;
  }
  if (state === "no_price") {
    return `${label}：该产品按日没有估值序列，不参与收益计算`;
  }
  if (state === "no_data") {
    return `${label}：交易日但一个当天估值都没取到（净值未发布或每日同步未跑）`;
  }
  if (state === "no_position") {
    return `${label}：当天没有持仓`;
  }
  if (state === "closed") {
    return `${label}：非交易日（休市）`;
  }
  if (state === "zero") return `${label}：收益 0.00 元`;
  return `${label}：收益 ${pnl ?? 0} 元`;
}

/** 区间内最大绝对盈亏（色深与柱高共用的分母；0 表示全是零收益 / 无数据） */
export function maxAbsPnl(values: (number | null)[]): number {
  let max = 0;
  for (const v of values) {
    if (v != null) max = Math.max(max, Math.abs(v));
  }
  return max;
}

/**
 * 色深档位：0（浅）/ 1（中）/ 2（深），由 |收益| / 区间内最大值决定。
 *
 * **绝不为了视觉冲击加深底色**：上限对应的填充比例是算出来的（见 `PnlCalendarTile`
 * 的配色注释，涨色 12% 是 WCAG AA 的硬顶）。
 */
export function intensity(pnl: number | null, maxAbs: number): 0 | 1 | 2 {
  if (pnl == null || maxAbs === 0) return 0;
  const ratio = Math.abs(pnl) / maxAbs;
  if (ratio >= 0.6) return 2;
  if (ratio >= 0.25) return 1;
  return 0;
}

// ── 区间计算（#1942 从 index.vue 抽出：纯函数，与「发什么请求 / 显示什么标签」解耦）──

/** 今年（年视图区间的右端） */
export function currentYear(): number {
  return new Date().getFullYear();
}

/**
 * 年视图的起始年份：`first_txn_date`（最早一笔改变份额的流水）所在年。
 *
 * 起点未知时**回落到今年**——那只会让年视图短暂只显示一年，而 `index.vue` 的
 * `load()` 拿到第一次响应后会用真实起点重取一次。
 * **不要**改成写死的年数窗口（#1925 的 `YEAR_WINDOW = 3` 就是这么做的）：
 * 窗口边界与真实建仓年份无关，用户会看到「投资以来」缺了最早的几年。
 *
 * ⚠️ 代价要知情（真实库只读探针，2026-10-07，家庭 154 笔持仓 / 151 笔在用）：
 * 起点从此固定为**最早一笔流水**（实测 2023-03-13）⇒ 区间 1391 天，
 * `granularity=year` 单次 **6.08s**（同年 366 天的 month 视图 1.66s、整月 0.75s）。
 * 区间长度与耗时近似线性，故年份逐年增加会继续变慢。这是「投资以来每一年一格」
 * 的直接代价，不是回归；根治要给日序列做物化快照（#1926，读时计算 → 写时计算）。
 * 在那之前**不要再往后拉区间**（例如把起点再提前），否则会变成明显的卡顿。
 */
export function firstInvestmentYear(firstTxnDate: string | null): number {
  return firstTxnDate ? Number(firstTxnDate.slice(0, 4)) : currentYear();
}

/** 当前粒度要请求的闭区间（日=当月，月=当年，年=投资以来 → 今年） */
export function rangeFor(
  granularity: PnlCalendarGranularity,
  cursor: Date,
  firstTxnDate: string | null
): { start: string; end: string } {
  const year = cursor.getFullYear();
  const month = cursor.getMonth();
  if (granularity === "month") {
    return { start: `${year}-01-01`, end: `${year}-12-31` };
  }
  if (granularity === "year") {
    // 投资以来：起点取最早流水那一年，终点取今年。**不跟随游标**——
    // 往前翻只会有建仓前的空年份，往后翻本来就是空的，故年视图没有区间导航。
    const from = firstInvestmentYear(firstTxnDate);
    return { start: `${from}-01-01`, end: `${currentYear()}-12-31` };
  }
  const last = new Date(year, month + 1, 0).getDate();
  return {
    start: `${year}-${String(month + 1).padStart(2, "0")}-01`,
    end: ymd(new Date(year, month, last))
  };
}

/** 当前浏览区间的标签（导航中键 / 区间标签、合计行、柱状图 aria 共用同一份） */
export function rangeLabelFor(
  granularity: PnlCalendarGranularity,
  cursor: Date,
  firstTxnDate: string | null
): string {
  if (granularity === "year") {
    const from = firstInvestmentYear(firstTxnDate);
    const to = currentYear();
    return from < to ? `${from}–${to} 年` : `${to} 年`;
  }
  const year = cursor.getFullYear();
  if (granularity === "month") return `${year} 年`;
  return `${year} 年 ${cursor.getMonth() + 1} 月`;
}
