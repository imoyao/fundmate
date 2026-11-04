/**
 * 风格覆盖率的口径选择（#2628）。
 *
 * 后端两个口径并存（`services/fund_style_service.portfolio_style_exposure`）：
 * - `coverage_pct`：分母 = **全部**持仓市值（#2478 契约），含货基 / 现金这些
 *   永远不会有风格箱的品种 ⇒ 数字有天花板（实测 121 只持仓 → 8.35%），
 *   很容易被读成「同步没在跑」；
 * - `eligible_coverage_pct`：分母只含可能带箱体的持仓（场外基金 / ETF，剔除 QDII）。
 *
 * 展示与「算得全不全」的判断都用后者。`null` 表示**没有可覆盖的资产**，
 * 与「0% 覆盖」是两件事，不得合并成一句话（#2617 的纪律：宁可明示缺口，不可造假）。
 *
 * 老响应没有该字段时回退 `coverage_pct`（向后兼容），故本函数可能返回 number。
 */

export interface StyleCoverageFields {
  /** 全量持仓口径覆盖率（0-100，含永远无箱体的货基/现金） */
  coverage_pct: number;
  /** 可覆盖资产口径覆盖率（0-100）；`null` = 没有可覆盖的资产；缺字段 = 老响应 */
  eligible_coverage_pct?: number | null;
}

/**
 * 取「可覆盖口径」覆盖率。
 *
 * 返回值语义：`number` = 该口径下的覆盖率；`null` = **没有可覆盖的资产**。
 * 刻意不把 `null` 折成 0 —— 那会把「这组合全是货基/现金」说成「一只都没同步到」。
 */
export function effectiveCoveragePct(
  data: StyleCoverageFields | null | undefined
): number | null {
  if (!data) return null;
  const eligible = data.eligible_coverage_pct;
  // 必须显式判 null：`??` 会把「没有可覆盖资产」当成缺省值而回退成全量口径
  if (eligible === null) return null;
  if (typeof eligible === "number" && Number.isFinite(eligible))
    return eligible;
  return Number.isFinite(data.coverage_pct) ? data.coverage_pct : 0;
}

/**
 * 全量口径的提示文案：只在两个口径**不同**时给 —— 相同时多说一句只是噪音。
 * 返回 null 表示不需要提示（含「没有可覆盖资产」，那种情况另有专门文案）。
 */
export function coverageScopeHint(
  data: StyleCoverageFields | null | undefined
): string | null {
  if (!data) return null;
  const effective = effectiveCoveragePct(data);
  if (effective === null) return null;
  const total = Number.isFinite(data.coverage_pct) ? data.coverage_pct : 0;
  if (Math.abs(total - effective) < 0.005) return null;
  return `含货基/现金的全量口径 ${total.toFixed(1)}%`;
}

/** 「没有可覆盖资产」的统一文案：两个面板必须说同一句话 */
export const NO_ELIGIBLE_COVERAGE_TEXT =
  "当前持仓没有可覆盖风格的品种（货基/现金不计入）";
