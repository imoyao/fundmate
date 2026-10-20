// src/views/asset/cleared-cycles/helpers.ts
/**
 * 清仓周期复盘（#2131）纯展示助手。
 *
 * 纪律：只做「null → 占位」与键构造，**不做任何数值计算**——
 * 盈亏/胜率/持有天数全部由后端算好（services/analytics/cleared_cycles.py），
 * 前端二次计算即第二口径。
 */
import type { ClearedCycle, ClearedCyclesSummary } from "@/api/summary";

/** 比率展示（胜率 %/盈亏比）：null = 无样本/不可算 → "--"，禁止画 0 */
export function fmtRatio(value: number | null | undefined): string {
  return value === null || value === undefined ? "--" : value.toFixed(2);
}

/** 平均持有天数展示：null → "--" */
export function fmtHoldingDays(days: number | null | undefined): string {
  return days === null || days === undefined ? "--" : `${days} 天`;
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
