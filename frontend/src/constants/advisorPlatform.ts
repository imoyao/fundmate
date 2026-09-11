// frontend/src/constants/advisorPlatform.ts
// 投顾组合平台枚举 → 中文名；组合类标的（投顾组合 / 基金经理）判定。
//
// 为什么收口到这里：平台中文名原先只存在于
// views/asset/watchlist/columnRenderers.tsx 内部常量里，而「添加自选」弹窗
// （components/QuickEntry/AddToWatchlistModal.vue）同样需要「按平台展示」。
// 复制第二份必然漂移（#1171 枚举一致性教训），故统一从此处取用。
//
// 单一真相源仍在后端：AdvisorPortfolio.platform（QIEMAN/DANJUAN/TIANTIAN/YINGMI）。

/** 投顾组合平台枚举 → 中文（后端 AdvisorPortfolio.platform） */
export const ADVISOR_PLATFORM_LABELS: Record<string, string> = {
  QIEMAN: "且慢",
  DANJUAN: "蛋卷基金",
  TIANTIAN: "天天基金",
  YINGMI: "盈米"
};

/** 平台枚举 → 中文；未知值原样兜底（新增平台未同步映射时不至于空白），空值返回空串 */
export function getAdvisorPlatformLabel(platform?: string | null): string {
  if (!platform) return "";
  return ADVISOR_PLATFORM_LABELS[platform] || platform;
}

/**
 * 组合类标的（非交易实体）的资产类型集合，与后端 asset_types 单一来源对齐。
 *
 * 为什么单列出来：这类标的**没有对外有意义的交易代码**——投顾组合用平台原生码
 * （且慢 ZHxxxx、天天基金 tgCode）、基金经理用 MGR_ 派生码，对用户都无意义；
 * 其中天天基金的 tgCode 属平台私有标识，更是不应出现在 UI 上。
 * 其识别信息只能由「名称 + 品类 +（平台 / 主理人 / 所属公司）」承担。
 */
export const COMPOSITE_ASSET_TYPES = new Set(["portfolio", "manager"]);

/** 资产类型是否属组合类标的（大小写不敏感；空值按普通标的处理） */
export function isCompositeAssetType(assetType?: string | null): boolean {
  return COMPOSITE_ASSET_TYPES.has((assetType || "").toLowerCase());
}
