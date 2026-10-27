/**
 * 类型快捷胶囊栏的派生模型（自 WatchlistFilterBar 抽出，纯函数、零副作用）。
 *
 * 为什么单独成文件：这三个函数承载的是本页**两条容易被改坏的业务规则**——
 * 「持仓分组下收窄可见类型」（#2329）与「单选覆盖式切换」（#2199）。此前它们
 * 以 computed 内联在 .vue 的 script 里，只能靠端到端手点验证；抽成纯函数后
 * 由 `__tests__/quickTypeModel.spec.ts` 直接钉住边界。
 *
 * 本文件只做「从状态派生 UI 值」，不读也不写任何响应式源；所有收窄口径统一
 * 复用 watchlistAssetTypes.ts 的 narrowToHolding（该文件的 HOLDING_ASSET_TYPES
 * 是唯一真相源，禁止在此另写一份类型清单）。
 */
import { narrowToHolding } from "./watchlistAssetTypes";

/** 快捷胶囊项：value 为资产类型 key（或 'all'），label 已由调用方映射为中文 */
export interface QuickTypeOption {
  label: string;
  value: string;
}

/** 「全部」胶囊的固定 value（与后端 asset_type 池无冲突的哨兵值） */
export const QUICK_TYPE_ALL = "all";

/**
 * 构建胶囊选项：「全部」恒为首项 + 用户外露类型。
 *
 * @param exposed       用户偏好外露的资产类型 key（useWatchlistQuickFilters 单例）
 * @param isHoldingGroup 当前是否处于「持仓」分组
 * @param labelOf       资产类型 key → 中文 label（调用方传 assetTypeLabel，
 *                      后端 /enums/asset_type 为唯一真相源，禁止在此手抄映射）
 *
 * #2329：持仓分组下必须收窄——外露列表来自跨设备同步的用户偏好，用户一旦把
 * `manager` 配进去，所有分组都会露出它；而 manager / portfolio 按后端定义
 * 「不进 positions」，在持仓视图下永远筛不出东西，点了只得到空列表。
 * `stock` / `fund` 是 PINNED 常驻项，收窄不会摘掉它们。
 *
 * 注意：本函数**只决定哪些胶囊可见**，不改已生效的筛选状态（唯一写入点是
 * index.vue 的 applyHoldingTypeConstraint）。
 */
export function buildQuickTypeOptions(
  exposed: readonly string[],
  isHoldingGroup: boolean,
  labelOf: (value: string) => string
): QuickTypeOption[] {
  const visible = isHoldingGroup ? narrowToHolding(exposed) : exposed;
  return [
    { label: "全部", value: QUICK_TYPE_ALL },
    ...visible.map(v => ({ label: labelOf(v), value: v }))
  ];
}

/**
 * 当前单选激活项派生：
 * - 无类型筛选 → 'all'（高亮「全部」）；
 * - 恰好单选一个**当前可见**的胶囊 → 该类型；
 * - 多选 / 选了不可见（未外露或已被持仓分组收窄掉）的类型 → ''（无高亮，
 *   组合态，看「筛选」入口的角标）。
 *
 * #2329：判据对**实际渲染的那一串选项**求值，而非裸外露列表——否则会出现
 * 「高亮了一个根本不渲染的胶囊」这种高亮与可见性对不上的状态。
 */
export function resolveQuickActiveValue(
  selected: readonly string[],
  options: readonly QuickTypeOption[]
): string {
  if (selected.length === 0) return QUICK_TYPE_ALL;
  if (selected.length === 1 && options.some(o => o.value === selected[0])) {
    return selected[0];
  }
  return "";
}

/**
 * 点击胶囊后的下一次筛选值（单选覆盖式）：
 * - 「全部」→ 清空类型筛选；
 * - 再点当前唯一生效项 → 取消回「全部」；
 * - 其余 → 覆盖为该项。
 *
 * 与「筛选」Popover 内多选正交：此处只能单维度，复杂组合进 Popover。
 */
export function nextQuickSelection(
  selected: readonly string[],
  value: string
): string[] {
  if (value === QUICK_TYPE_ALL) return [];
  if (selected.length === 1 && selected[0] === value) return [];
  return [value];
}
