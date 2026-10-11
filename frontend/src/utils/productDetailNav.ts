// frontend/src/utils/productDetailNav.ts
import { resolveProduct } from "@/api/products";
import { isDetailAssetType, productRoute } from "@/utils/productIdentity";

/**
 * 详情页跳转辅助（#1965）。
 *
 * 四个入口（自选速览抽屉 / 聚合抽屉 / 账户持仓抽屉 / 首页 Widget）都需要
 * 「拿到某产品 → 跳详情页」这同一件事，故收口于此，避免四处各写一遍拼接与兜底。
 *
 * 为什么不直接 `productRoute({ assetType: row.asset_type, ... })` 就完事：
 * 入口拿到的品类字段**并不齐、且字段名不统一**——聚合抽屉的 group 根本没有
 * asset_type，持仓抽屉叫 `type`，首页 Widget 的 asset_type 可空。按设计 §3.3
 * 「前端不推断、不剥前缀，身份以后端判定为准」，这些缺口一律回 A1 端点问一次，
 * 而不是在前端按 symbol 形态猜品类（那正是 #1497 把指数错标成无关基金的根因）。
 *
 * 只返回路径、**不自己跳转**：四个入口里有三个是抽屉，都需要「先关抽屉、再跳详情」，
 * 跳转时机由各自控制（沿用 `QuickEntry/TransactionDrawer.vue` 的既有范式）。
 */

/** 各入口能提供的原始标识字段（缺失就留空 / null，由本模块兜底） */
export interface DetailNavInput {
  symbol: string;
  /** 入口自带的品类：可能是 `asset_type`，也可能是持仓的 `type`，也可能缺失 */
  assetType?: string | null;
  /** 市场消歧。**原样透传**，不做 SH/SZ → CN_A 归一：库里存的就是 normalizer 原值 */
  market?: string | null;
  /** 场所消歧（EXCHANGE / OTC）；持仓等没有该字段时留空 */
  venue?: string | null;
}

/**
 * 解析详情页路径。
 *
 * 品类齐全且在一期白名单内 → 直接拼，省一次请求；否则先问后端拿权威 asset_type。
 *
 * @returns 详情页路径；空串表示「该品类详情页尚未开放」（二期 / 三期品类）。
 * @throws 后端 404（产品未被收录）或网络异常——调用方据此区分「未开放」与「不存在」。
 */
export async function resolveDetailPath(
  input: DetailNavInput
): Promise<string> {
  const symbol = (input.symbol || "").trim();
  if (!symbol) return "";

  if (isDetailAssetType(input.assetType)) {
    // 只带品类段与 symbol：#2006 起详情页 URL 不再承载 market / venue
    const direct = productRoute({
      assetType: input.assetType,
      symbol
    });
    if (direct) return direct;
  }

  // 品类缺失 / 不在一期白名单 → 后端权威判定。
  // 注意：这里的 market / venue 是**发给 resolve 的 HTTP 入参**（后端据此在
  // watchlist / positions 行内快照里判身份），与「URL 是否承载消歧参数」是两件事，
  // 故保留；而返回的路径不再回填它们（#2006）。
  const { data } = await resolveProduct({
    symbol,
    market: input.market ?? undefined,
    venue: input.venue ?? undefined
  });
  return productRoute({
    assetType: data.asset_type,
    symbol: data.symbol
  });
}
