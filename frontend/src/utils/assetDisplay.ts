// src/utils/assetDisplay.ts
// 资产展示辅助：统一「组合类标的」副标题（基金经理所属公司 / 投顾组合平台·主理人·策略）。
//
// 为什么收口到这里：同一段拼接逻辑原本散落在
//   - views/asset/watchlist/columnRenderers.tsx（compositeSubMeta）
//   - components/QuickEntry/AddToWatchlistModal.vue（rowColumns）
//   - components/Watchlist/GroupItemsDialog.vue（新增需求）
// 三处手写会导致平台/主理人/公司显示口径漂移，故提取为单一纯函数。
//
// 单一真相源仍在后端：AdvisorPortfolio.platform / host / strategy_type，
// FundManager.company；本函数只负责展示层的兜底与拼接。

import {
  getAdvisorPlatformLabel,
  isCompositeAssetType
} from "@/constants/advisorPlatform";

/** 可用于计算副标题的最小元信息集合 */
export interface AssetDisplayMeta {
  asset_type?: string | null;
  manager_company?: string | null;
  advisor_platform?: string | null;
  advisor_host?: string | null;
  advisor_strategy_type?: string | null;
}

/**
 * 返回资产副标题：
 * - 基金经理 → 所属公司（如「易方达基金管理有限公司」）
 * - 投顾组合 → 平台 · 主理人 · 策略类型（如「且慢 · 基民柠檬」）
 * - 股票/基金/指数/可转债等普通标的 → 空串（编码由调用方直接展示）
 *
 * 空值会被过滤，避免副标题出现无意义的「·」或空白片段。
 */
export function buildAssetSubtitle(meta: AssetDisplayMeta): string {
  const type = (meta.asset_type || "").toLowerCase();

  if (type === "manager") {
    return meta.manager_company || "";
  }

  if (isCompositeAssetType(type)) {
    return [
      getAdvisorPlatformLabel(meta.advisor_platform),
      meta.advisor_host,
      meta.advisor_strategy_type
    ]
      .filter((v): v is string => Boolean(v))
      .join(" · ");
  }

  return "";
}

/**
 * 是否应当在当前位置显示交易代码（如 SH600519 / 001414）。
 * 组合类标的（投顾组合 ZHxxxx / 基金经理 MGR_xxx）的平台原生码对用户无意义，应隐藏。
 */
export function shouldShowAssetCode(meta: AssetDisplayMeta): boolean {
  return !isCompositeAssetType(meta.asset_type);
}
