// src/views/asset/cleared-cycles/helpers.ts
/**
 * 清仓周期复盘（#2131）纯展示助手。
 *
 * 纪律：只做「null → 占位」「展示舍入」与键构造，**不做任何数值计算**——
 * 盈亏/胜率/持有天数全部由后端算好（services/analytics/cleared_cycles.py），
 * 前端二次计算即第二口径。（取整属展示舍入，见 `fmtHoldingDays` 的长注释。）
 */
import type { ClearedCycle, ClearedCyclesSummary } from "@/api/summary";

/** 比率展示（胜率 %/盈亏比）：null = 无样本/不可算 → "--"，禁止画 0 */
export function fmtRatio(value: number | null | undefined): string {
  return value === null || value === undefined ? "--" : value.toFixed(2);
}

/**
 * 平均持有天数的**数值**展示（已取整；汇总卡自己带 `unit`，不能再拼「天」）。
 *
 * 取整的理由见 `fmtHoldingDays`；此处单列是为了让「周期行要单位 / 汇总卡不要单位」
 * 共用同一份舍入规则，而不是两处各写一个 `Math.round`。
 */
export function fmtHoldingDaysValue(
  days: number | null | undefined
): number | null {
  if (days === null || days === undefined) return null;
  return Math.round(days);
}

/**
 * 平均持有天数展示：null → "--"，有值**取整到整数天**后带单位。
 *
 * 后端给的是「份额加权平均天数」，带一位小数（例：5000 份持 364 天 + 5000 份持
 * 729 天 → 546.5 天）。这个小数据**没有可行动的意义**：
 *
 * - 底层事实粒度就是日历天（确认日 → 确认日），不存在「半天」；
 * - 0.1 天 ≈ 2.4 小时，远小于 FIFO 配对本身的误差；
 * - 表格里 109.1 / 92 / 27.9 混排，小数位让右对齐的数字参差不齐，反而不易扫读。
 *
 * 取整放在**展示层**而不是后端，有两个具体原因：
 * 1. 后端口径层要保留精确值——`test_analytics_behavior.py` 正是用 546.5 这个
 *    精确加权值钉住 FIFO 分摊逻辑，抹掉小数就失去该用例的表达力；
 * 2. Python 的 `round()` 是**银行家舍入**（`round(89.5) == 88`），在服务端取整会
 *    出现「89.5 天显示 88 天」；`Math.round` 是 half-up（→ 90），符合常识。
 *
 * `ProductProPerformance` 的平均持有天数早已是 `toFixed(0)`，此处对齐同一惯例。
 */
export function fmtHoldingDays(days: number | null | undefined): string {
  const rounded = fmtHoldingDaysValue(days);
  return rounded === null ? "--" : `${rounded} 天`;
}

/** 周期行唯一键：同一标的可有多轮周期（cycle_number 区分） */
export function cycleRowKey(cycle: ClearedCycle): string {
  return `${cycle.symbol}#${cycle.cycle_number}`;
}

/** 汇总卡样本说明：样本 < 周期数时须显式说明部分周期未进样本（诚实降级） */
export function sampleNote(summary: ClearedCyclesSummary): string {
  const { sample_count: sample, cycle_count: total } = summary;
  if (total === 0) return "录入卖出流水后自动归档";
  if (sample === total) return `基于 ${total} 个已完结周期`;
  return `基于 ${sample}/${total} 个周期（部分配对周期不可算，未计入）`;
}

/** 汇总卡盈亏 caption：无样本时不显示「¥0.00」误导成「没赚到钱」 */
export function pnlTotalCaption(summary: ClearedCyclesSummary): string {
  return summary.sample_count > 0
    ? `共 ${summary.total_trade_count} 笔交易`
    : "暂无可算周期";
}

/* ─────────────────── 时间范围（#2774） ───────────────────
 * 只负责「档位 → start_date」，**不在前端裁剪数据**：区间由后端按末卖日裁，
 * 前端再算一遍就是第二口径（且会与汇总数字打架）。
 */

export type ClearedRangeKey = "1m" | "6m" | "1y" | "all";

/** 档位顺序由近到远，「投资以来」垫底且为默认（与 #2131 上线时的行为一致） */
export const CLEARED_RANGE_OPTIONS: readonly {
  label: string;
  value: ClearedRangeKey;
}[] = [
  { label: "近一月", value: "1m" },
  { label: "近半年", value: "6m" },
  { label: "近一年", value: "1y" },
  { label: "投资以来", value: "all" }
] as const;

const RANGE_MONTHS: Record<Exclude<ClearedRangeKey, "all">, number> = {
  "1m": 1,
  "6m": 6,
  "1y": 12
};

/** 按本地时区拼 YYYY-MM-DD；**不用** toISOString——它按 UTC 截断，东八区会差一天 */
function toIsoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/**
 * 往前推 N 个**日历月**，日号超界时夹到当月最后一天。
 *
 * 为什么不用「30 × N 天」：近一月/近半年这类说法在用户心里是日历月，
 * 而 3-31 减一个月必须落在 2-28（`setMonth` 直接减会溢出成 3-03）。
 */
export function subtractMonths(base: Date, months: number): Date {
  const d = new Date(base.getTime());
  const day = d.getDate();
  d.setDate(1);
  d.setMonth(d.getMonth() - months);
  const lastDay = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
  d.setDate(Math.min(day, lastDay));
  return d;
}

/** 档位 → 后端 `start_date`；「投资以来」返回 null（不传参 = 全量） */
export function rangeStartDate(
  range: ClearedRangeKey,
  today: Date = new Date()
): string | null {
  if (range === "all") return null;
  return toIsoDate(subtractMonths(today, RANGE_MONTHS[range]));
}

/* ─────────────────── 盈亏排行（#2774） ─────────────────── */

export type RankDirection = "win" | "loss";

export const RANK_LIMIT = 5;

/**
 * 取盈亏排行前 N（含方向过滤）。
 *
 * 三条纪律：
 * 1. **只收 `pnl_known` 周期**——部分配对的盈亏是 null，排进榜单等于把「不可算」当 0；
 * 2. 盈利榜只收 `> 0`、亏损榜只收 `< 0`：零盈亏既不是「最赚」也不是「最亏」，混进去会挤掉真样本；
 * 3. 排序用副本，不改动调用方数组（表格仍按末卖日倒序展示）。
 */
export function pickTop(
  cycles: readonly ClearedCycle[],
  direction: RankDirection,
  limit: number = RANK_LIMIT
): ClearedCycle[] {
  const known = (cycles || []).filter(
    c => c.pnl_known && typeof c.realized_pnl === "number"
  );
  const sorted = [...known].sort((a, b) => {
    const diff = (b.realized_pnl as number) - (a.realized_pnl as number);
    return direction === "win" ? diff : -diff;
  });
  return sorted
    .filter(c =>
      direction === "win"
        ? (c.realized_pnl as number) > 0
        : (c.realized_pnl as number) < 0
    )
    .slice(0, Math.max(0, limit));
}

/* ─────────────────── 清仓后涨跌幅（#2773） ─────────────────── */

export type PostClearCell = {
  /** 涨跌幅（%）；null = 算不出，模板画占位。**不是 0** */
  pct: number | null;
  /** 算不出时的占位文案（算得出时为 null，数值交给 RiseFallText 着色） */
  placeholder: string | null;
  /** 必给的说明：算得出 → 截至哪天 + 什么口径；算不出 → 为什么算不出 */
  title: string;
};

const POST_CLEAR_REASON: Record<string, string> = {
  no_nav_at_sell:
    "卖出日及之前没有净值记录（多为早期清仓，历史净值从未拉取过），无法计算",
  no_nav_after: "卖出之后没有更新的净值（净值已停更）。这不是「没涨没跌」",
  not_supported:
    "场内标的暂不支持——需要另一套价格源（前复权收盘价），未接入前不假装能算"
};

/**
 * 「清仓后」单元格：数值 + 必须存在的说明。
 *
 * 三条纪律（都是 #2773 的验收口径）：
 *
 * 1. **算不出回 `--` 且带原因**：`post_clear_pct` 为 null 时状态码解释了是「没锚点」
 *    还是「净值停更」，两者对用户的含义完全不同，不能都画成一个空格。
 * 2. **颜色按涨跌，不按好坏**：红=涨（卖飞了）、绿=跌（躲过一刀）。好坏只写在
 *    `title` 里。反过来编码会让同一列出现两种解读（同一条红既可能表示「赚了」
 *    也可能表示「卖早了」）。
 * 3. **「截至哪天」跟数一起给**：净值可能停在几个月前，不标日期等于把旧数当实时值。
 */
export function postClearCell(cycle: ClearedCycle): PostClearCell {
  const status = cycle.post_clear_status;
  const pct = cycle.post_clear_pct;

  if (status === "ok" && typeof pct === "number") {
    const basis =
      cycle.post_clear_basis === "unit_nav"
        ? "单位净值口径（不含分红再投）"
        : "累计净值口径（含分红再投）";
    const asOf = cycle.post_clear_as_of
      ? `截至 ${cycle.post_clear_as_of}`
      : "截至最新净值";
    const meaning =
      pct > 0
        ? "卖出后继续上涨（卖飞）"
        : pct < 0
          ? "卖出后下跌（躲过）"
          : "卖出后持平";
    return {
      pct,
      placeholder: null,
      title: `清仓后至${asOf}，${basis}；${meaning}`
    };
  }

  if (!status) {
    // 没传 `include_post_clear` 才会走到这里：如实说「没算」，别让它看起来像「算出来是空」
    return {
      pct: null,
      placeholder: "--",
      title: "本次请求未计算清仓后涨跌幅"
    };
  }

  return {
    pct: null,
    placeholder: "--",
    title: POST_CLEAR_REASON[status] ?? "清仓后涨跌幅不可算"
  };
}

/**
 * 胜率卡的说明：**必须**把「还有几只浮亏没算进来」并列写出来（#2773）。
 *
 * 胜率只统计已清仓周期，套牢不卖的浮亏不在分母里 ⇒ 这个数天然偏乐观。把
 * `unrealized_count` 降级成一条 caveat（或干脆不显示）等于让用户拿被挑过的样本
 * 下结论。所以它这里不是「附加信息」，是与胜率绑定的限定条件。
 */
export function winRateCaption(summary: ClearedCyclesSummary): string {
  const base =
    summary.sample_count === 0
      ? "暂无已完结周期"
      : `胜 ${summary.win_count} / 负 ${summary.loss_count}（样本 ${summary.sample_count}）`;
  const unrealized = summary.unrealized_count;
  if (unrealized === null || unrealized === undefined) {
    // 后端没算（降级）≠ 没有浮亏，不能省略不提
    return `${base}；浮亏标的数不可用`;
  }
  if (unrealized === 0) return `${base}；当前无浮亏持仓`;
  return `${base}；另有 ${unrealized} 只持仓浮亏未计入`;
}
