// 同类优选的数值单元格口径（#980 拆分自 index.vue）：格式化、涨跌配色、数据条长度。
//
// 全是**纯函数**（入参是行与列，不读组件状态），因此「给定一行 → 渲染成什么」可以单测；
// 组件里只剩模板绑定。列定义见 ./rankingColumns.ts。
//
// 两条口径红线（原实现注释，勿在重构中丢掉）：
// 1. null 一律降级「—」，不编造 0；
// 2. 显式 +/- 只给收益列——风险比率列加「+」会被读成「收益为正」（UI=+18.5 尤其误导）。
import type { FundRiskRankingRow } from "@/api/products";
import type { RankingColumn } from "./rankingColumns";

export const DASH = "—";

type Column = RankingColumn;

/** 数值格式化：null 一律降级「—」（诚实降级，不编造 0）。
 *  显式 +/- 只给收益列（kind=return，design.md：不用颜色作为唯一信息载体）；
 *  夏普 / 卡玛 / 波回比 / UI 是比率、最大回撤以负数存储——给它们加「+」会读成
 *  「收益为正」（UI=+18.5 尤其误导：越高越煎熬，不是利好）。 */
export function formatCell(row: FundRiskRankingRow, col: Column): string {
  const v = row[col.key as keyof FundRiskRankingRow] as number | null;
  if (v == null) return DASH;
  const fixed = v.toFixed(2);
  return col.kind === "return" && v > 0 ? `+${fixed}` : fixed;
}

/** 收益列涨跌配色（红涨绿跌，A 股惯例）：文字级 -ink 令牌保 WCAG AA，
 *  与自选页「涨跌幅」列同规则；0 与非数值不染。 */
export function numClass(row: FundRiskRankingRow, col: Column): string {
  const v = row[col.key as keyof FundRiskRankingRow] as number | null;
  if (v == null || v === 0) return "";
  return v > 0 ? "num--rise" : "num--fall";
}

/** 数据条（夏普 / 卡玛）：条长 = 该值在**当前榜单**内的相对位置。
 *  全列同值时统一样式（满条）——都排在同一位置，没有长短差异可言。
 *  纯函数化（#980）：入参是行集与列，换榜单即重算，不再依赖组件 computed。 */
export function buildBarRanges(
  rows: FundRiskRankingRow[],
  columns: RankingColumn[]
): Record<string, { min: number; max: number }> {
  const out: Record<string, { min: number; max: number }> = {};
  for (const col of columns) {
    if (!col.bar) continue;
    const vals = rows
      .map(r => r[col.key as keyof FundRiskRankingRow] as number | null)
      .filter((v): v is number => v != null);
    if (vals.length)
      out[col.key] = { min: Math.min(...vals), max: Math.max(...vals) };
  }
  return out;
}

export function barWidth(
  row: FundRiskRankingRow,
  key: string,
  ranges: Record<string, { min: number; max: number }>
): string | undefined {
  const range = ranges[key];
  const v = row[key as keyof FundRiskRankingRow] as number | null;
  if (!range || v == null) return undefined;
  const span = range.max - range.min;
  const pct = span === 0 ? 100 : ((v - range.min) / span) * 100;
  return `${Math.max(4, Math.min(100, pct))}%`;
}

export function dirLabel(dir: string): string {
  return dir === "high" ? "越高越好" : "越低越好";
}
