/**
 * 对账中心专用术语表（2026-11-07 第二轮，owner 逐条反馈后的收口）。
 *
 * ## 为什么不改 `@/constants` 的 DISCREPANCY_TYPE_LABELS
 * 那张表是全站共享（`DiscrepancyBanner` 也用），值是「数量 / 成本 / 资金 / 孤儿」
 * 这类**存储枚举名**。对账中心要回答的是「哪里对不上」，不是「这是哪种枚举」；
 * 直接改全站映射会让别的页面文案一起变。故本页单独维护展示层术语，
 * 全站表保持不动（避免 #2958 那种「一处改、多处漂移」）。
 */

/** 差异类型 → 用户能看懂的「问题」。未知码也不许露英文枚举。 */
export const DISCREPANCY_ISSUE_LABEL: Record<string, string> = {
  quantity: "份额对不上",
  cost: "成本对不上",
  cash: "资金对不上",
  orphan: "有持仓、缺流水",
  // #3125：不是「对不上」而是「没法对」——持仓份额来自券商快照，流水只覆盖了一部分，
  // 缺基准时两边本就不该互校，否则用户以为要自己补一笔不存在的交易。
  // 适用面由 #3127 收窄：流水净额 ≤ 0 却仍有份额属幽灵持仓/超卖，仍归 quantity。
  no_anchor: "没有可对照的流水，核对不了"
};

export function discrepancyIssue(type: string | null | undefined): string {
  if (!type) return "记录有出入";
  return DISCREPANCY_ISSUE_LABEL[type] ?? "记录有出入";
}

/**
 * 特殊标的码 → 中文。
 * 后端 `core/asset_types.py:63` 早有 `'cash': '现金'`，支付宝解析器写 `'__CASH__'`
 * （`importer/parsers/alipay_fund.py:191-199`）；此前前端 `reconGroupTitle()`
 * 原样返回 symbol，界面就露出裸 `cash`。key 一律小写，查询时先 toLowerCase()。
 */
export const SPECIAL_SYMBOL_LABELS: Record<string, string> = {
  cash: "现金",
  _cash: "现金",
  __cash__: "现金"
};

export function specialSymbolLabel(
  symbol: string | null | undefined
): string | null {
  const raw = symbol?.trim();
  if (!raw) return null;
  return SPECIAL_SYMBOL_LABELS[raw.toLowerCase()] ?? null;
}

/** 这种标的不是一只产品，必须说明，避免用户去找一只叫 cash 的基金 */
export const CASH_SYMBOL_HINT = "这不是一只产品，是账户里的现金余额";

/** 差异表列名：一次改齐，不在组件里各写一份（场景化：说券商流水与账本各剩多少） */
export const DISC_COLUMN_LABELS = {
  product: "产品",
  issue: "问题",
  expected: "券商流水应剩",
  actual: "账本现记",
  diff: "差",
  status: "状态",
  action: "操作"
} as const;

/** 临门一脚的风险句：只在抽屉按钮旁或二次确认里出现，列表态不许带「不可撤销」 */
export const ACTION_RISK_HINTS = {
  eaccountCover: "归因覆盖会删除渠道原记录，不可撤销。",
  ghostDelete: "删除其中一笔会重算持仓，无法撤销。"
} as const;
