/**
 * 组合风格面板的派生逻辑（#2603）。
 *
 * 提到纯模块的原因与 `views/asset/family/familyMemberModel.ts` 相同：vitest 的 node
 * 环境拉不起渲染器（会连带 router / supabase），所以组件里可测的判定必须落在这里。
 *
 * 三种状态必须分清，不能合并成一句「暂无数据」：
 * - `empty`：一个风格都没算出来（无持仓 / 全无风格箱数据）——「算不出来」；
 * - `low-coverage`：算出来了但覆盖率不足 ——「算得不全」；
 * - `ready`：覆盖率达标 ——「算得全」。
 * 「0 暴露」与「没有数据」是两件事，前者不该被读成后者。
 */

import {
  NO_ELIGIBLE_COVERAGE_TEXT,
  coverageScopeHint,
  effectiveCoveragePct
} from "@/utils/styleCoverage";

/** 单风格暴露（0-100，合计 100；null = 该风格缺失，不补 0） */
export interface StyleItem {
  style_name: string;
  value: number | null;
}

/** 无风格箱的持仓 */
export interface StyleUncovered {
  symbol: string;
  name: string;
  market_value_cents: number;
}

/** 组合加权风格暴露（对应后端 `portfolio_style_exposure` 出参） */
export interface PortfolioStyleData {
  styles: StyleItem[];
  fund_count: number;
  /** 全量持仓口径覆盖率（含永远无箱体的货基/现金，#2478 契约） */
  coverage_pct: number;
  /** 可覆盖资产口径覆盖率；null = 没有可覆盖的资产（≠ 0%），见 utils/styleCoverage */
  eligible_coverage_pct?: number | null;
  period_from: string | null;
  period_to: string | null;
  uncovered: StyleUncovered[];
  has_qdii: boolean;
}

export type StylePanelState = "empty" | "low-coverage" | "ready";

/**
 * 风格数据覆盖率的门槛（%）。
 * 与后端 `services/insight/rules.py` 的 `STYLE_MIN_COVERAGE_PCT` 同值：
 * 低于它时，「某风格占 62%」可能只是样本少造成的假象，宁可少说。
 */
export const STYLE_COVERAGE_FLOOR = 50;

/**
 * 面板状态判定。
 *
 * 覆盖率必须用**可覆盖口径**（#2628）：货基/现金的市值永远拿不到箱体，算进分母会把
 * 「其实算得全」误判成「算得不全」，白挂一条低覆盖警告。
 */
export function resolveStylePanelState(
  data: PortfolioStyleData | null | undefined
): StylePanelState {
  if (!data || !data.styles || data.styles.length === 0) return "empty";
  const pct = effectiveCoveragePct(data);
  // null = 没有可覆盖资产（此时 styles 仍有值只可能是 QDII 等），按「算得不全」处理
  if (pct === null || pct < STYLE_COVERAGE_FLOOR) return "low-coverage";
  return "ready";
}

/** 暴露值格式化：null / NaN 一律显示「—」，不补 0（0 暴露与缺值是两件事） */
export function formatStyleValue(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(1)}%`;
}

/** 条形宽度：夹在 0~100%，防止上游异常值把布局撑破 */
export function styleBarWidth(value: number | null | undefined): string {
  const v = Math.max(0, Math.min(100, value ?? 0));
  return `${v}%`;
}

/**
 * 覆盖率说明文案：主数字用**可覆盖口径**，全量口径降为提示（#2628）。
 *
 * 两个数不同时都写出来：只写可覆盖口径，用户会疑惑「上面那只货基怎么算的」；
 * 只写全量口径，又会把「全是货基」误读成「没同步」。
 */
export function describeStyleCoverage(
  data: PortfolioStyleData | null | undefined
): string {
  const n = data?.fund_count ?? 0;
  const pct = effectiveCoveragePct(data);
  if (pct === null) {
    return `${NO_ELIGIBLE_COVERAGE_TEXT}，${n} 只基金有风格箱`;
  }
  const main = `风格数据覆盖 ${pct.toFixed(1)}%（可覆盖资产口径），${n} 只持仓基金有风格箱`;
  const hint = coverageScopeHint(data);
  return hint ? `${main}；${hint}` : main;
}

/** 未覆盖持仓说明（最多列 3 个名字，其余给总数） */
export function describeUncovered(
  data: PortfolioStyleData | null | undefined
): string {
  const list = data?.uncovered ?? [];
  if (!list.length) return "";
  const names = list.map(item => item.name || item.symbol);
  const shown = names.slice(0, 3).join("、");
  const rest = names.length - 3;
  // 数量始终给出来：只列名字不列数量，用户不知道漏了几个
  return `${shown}${rest > 0 ? " 等" : ""} ${names.length} 只持仓没有风格数据`;
}

/**
 * QDII 口径说明。QDII 的风格分类是上游原值（韭圈儿对海外资产映射存疑，
 * 实测 270042 纳指100 被判「固收风格」），必须让用户看见而不是默认它对。
 */
export function describeQdiiCaveat(
  data: PortfolioStyleData | null | undefined
): string {
  if (!data?.has_qdii) return "";
  return "含 QDII 持仓：其风格分类为上游原值（对海外资产映射存疑），仅供参考";
}
