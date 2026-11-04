// 搜索结果行 / 已选卡片主行的三列取值（#980 拆分，源自 AddToWatchlistModal.vue 的 rowColumns）。
//
// 纯函数：给定一条搜索结果 → { name, sub, type, typeKey }，不碰组件状态，故可单测。
//
// ⚠️ 已知债（本轮**刻意不改**）：`@/utils/assetDisplay` 的 buildAssetSubtitle 是同口径的
// 单一真相源，其文件头注释已把本文件原先的 rowColumns 列为「应被收口的第三处」。
// 但收口会改变组合类的拼接细节（属于有视觉变更的重构），按 #980「零视觉变更」纪律，
// 本轮只做搬运；合并到 assetDisplay 应单独一轮 + 截图对齐。
import {
  getAdvisorPlatformLabel,
  isCompositeAssetType
} from "@/constants/advisorPlatform";
import { getTypeLabel } from "@/constants/assetType";
import { getVenueLabel } from "@/constants/market";
import type { AssetSearchExtra } from "@/api/search";

export interface SearchAssetOption {
  symbol: string;
  name: string;
  market: string;
  type?: string;
  venue: string;
  /** 品种差异化展示字段（#1285）：组合类的 platform/host、经理的 company 等。
      原先在 remoteSearch 映射时被丢弃，导致弹窗无法按「平台」而非「编码」展示。 */
  extra?: AssetSearchExtra;
  searchType?: "sec" | "fund";
  subscription_rate?: number;
  is_money_fund?: boolean;
  code?: string;
}

// ── 展示派生（组合类标的不展示平台原生码，见 @/constants/advisorPlatform）──

/** 品类中文标签（后端 asset_type → 中文，如 portfolio → 投顾组合） */
export const typeLabelOf = (item: SearchAssetOption): string =>
  getTypeLabel(item.type || "");

/** 交易场所标签（EXCHANGE 场内 / OTC 场外；空串＝无市场实体，不展示） */
export const venueLabelOf = (item: SearchAssetOption): string =>
  item.venue ? getVenueLabel(item.venue) : "";

/**
 * 搜索结果 / 已选信息卡主行：方案 A——名称统一为主视觉，次要锚点(灰)置右，类型配色最右。
 * 所有品种行内结构完全一致，混合列表不再「各是各的」：
 * - 带编码品种（股票/基金/ETF/指数/可转债/加密等）：名称 | 编码 | 类型
 * - 组合类（基金经理/投顾）：名称 | 平台·主理人/公司 | 类型
 *   平台原生码（且慢 ZHxxxx / 天天基金 tgCode）对用户无意义，整段不展示，
 *   由名称 + 平台/主理人承担（见 @/constants/advisorPlatform）。
 */
export interface RowColumns {
  /** 主视觉：资产名称。所有品种统一加粗主色、左对齐占满、超长省略 */
  name: string;
  /** 次要锚点：编码 / 平台·主理人 / 市场。灰色小字，无则不展示 */
  sub?: string;
  /** 类型中文标签（最右 pill 文本） */
  type: string;
  /** 原始 asset_type，用于类型 pill 按品种配色 */
  typeKey: string;
}
export const rowColumns = (item: SearchAssetOption): RowColumns => {
  const extra = item.extra ?? {};
  const type = typeLabelOf(item);
  const typeKey = item.type || "";
  if (isCompositeAssetType(item.type)) {
    if (item.type === "manager") {
      return {
        name: item.name,
        sub: extra.company || undefined,
        type,
        typeKey
      };
    }
    const sub = [getAdvisorPlatformLabel(extra.platform), extra.host]
      .filter((v): v is string => Boolean(v))
      .join(" · ");
    return { name: item.name, sub: sub || undefined, type, typeKey };
  }
  return { name: item.name, sub: item.symbol || undefined, type, typeKey };
};
