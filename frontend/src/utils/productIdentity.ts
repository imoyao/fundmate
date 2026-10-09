// frontend/src/utils/productIdentity.ts
/**
 * 产品身份与详情页路由（#1964 · 设计 §3.2）。
 *
 * 设计定调：`docs/working-notes/product-detail-page-design-2026-10-08.md` §3.1
 * **路径段 = asset_type，一对一映射，不推断、不别名**，映射表只有本文件一份；
 * 任何页面都不得自己拼字符串跳转。
 *
 * 一期只做三品类（§3.1 表格）：fund / stock / manager。bond 一期只做集思录外链、
 * etf / index 二期、portfolio 三期，故不在白名单内——传了返回空串，由调用方回退。
 *
 * 路径上的 asset_type 只是**入口提示**，真实身份一律由后端
 * `GET /api/products/resolve/` 判定（§3.3）。本模块**不解析、不剥前缀**，
 * symbol 原样透传，各品类由后端与各自表去认。
 */

/** 详情页路由参数形状（与 vue-router 的 params 对齐） */
export interface ProductRef {
  assetType: string;
  symbol: string;
  market?: string;
  venue?: string;
}

/** 一期支持独立详情页的品类白名单（设计 §3.1） */
export const DETAIL_ASSET_TYPES = ["fund", "stock", "manager"] as const;

export type DetailAssetType = (typeof DETAIL_ASSET_TYPES)[number];

/** 是否一期已支持详情页的品类 */
export function isDetailAssetType(value: unknown): value is DetailAssetType {
  return (
    typeof value === "string" &&
    (DETAIL_ASSET_TYPES as readonly string[]).includes(
      value.trim().toLowerCase()
    )
  );
}

/** asset_type → 路径段（唯一映射表）；非白名单返回空串 */
export function assetTypeToPath(assetType: string): string {
  return isDetailAssetType(assetType) ? assetType.trim().toLowerCase() : "";
}

/** 路径段 → asset_type；不在白名单内返回 null（路由守卫据此判非法段） */
export function pathToAssetType(segment: string): DetailAssetType | null {
  const normalized = (segment || "").trim().toLowerCase();
  return isDetailAssetType(normalized) ? normalized : null;
}

/** 生成详情页 URL：/fund/004369?market=&venue=（空消歧参数不带） */
export function productRoute(ref: ProductRef): string {
  const segment = assetTypeToPath(ref.assetType);
  const symbol = (ref.symbol || "").trim();
  if (!segment || !symbol) return "";

  const params = new URLSearchParams();
  if (ref.market) params.set("market", ref.market);
  if (ref.venue) params.set("venue", ref.venue);
  const query = params.toString();
  return `/${segment}/${encodeURIComponent(symbol)}${query ? `?${query}` : ""}`;
}

/**
 * 从路由信息解析产品引用。
 *
 * 接受 vue-router 的 route（含 params）或裸 path 字符串。symbol **原样返回**，
 * 拼接与解析各只做一次编码 / 解码，含特殊字符的代码不会被中途改写。
 * 品类段不在白名单内时返回 null（调用方交给 404 态，不硬渲染页面）。
 */
export function parseProductRef(
  input: { params?: Record<string, unknown> } | string | undefined
): ProductRef | null {
  if (!input) return null;

  let assetType: unknown;
  let symbol: unknown;
  let market: unknown;
  let venue: unknown;

  if (typeof input === "string") {
    const [path, query = ""] = input.split("?");
    const [segment, code] = path.replace(/^\/+/, "").split("/");
    assetType = segment;
    symbol = code;
    const search = new URLSearchParams(query);
    market = search.get("market");
    venue = search.get("venue");
  } else {
    assetType = input.params?.assetType;
    symbol = input.params?.symbol;
    market = input.params?.market;
    venue = input.params?.venue;
  }

  const normalizedType = pathToAssetType(String(assetType ?? ""));
  const normalizedSymbol = typeof symbol === "string" ? symbol.trim() : "";
  if (!normalizedType || !normalizedSymbol) return null;

  return {
    assetType: normalizedType,
    symbol: decodeURIComponent(normalizedSymbol),
    market: typeof market === "string" && market ? market : undefined,
    venue: typeof venue === "string" && venue ? venue : undefined
  };
}

/** 产品唯一键：assetType|symbol|market|venue（设计 §3.2） */
export function productKey(ref: ProductRef): string {
  return [ref.assetType, ref.symbol, ref.market || "", ref.venue || ""].join(
    "|"
  );
}
