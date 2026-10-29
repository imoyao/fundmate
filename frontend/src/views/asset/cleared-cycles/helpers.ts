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
