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
