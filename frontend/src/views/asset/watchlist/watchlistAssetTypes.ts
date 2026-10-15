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
