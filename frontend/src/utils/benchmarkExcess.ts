/**
 * #2134 基准超额收益：账户 / 组合详情两处容器共用的区间与降级文案。
 *
 * 口径唯一：所有数值都来自后端 `/summary/benchmark-excess/`，本文件只做
 * 「请求区间怎么取」与「算不出时怎么说」，禁止在前端二次计算收益率。
 */
import type { BenchmarkExcessResult } from "@/api/summary";
import { formatDate } from "./date";

/** 默认展示区间：近 90 天（含今日）；两处容器保持一致 */
export const EXCESS_RANGE_DAYS = 90;

/** 请求区间（YYYY-MM-DD，本地时区，不走 toISOString 避免 UTC 跨日偏移） */
export function excessDateRange(days = EXCESS_RANGE_DAYS): {
  start_date: string;
  end_date: string;
} {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - (days - 1));
  return { start_date: formatDate(start), end_date: formatDate(end) };
}

/** 带符号百分比文本（+5.00% / -1.67%）；null 回「—」（诚实降级，不造 0） */
export function formatSignedPct(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const body = value > 0 ? `+${value.toFixed(2)}` : value.toFixed(2);
  return `${body}%`;
}

/**
 * 降级原因的平实中文提示；可算（两侧都齐）回空串。
 * 只取最根本的一条：区间收益侧原因优先于指数侧。
 */
export function excessDegradHint(data: BenchmarkExcessResult | null): string {
  if (!data) return "";
  const reason = data.range_reason ?? data.benchmark?.reason ?? null;
  if (!reason) return "";
  switch (reason) {
    case "non_cn_a_holdings":
      return "持仓含港美股，宽基指数不可比";
    case "unrecognized_benchmark":
      return "所设基准不在宽基指数范围";
    case "index_insufficient_data":
    case "coverage_start_insufficient":
    case "coverage_end_insufficient":
      return "指数区间数据不足";
    case "no_members":
      return "组合暂无关联账户";
    case "no_position":
      return "区间内无持仓";
    default:
      return "暂无可比数据";
  }
}
