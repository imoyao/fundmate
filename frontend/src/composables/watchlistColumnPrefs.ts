/**
 * 自选列偏好的「本地 ↔ 云端」合并原语（#1337 方案 B，从 useWatchlistColumnVisibility 抽出）。
 *
 * WHY 独立文件：合并策略是纯函数（无 IO、无 Vue 状态），抽出后可被 vitest 直接单测，
 * 而不必连带加载 composable 的 localforage / http / columnDefs 依赖链。
 */

/** 列设置持久化结构（本地与云端共用；updated_at 仅本地存，云端由服务端时间戳维护） */
export interface ColumnSettings {
  hidden: string[];
  /**
   * 被用户「显式开启」的默认隐藏列（defaultHidden=true）。
   * 与 hidden 分开存：hidden 记「用户关掉的」，shown 记「用户打开的」，二者互斥。
   * 旧缓存缺 shown 字段时按「从未开启」处理，新增列保持隐藏（不打扰老用户）。
   */
  shown?: string[];
  /** 可拖拽列的自定义顺序（key 数组）；缺省 = 默认定义顺序（#992） */
  order?: string[];
  /** 本地最后修改时间（ms epoch）；上云前剥离，云端比对用服务端 updated_at */
  updated_at?: number;
}

/** 一侧（本地或云端）的偏好快照：配置 + 该侧最近修改时间 */
export interface PrefStamp {
  settings: ColumnSettings;
  ts: number;
}

/**
 * 「最近修改时间取胜」（#1337 卡面建议的合并策略）：
 * - 只有一侧有值 → 用那一侧；
 * - 两侧都有 → ts 更新者胜（相等时本地胜，避免无谓的云端覆盖写）。
 * 时钟偏差容忍度为秒级：单向收敛（胜者回写另一侧一次），不做双向同步环。
 */
export function pickNewer(
  local: PrefStamp | null,
  cloud: PrefStamp | null
): PrefStamp | null {
  if (!local) return cloud;
  if (!cloud) return local;
  return cloud.ts > local.ts ? cloud : local;
}

/** 上云 payload：剥离本地时钟字段 updated_at（云端时间戳由服务端维护，不接受客户端篡改） */
export function stripStamp(
  settings: ColumnSettings
): Omit<ColumnSettings, "updated_at"> {
  const { updated_at: _ignored, ...rest } = settings;
  return rest;
}
