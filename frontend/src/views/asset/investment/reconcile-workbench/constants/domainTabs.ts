/**
 * 对账中心 Tab 定义（§6.3）
 *
 * #980 拆分：自 reconcile-workbench/index.vue 抽出为页面级常量（constants/），
 * #2151：新增域 D「跨账本重复交易」（幽灵重复），联合类型随之扩展。
 * 2026-10-28：域 C 接入真实差异列表，删掉 `status` / `statusLabel` / `placeholderHint`
 * 三个「工程内部状态」字段——它们曾让域 C 在功能已通的情况下对外自称
 * 「P1 规划 / 本期占位」，用户点进去发现能用，文案与事实自相矛盾。界面上不再出现
 * 「这个域做到第几期」这类只有开发者关心的话。
 *
 * ⚠️ 这里刻意**不导出** `WorkbenchDomainKey = "A" | "B" | "C" | "D" | "E"` 之外的东西：
 * 域标识是「页面级」概念（与 `useReconDraft.ts` 的 `ReconDomain` 是两码事——
 * 后者是导入草稿的路由标签，只有 A/B/C，本次不动它）。
 */

/** 域标识：A=E账户 / B=持仓快照 / C=对账单导入 / D=跨账本重复交易 / E=分红未记扣税 */
export type WorkbenchDomainKey = "A" | "B" | "C" | "D" | "E";

export interface WorkbenchDomainEntryLink {
  to: string | { name: string };
  label: string;
}

export interface WorkbenchDomainTab {
  key: WorkbenchDomainKey;
  label: string;
  title: string;
  description: string;
  badgeType: string;
  /**
   * 域内引导区（目前只有域 C 用）：说清「这个域的入口动作是什么」，
   * 并把入口做成正式按钮。缺省时域内直接就是列表。
   */
  entry?: {
    title: string;
    hint: string;
    links: WorkbenchDomainEntryLink[];
  };
}

export const domainTabs: WorkbenchDomainTab[] = [
  {
    key: "A",
    label: "E账户对账",
    title: "E账户对账",
    description: "E账户官方快照 vs 渠道持仓",
    badgeType: "e_account"
  },
  {
    key: "B",
    label: "持仓快照",
    title: "持仓快照一致性",
    description: "流水推演理论持仓 vs 实际持仓",
    badgeType: "fund"
  },
  {
    key: "C",
    label: "对账单导入",
    title: "对账单导入核对",
    description: "导入交割单后自动比对孤儿持仓",
    badgeType: "fund",
    entry: {
      title: "导入交割单后自动核对",
      // 措辞边界：域 C 后端只做孤儿检测，不做数量比对——不能写成「全面对账」，
      // 否则用户会以为差额也能在这里看到（数量差异在域 B）。
      hint: "提交导入后系统会自动跑一次对账：有持仓、却没有对应交易流水的，会列在下方等你补录或忽略。",
      links: [
        { to: "/inventory/investment/import", label: "前往交易导入" },
        // 目的地页面 #1788 已改名「导入持仓快照」，链接文案跟着对齐，避免点过去标题对不上
        { to: "/investment/holding-import", label: "导入持仓快照" }
      ]
    }
  },
  {
    key: "D",
    label: "跨账本重复",
    title: "跨账本重复交易",
    description: "同一笔交易疑似出现在多个账本",
    badgeType: "fund"
  },
  {
    key: "E",
    label: "分红未扣税",
    title: "分红未记扣税",
    // 措辞注意：本域不做「替你算税」，只指出哪几笔对不上账。税率取决于买入批次持有期，
    // 本系统只有聚合持仓，反推出来的是会被券商否掉的猜测（见后端 dividend_tax_service）。
    description: "有现金分红，该年账上却没有扣税流水",
    badgeType: "fund"
  }
];
