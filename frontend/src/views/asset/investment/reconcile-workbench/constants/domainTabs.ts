/**
 * 对账工作台 Tab 定义（§6.3）
 *
 * #980 拆分：自 reconcile-workbench/index.vue 抽出为页面级常量（constants/），
 * 零行为变更——字段与取值与原内联数组逐字一致。
 * #2151：新增域 D「跨账本重复交易」（幽灵重复），联合类型随之扩展。
 *
 * ⚠️ 这里刻意**不导出** `WorkbenchDomainKey = "A" | "B" | "C" | "D"` 之外的东西：
 * 域标识是「页面级」概念（与 `useReconDraft.ts` 的 `ReconDomain` 是两码事——
 * 后者是导入草稿的路由标签，只有 A/B/C，本次不动它）。
 */

/** 域标识：A=E账户 / B=持仓快照 / C=对账单导入 / D=跨账本重复交易 */
export type WorkbenchDomainKey = "A" | "B" | "C" | "D";

export interface WorkbenchDomainTab {
  key: WorkbenchDomainKey;
  label: string;
  title: string;
  description: string;
  badgeType: string;
  status: "ready" | "planned";
  statusLabel: string;
  placeholderHint: string;
  desc: string;
  links: Array<{ to: string | { name: string }; label: string }>;
}

export const domainTabs: WorkbenchDomainTab[] = [
  {
    key: "A",
    label: "E账户对账",
    title: "E账户对账（域 A）",
    description: "E账户官方快照 vs 渠道持仓",
    badgeType: "e_account",
    status: "ready",
    statusLabel: "已接入",
    placeholderHint: "复用既有对账链路",
    desc: "E账户对账已上线，P2 迁入本工作台统一入口。本期保持原入口可用。",
    links: [{ to: { name: "InvestmentReconcile" }, label: "前往原对账中心" }]
  },
  {
    key: "B",
    label: "持仓快照",
    title: "持仓快照一致性（域 B）",
    description: "流水推演理论持仓 vs 实际持仓",
    badgeType: "fund",
    status: "ready",
    statusLabel: "已接入",
    placeholderHint: "数量差异 + 孤儿检测",
    desc: "P1 已接入：理论持仓 = 流水重建净份额，比对实际持仓数量差异与孤儿。",
    links: []
  },
  {
    key: "C",
    label: "对账单导入",
    title: "对账单/交割单导入对账（域 C）",
    description: "导入的券商/基金对账单 vs 系统持仓",
    badgeType: "fund",
    status: "planned",
    statusLabel: "P1 规划",
    placeholderHint: "本期占位",
    desc: "P1 落地：导入 commit 后自动触发对账，差异进本工作台补录。",
    links: [
      { to: "/inventory/investment/import", label: "前往交易导入" },
      // 目的地页面 #1788 已改名「导入持仓快照」，链接文案跟着对齐，避免点过去标题对不上
      { to: "/investment/holding-import", label: "前往导入持仓快照" }
    ]
  },
  {
    key: "D",
    label: "跨账本重复",
    title: "跨账本重复交易（域 D）",
    description: "同一笔交易疑似出现在多个账本",
    badgeType: "fund",
    status: "ready",
    statusLabel: "已接入",
    placeholderHint: "逐组核对，保留一份",
    desc: "导入去重按账本隔离后，同一份交割单在多个账本各导一次会让交易与收益翻倍。本域列出疑似重复组及组内明细，供逐组核对。",
    links: []
  }
];
