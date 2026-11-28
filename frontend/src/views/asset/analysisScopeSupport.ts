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
 * **只有家庭 / 账户两档。** 组合档的四个空洞（净值曲线 `snapshots` 无
 * `portfolio_id`、清仓复盘 `cleared-cycles` 只认 `ledger_id`、浮亏回本走
 * `/positions/` 同理、收益日历不在本页）都属后端能力缺口，按 D1 的取舍留到三期。
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
  netWorth: { label: "资产净值走势", kinds: ["family", "ledger"] },
  cashFlow: { label: "资金流动", kinds: ["family", "ledger", "portfolio"] },
  cycles: { label: "清仓复盘", kinds: ["family", "ledger"] },
  breakEven: { label: "浮亏回本", kinds: ["family", "ledger"] },
  structure: { label: "持仓结构", kinds: ["family", "ledger", "portfolio"] },
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
