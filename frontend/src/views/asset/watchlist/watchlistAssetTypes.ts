/**
 * 自选场景的资产类型 key 池（业务选择属前端职责，单列于此供多处共用）。
 *
 * 消费方：
 * - 筛选弹层类型多选（FilterPanelBody）；
 * - 主界面快捷筛选外露类型自定义（#1449），偏好值合法性也以本池为准。
 *
 * 中文 label 统一走 useEnumLabels.assetTypeLabel（后端 /enums/asset_type 为
 * 唯一真相源，禁止手抄映射），本文件只管 key 清单。
 */
export const WATCHLIST_ASSET_TYPE_OPTIONS = [
  "stock",
  "etf",
  "fund",
  "money_fund",
  "bond",
  "index",
  "crypto",
  "reverse_repo",
  // #1285 品类视图：经理 / 投顾组合也需可筛选（此前缺失 → 无法进入其品类视图）
  "manager",
  "portfolio"
] as const;

export type WatchlistAssetType = (typeof WATCHLIST_ASSET_TYPE_OPTIONS)[number];

/**
 * 「持仓」分组下语义成立的资产类型（#2329 单一真相源）。
 *
 * 持仓只来自 positions 表，而 manager / portfolio 按后端 `core/asset_types.py` 的
 * 定义是「可自选观察的非交易实体，**不进 positions**」——它们在持仓视图下永远
 * 筛不出东西，却会在筛选器里露出，点了只得到一个空列表（用户实测：持仓分组下
 * 冒出「基金经理」胶囊）。
 *
 * 为什么是这 5 个（含 index / etf / bond）：
 * - 早期只留 stock / fund，导致 ETF / 可转债 / 指数的持仓类型筛选形同虚设（#1449）；
 * - `index.vue` 当时的集合里还混了一个 `convertible`，但**该 key 根本不是合法
 *   asset_type**（后端 `bond` 即可转债，见 core/asset_types.py 的 bond 澄清），
 *   永远不会出现在任何筛选值里，属纯死项，本次一并清掉。
 *
 * ⚠️ 本常量是「持仓分组允许哪些类型」的唯一判据。历史上同一件事写过三份且互相
 * 不一致（切组过滤 6 项 / 弹层可选集 2 项 / 快捷胶囊栏完全不判），新增消费方
 * 一律复用本常量，禁止再写第四份。
 */
export const HOLDING_ASSET_TYPES: readonly WatchlistAssetType[] = [
  "stock",
  "fund",
  "etf",
  "bond",
  "index"
] as const;

/** 持仓分组下的资产类型判定（Set 查表，供 .filter / .includes 热路径使用） */
export const HOLDING_ASSET_TYPE_SET: ReadonlySet<string> = new Set(
  HOLDING_ASSET_TYPES
);

/**
 * 把一份资产类型清单收窄为「持仓分组语义下成立」的子集（#2329 单一真相源的执行口）。
 *
 * 为什么必须是**被调用的纯函数**而不是各处各写一份 filter：
 * 历史上同一件事散成三处各自 inline 的表达式，于是三处可以各自漂移——
 * 切组过滤 6 项、弹层可选集 2 项、快捷胶囊完全不判。前两次「静态守卫」也栽在
 * 同一处：断言写成「文件里出现常量名」，而**光一条 import 就能让它通过**，
 * 于是「导入了却没真正用」的回退完全咬不住（探针实测 P2/P3/P4 全 MISS）。
 *
 * 现在三处调用方都必须真的调用本函数，静态守卫也相应断言**调用点**
 * （`narrowToHolding(` 带括号，import 行匹配不到）。
 *
 * @param list 任意资产类型清单（类型池全集 / 用户外露列表 / 已生效筛选值）
 * @returns 落在 HOLDING_ASSET_TYPES 内的子集；保持入参顺序，不改入参
 */
export function narrowToHolding<T extends string>(list: readonly T[]): T[] {
  return list.filter(t => HOLDING_ASSET_TYPE_SET.has(t));
}

/**
 * 类型快捷切换器的默认外露类型（#1449）：
 * 用户自定义存 user_preferences.watchlist_quick_filters（跨设备同步），
 * 无偏好 / 偏好损坏时回退本默认值。
 */
export const DEFAULT_QUICK_FILTER_TYPES: readonly WatchlistAssetType[] = [
  "stock",
  "fund",
  "etf",
  "bond"
];

/**
 * 常驻外显类型（#2199 用户拍板）：股票、基金是最高频的两个基础品类，
 * 无论用户偏好如何配置都恒在外露列表最前两位——注入由 useWatchlistQuickFilters
 * 的应用 / 保存路径负责（normalizeQuickFilters 仍保持纯校验，不注入），
 * 弹窗内对应 checkbox disabled 恒勾选。
 */
export const PINNED_QUICK_TYPES: readonly WatchlistAssetType[] = [
  "stock",
  "fund"
];
