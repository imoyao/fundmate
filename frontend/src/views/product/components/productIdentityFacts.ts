// frontend/src/views/product/components/productIdentityFacts.ts
/**
 * 识别卡事实项的可见性口径（#2228）。
 *
 * 识别卡（`ProductIdentityCard.vue`）只放**事实项**，其中「代码」一项对**组合 / 经理**两类
 * 没有意义 —— 它们的 `symbol` 是**内部编码**，不是用户能拿去用的代码：
 *
 * - 经理：`MGR_98CE0328FFF1`（基金经理编码，见 `services/product_identity.py`）
 * - 投顾组合：平台原生码（如 `ZH000001`；其裸码与市场码无关，同一处注释有记）
 *
 * 设计《产品详情页设计》§2.6 写得很明确：**「代码展示：渲染后端返回的 `symbol` 原样，
 * 不拼不剥；组合 / 经理类不展示代码」**——这两类靠「名称 + 品类 + 平台 / 主理人」识别，
 * 甩一串内部编码给用户看只会制造疑问。
 *
 * ## 为什么收口在纯函数里
 *
 * #2228 的复核结论正是「**设计写了、代码没落地**」：`ProductIdentityCard` 里那行「代码」
 * 事实项是**无条件**渲染的。判定写在模板的 `v-if` 里没法被测试钉住，抽出来才能单测。
 */

/** 不展示「代码」项的品类：`symbol` 是内部编码，对用户无意义（设计 §2.6） */
export const NO_CODE_ASSET_TYPES = ["manager", "portfolio"] as const;

/**
 * 是否展示「代码」事实项。
 *
 * 只有**明确**是组合 / 经理才隐藏。`asset_type` 缺失（null / undefined / 空串）时**展示**：
 * 「不知道品类」不该反过来变成隐藏信息 —— 识别卡其余事实项照常，这里也不该例外。
 * 大小写与首尾空白一并归一（后端给的是小写裸值，但别把健壮性押在调用方身上）。
 */
export function showsCodeItem(assetType?: string | null): boolean {
  const normalized = (assetType ?? "").trim().toLowerCase();
  if (!normalized) return true;
  return !(NO_CODE_ASSET_TYPES as readonly string[]).includes(normalized);
}
