/**
 * 大盘指数条的纯计算口径（#watchlist 顶部指数条）。
 *
 * WHY 单独抽一层：
 *   跑马灯要靠 DOM 测量才知道「溢没溢出」，但「要不要动」「一圈多久」这两条
 *   口径本身是纯数学，必须能单测——vitest 跑在 node 环境，测不了
 *   ResizeObserver / getBoundingClientRect。故 DOM 侧只留 `useIndexBarMarquee`，
 *   判据全部落在这里。
 */

import type { IndexCatalogEntry } from "@/views/asset/watchlist/composables/indexCatalog";

/**
 * 折叠态单个指数的展示模型（父组件负责取数与格式化，子组件只渲染）。
 *
 * 把格式化后的字符串下发，是为了让跑马灯组件不依赖 `useIndexBarQuotes`：
 * 它只关心「一排等宽可点的东西」，与行情来源解耦。
 */
export interface IndexTickerItem {
  meta: IndexCatalogEntry;
  name: string;
  price: string;
  pct: string;
  /** 语义色 class：is-rise / is-fall / is-flat */
  trend: string;
}

/**
 * 单个指数最多可同时展示的数量。
 *
 * 上限 8 有两条硬约束，不是随手取的：
 *   1. **请求量**：`useIndexBarQuotes` 每 30s 对每个指数各发一次东财分时请求，
 *      N 个指数 = N 请求/30s；超过 8 个就该先做批量分时接口。
 *   2. **展开态高度**：展开是网格换行（每行约 119px），8 个恰好两行（+139px），
 *      「我的持仓」汇总条与自选表格仍在首屏；12 个起会变成三行把表格推出视口。
 */
export const MAX_INDEX_COUNT = 8;

/**
 * 跑马灯恒定线速度（px/s）。
 *
 * 刻意用**恒定速度**而不是固定一圈时长：固定时长会让「选得越多跑得越快」，
 * 那正是紧迫感的来源。28px/s 约等于每个指数停留 5–6 秒——慢到不催人，
 * 又快到「在动」可被察觉。
 */
export const MARQUEE_SPEED_PX_PER_SEC = 28;

/** 可用速度区间（仅供注释与调试参照，不对外暴露成设置项） */
export const MARQUEE_MIN_SPEED_PX_PER_SEC = 20;
export const MARQUEE_MAX_SPEED_PX_PER_SEC = 40;

/** 亚像素容差：内容宽最多只比容器宽 1px 时不算溢出 */
const OVERFLOW_TOLERANCE_PX = 1;

/**
 * 内容是否溢出到需要用跑马灯承载。
 *
 * 不溢出时一律静态——4 个指数一屏放得下还晃来晃去，是纯噪音。
 */
export function shouldMarquee(
  contentWidth: number,
  containerWidth: number
): boolean {
  if (!Number.isFinite(contentWidth) || !Number.isFinite(containerWidth)) {
    return false;
  }
  if (containerWidth <= 0) return false;
  return contentWidth > containerWidth + OVERFLOW_TOLERANCE_PX;
}

/**
 * 一圈所需秒数 = 内容宽 ÷ 恒定速度。
 *
 * 速度非法（0 / 负数 / NaN）时回落到默认速度，避免算出 Infinity 让动画卡死。
 */
export function marqueeDurationSeconds(
  contentWidth: number,
  speed: number = MARQUEE_SPEED_PX_PER_SEC
): number {
  if (!Number.isFinite(contentWidth) || contentWidth <= 0) return 0;
  const safeSpeed =
    Number.isFinite(speed) && speed > 0 ? speed : MARQUEE_SPEED_PX_PER_SEC;
  return contentWidth / safeSpeed;
}
