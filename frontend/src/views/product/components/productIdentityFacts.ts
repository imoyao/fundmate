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

/**
 * 识别卡是否有**身份事实**可放（代码 / 市场 / 场所）。
 *
 * ## 身份 vs 状态
 *
 * 识别卡回答的是「**这是什么标的**」——代码、市场、场所都能独立回答它。
 * 「自选 / 已持有」回答的是「**我和它什么关系**」，是**状态**，不是身份；
 * 它只能在卡片**已经因为身份事实而存在**时，作为附加徽标出现。
 *
 * ## 为什么不能「有任何一项就成卡」（2026-11-26 用户实测）
 *
 * 组合 / 经理类不展示代码（`showsCodeItem` 为 false），也没有市场 / 场所。
 * 一旦用户恰好自选了该组合，旧判据 `hasAnyFact` 就会造出一张**横贯整行、
 * 只写「自选 / 已关注」两行字**的卡片：它不可操作（点不了取消自选），
 * 也不携带任何能被使用的事实。用户原话：「这个自选直接一个横幅卡片，
 * 而且似乎也没有什么意义」。
 *
 * 根因是判据把状态算成了内容 —— 于是**没有身份的页面上，卡片为一行状态而存在**。
 * 换成「有身份事实才成卡」后：基金 / 股票 / ETF 照旧（有代码），
 * 组合 / 经理类整卡不渲染；自选状态改由页头承担（可操作），不靠一张死卡片背书。
 */
export function hasIdentityFacts(product: {
  asset_type?: string | null;
  market?: string | null;
  venue?: string | null;
}): boolean {
  return (
    showsCodeItem(product.asset_type) ||
    Boolean(product.market) ||
    Boolean(product.venue)
  );
}
