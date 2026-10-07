/**
 * PnlCalendar 的共享小工具（#1925 拆 `PnlCalendarGrid` 时抽出；#1942 扩为三个格子视图共用）。
 *
 * 日 / 月 / 年三粒度都要构造请求区间、格子日期、四态文案与色深档位。这些规则
 * **必须只有一份实现**：两处各写一份 `padStart` 迟早漏掉补零（后端只认 `YYYY-MM-DD`），
 * 两处各写一份状态文案则会出现「同一个状态在日历图叫未同步、在方格图叫没数据」。
 */

import type { PnlCalendarGranularity, PnlCalendarState } from "@/api/summary";

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
  // 用户明确要求：不要说「无历史价格序列」——那是实现语言，用户看不懂，
  // 且会被误解成「我的理财出问题了」。产品语言是「暂无每日估值」。
  no_price: "暂无估值",
  // 开盘日却没有当天估值：净值还没发布，或每日同步任务没跑。用户能处置。
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
  if (state === "no_price") {
    return `${label}：该产品按日没有估值序列，不参与收益计算`;
  }
  if (state === "no_data") {
    return `${label}：交易日但没有当天估值（净值未发布或每日同步未跑）`;
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
