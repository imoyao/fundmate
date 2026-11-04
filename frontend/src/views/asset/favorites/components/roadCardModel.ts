/**
 * 未竟之蹊单卡的字段解析（#980 批 B6 从 `RoadCard.vue` 抽出）。
 *
 * 抽出的理由：这些函数原先是一串 computed，每个都在「查表 + 兜底」——
 * 兜底值散落在模板与脚本两处（模板写 `?? "资产"`、脚本写 `?? "观察中"`），
 * 改一处口径要翻两个地方。集中到本模块后，「缺省显示什么」成为可单测的事实，
 * 而不是靠读模板推断。
 *
 * 与 `../helpers` 的分工：helpers 管**数值与日期的展示口径**（涨跌幅、几天、复盘文案），
 * 本模块管**卡片自己的字段解析**（类型色 / 标签 / 胶囊文案 / 状态配色）。
 * 两边都是纯函数，不 import 任何带运行时依赖的模块 —— `asset_type` 的中文标签
 * 由调用方注入（`useEnumLabels` 会连带 `utils/http → router`，单测跑不动）。
 */
import type { WatchlistTag } from "@/api/watchlist";
import {
  ENTITY_COLOR,
  ENTITY_LABEL,
  HOLDING_STATE_LABEL,
  VENUE_LABEL
} from "../constants";
import { daysBetween, daysFromToday, reviewHintText } from "../helpers";

/** 类型色缺省（未在 ENTITY_COLOR 里登记的实体不染色，走中性文字） */
export const DEFAULT_ENTITY_COLOR = "var(--text-tertiary)";
/** 实体胶囊缺省文案 */
export const DEFAULT_ENTITY_LABEL = "资产";
/** 持仓状态胶囊缺省文案 */
export const DEFAULT_STATE_LABEL = "观察中";

/** 实体主色（封面色层与类型胶囊共用） */
export function entityColorOf(entity: string): string {
  return ENTITY_COLOR[entity] || DEFAULT_ENTITY_COLOR;
}

/** 实体胶囊文案 */
export function entityLabelOf(entity: string): string {
  return ENTITY_LABEL[entity] ?? DEFAULT_ENTITY_LABEL;
}

/** 持仓状态胶囊文案 */
export function stateLabelOf(holdingState: string): string {
  return HOLDING_STATE_LABEL[holdingState] ?? DEFAULT_STATE_LABEL;
}

/** 交易所前缀文案：未登记的 venue 原样返回（后端可能先上新市场），空值不显示 */
export function venueLabelOf(venue: string | null | undefined): string {
  return venue ? (VENUE_LABEL[venue] ?? venue) : "";
}

/**
 * `asset_type` 归一：返回空串表示「卡片不显示这一节」，否则返回小写键，
 * 由调用方交给 `useEnumLabels().assetTypeLabel` 翻成中文。
 *
 * `manager` 是域特有实体、不是通用 `asset_type`，在卡片上显示英文原键没有意义。
 */
export function normalizeAssetType(
  assetType: string | null | undefined
): string {
  const at = assetType?.toLowerCase();
  if (!at || at === "manager") return "";
  return at;
}

/**
 * 封面走势的口径标注：基金画净值、指数画点位、股票画价格。
 * 经理没有价格曲线，返回空串（`RoadSparkline` 不渲染标注）。
 */
const METRIC_KIND: Record<string, string> = {
  fund: "净值",
  index: "点位",
  stock: "价格"
};

export function metricKindLabelOf(entity: string): string {
  return METRIC_KIND[entity] ?? "";
}

/**
 * 状态胶囊配色（语义色，非涨跌）。
 *
 * 用常量表而不是每次 `computed` 重建 map：这三个色跟着状态走、与数据无关，
 * 没必要每帧重算。返回**新对象**而不是常量本身，避免调用方随手改到共享引用。
 */
const STATE_CHIP_TONE: Record<string, { bg: string; fg: string }> = {
  holding: { bg: "var(--brand-100)", fg: "var(--brand-700)" },
  watching: { bg: "var(--bg-soft)", fg: "var(--text-secondary)" },
  cleared: { bg: "var(--color-warning-20)", fg: "var(--text-secondary)" }
};

export function stateChipStyleOf(holdingState: string): {
  backgroundColor: string;
  color: string;
} {
  const tone = STATE_CHIP_TONE[holdingState] ?? STATE_CHIP_TONE.watching;
  return { backgroundColor: tone.bg, color: tone.fg };
}

/**
 * `tag_ids` → 标签对象。找不到的 id 直接丢弃（后端删标签后本地残留 id 是常态），
 * 顺序沿用 `tag_ids`（用户勾选顺序），不按标签表顺序重排。
 */
export function pickTags(
  tagIds: number[],
  tags: WatchlistTag[]
): WatchlistTag[] {
  return tagIds
    .map(id => tags.find(t => t.id === id))
    .filter((t): t is WatchlistTag => Boolean(t));
}

/** 复盘提醒文案（今天 / 逾期 N 天 / 还有 N 天）；无日期返回 null，由模板降级 */
export function reviewTextOf(nextReviewDate: string | null): string | null {
  return reviewHintText(nextReviewDate);
}

/** 是否临近复盘：7 天内（含已逾期）标为 due，模板据此上品牌色 */
export function isReviewDue(nextReviewDate: string | null): boolean {
  const days = daysFromToday(nextReviewDate);
  return days != null && days <= 7;
}

/** 关注天数（自 favorite_at 起）；日期缺失或非法返回 null，模板据此省掉这一段 */
export function favoriteDaysOf(favoriteAt: string | null): number | null {
  return daysBetween(favoriteAt);
}

/**
 * 对比数据条为空时的说明句。
 *
 * 经理与其它实体的「没数据」是两件事：经理本来就没有价格类指标（生涯数据在
 * 另一套接口里，接入中），而股票 / 基金 / 指数是真的还没攒够历史。混成一句
 * 「行情数据积累中」会让用户以为经理也该有行情。
 */
export function emptyMetricsText(entity: string): string {
  return entity === "manager" ? "经理生涯数据接入中" : "行情数据积累中";
}
