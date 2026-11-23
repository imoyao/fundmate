/**
 * 账户详情页「区块清单」（section manifest，2026-11-22）。
 *
 * ## 为什么收口成清单
 *
 * 详情页的区块可见性原先散落在三处：`useLedgerOverview.isCompositionLedger`
 * （资产构成）、`LedgerDetailOverview.showComposition` / `showDepthAnalysis`。
 * 每加一种账户类型，就得同时记得改这几处，漏一处就会出现「账户类型已支持、
 * 但某个区块还是按旧判断显示/隐藏」的漂移。
 *
 * 清单把「某 ledger_type 显示哪些区块」收成**单一真相源**：各区块的 `v-if`
 * 只读这里，不再各自 `includes(...)` 硬编码类型名单。
 *
 * ## 关键：property（实物资产）不是「投资账户的残缺版」
 *
 * 实物账户（房产 / 汽车 / 黄金等）与净值型投资账户（stock / fund / e_account）
 * 是**两套心智**：
 * - 投资账户：份额 + 净值 + 盈亏 + 收益日历 + 收益归因 + 持仓穿透；
 * - 实物账户：盘点 + 成本 + 数量 + 资产明细（它没有净值、没有每日盈亏、
 *   没有持仓穿透可言，房产不在 `positions` 表里而在 `assets` 表里）。
 *
 * 此前 property 吃的是投资账户的完整骨架，于是整页空转：盈亏 / 当日收益 /
 * 收益日历 / 收益归因 / 持仓结构 / 穿透全是 `--` 或空面板，而真正该看的
 * 「这套房产值多少钱、有几套」反而不在页面上。真机：账户 id=8「住房信息记录」
 * （ledger_type=property）持仓 0 条、assets 1 条房产，页面却渲染出投资账户
 * 的一整套净值指标。
 */

/** 详情页区块键。与 `LedgerDetailOverview.vue` 里的锚点 / 区块一一对应。 */
export type LedgerDetailSection =
  | "overview" // 账本概览（总资产 + 指标格 + 资产构成）
  | "assetList" // 资产明细（property 专属：本账户的实物资产清单）
  | "cashLike" // 类现金
  | "calendar" // 收益日历
  | "attribution" // 收益归因
  | "depthAnalysis"; // 持仓结构 / 持仓穿透

/**
 * 各区块是否对某 ledger_type 可见。
 *
 * 说明（为什么这样分）：
 * - `overview` 恒真：总资产是通用概念，任何账户都有。
 * - `assetList` 仅 property：实物资产的核心是「明细盘点」，它不进 positions。
 * - `cashLike` 仅 stock / fund / e_account / bank：类现金（货基 / 逆回购 /
 *   账户现金）是资金账户的概念，实物账户没有「类现金」可言。
 * - `calendar` / `attribution` / `depthAnalysis` 仅 stock / fund / e_account：
 *   三者都需要「净值 + 盈亏」口径，property / bank 不适用。
 */
const SECTION_VISIBILITY: Record<LedgerDetailSection, readonly string[]> = {
  overview: ["stock", "fund", "e_account", "bank", "property", "family"],
  assetList: ["property"],
  cashLike: ["stock", "fund", "e_account", "bank"],
  calendar: ["stock", "fund", "e_account"],
  attribution: ["stock", "fund", "e_account"],
  depthAnalysis: ["stock", "fund", "e_account"]
};

/**
 * 某账户类型是否显示某区块。`ledger_type` 未知 / 空值时按**最保守**处理：
 * 净值类区块一律不显示（避免 property / bank 被误判成投资账户而渲染出
 * 空面板），`overview` 恒显示（总资产通用）。
 */
export function isSectionVisible(
  section: LedgerDetailSection,
  ledgerType: string | undefined | null
): boolean {
  if (section === "overview") return true;
  if (!ledgerType) return false;
  return SECTION_VISIBILITY[section].includes(ledgerType);
}

/**
 * 是否「投资类账户」（有净值 + 盈亏口径），等价于旧 `isCompositionLedger`。
 * 单独导出便于 `useLedgerOverview` 兼容旧调用方，避免把「资产构成是否可画」
 * 与「是不是投资账户」两个概念混为一谈。
 */
export function isInvestmentLedger(
  ledgerType: string | undefined | null
): boolean {
  return !!ledgerType && ["stock", "fund", "e_account"].includes(ledgerType);
}
