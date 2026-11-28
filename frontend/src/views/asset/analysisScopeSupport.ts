/**
 * 复盘页「区块 × 口径档位」的能力声明（唯一真相源）。
 *
 * ## 为什么需要这张表
 *
 * 页面能开放哪几档，取决于**每一块都算得出来**的那几档：
 *
 * - 摆出组合档、而页面上有 4 块只能返回家庭级 ⇒ 用户看到的是半成品；
 * - 反过来偷偷让那几块退回家庭级 ⇒ **静默错口径**，比半成品危险得多。
 *
 * 所以档位不是硬编码，而是这张表的交集。将来某块补上组合档，改这里一行即可扩档；
 * 想给某块「临时凑合」必须改表，改表就会被评审看见。
 *
 * ## 当前结论（2026-11-28）
 *
 * **只有家庭 / 账户两档。** 区间表现 / 收益归因 / 持仓结构 / 资金流动 / 货基
 * 五块本身支持组合档（`kinds` 如实写三档），其余四块的后端空洞按 D1 的取舍留到三期。
 *
 * 三期 D 已补三处（D134）：清仓复盘 `cleared-cycles` / 浮亏回本 `/positions/` /
 * 收益日历 `pnl-calendar` 都接了 `portfolio_id`，**后端能算组合档了**，但本表仍写两档——
 * 净值曲线（`snapshots`）要等 `asset_snapshots` 长出组合维度，而**档位取交集**，
 * 少一块就整页不开；前端接线（组合下拉 + 逐块传 `portfolioId`）与表内扩档放在一起做，
 * 那才是本表应当变动的地方。
 *
 * ## 维护约定
 *
 * 新增区块必须同时登记（`analysisScopeSupport.spec.ts` 钉住「页面真实渲染的
 * 区块 == 表内条目」）。登记时写**实际验证过**的档位，不要写「应该能」。
 */

import type { ScopeKind } from "@/composables/analysisScope/toScopeProps";

export interface SectionScope {
  /** 中文名，报错信息与单测里用 */
  label: string;
  /** 该区块**真的能算**的档位（后端端点的实际能力，不是前端愿望） */
  kinds: readonly ScopeKind[];
}

/** 档位从宽到窄的固定顺序，交集结果按它排（保证第一个是 family） */
const KIND_ORDER: readonly ScopeKind[] = ["family", "ledger", "portfolio"];

export const ANALYSIS_SECTION_SCOPE: Record<string, SectionScope> = {
  overview: { label: "收益概览", kinds: ["family", "ledger"] },
  excess: { label: "区间表现", kinds: ["family", "ledger", "portfolio"] },
  netWorth: { label: "资产净值走势", kinds: ["family", "ledger"] },
  cashFlow: { label: "资金流动", kinds: ["family", "ledger", "portfolio"] },
  calendar: { label: "收益日历", kinds: ["family", "ledger"] },
  cycles: { label: "清仓复盘", kinds: ["family", "ledger"] },
  breakEven: { label: "浮亏回本", kinds: ["family", "ledger"] },
  structure: { label: "持仓结构", kinds: ["family", "ledger", "portfolio"] },
  attribution: { label: "收益归因", kinds: ["family", "ledger", "portfolio"] },
  moneyFund: { label: "货币基金收益", kinds: ["family", "ledger", "portfolio"] }
};

/**
 * 本页可开放的档位 = 所有区块都支持的交集。
 *
 * 空表返回 `["family"]`（家庭级恒可用）：宁可只剩一档，也不要摆出一个
 * 「有按钮但会取错数」的档位。
 */
export function commonAnalysisKinds(
  table: Record<string, SectionScope> = ANALYSIS_SECTION_SCOPE
): ScopeKind[] {
  const sections = Object.values(table);
  if (sections.length === 0) return ["family"];
  return KIND_ORDER.filter(kind => sections.every(s => s.kinds.includes(kind)));
}
