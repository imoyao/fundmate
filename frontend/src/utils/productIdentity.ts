// frontend/src/utils/productIdentity.ts
/**
 * 产品身份与详情页路由（#1964 · 设计 §3.2）。
 *
 * 设计定调：`docs/working-notes/product-detail-page-design-2026-10-08.md` §3.1
 * **路径段 = asset_type，一对一映射，不推断、不别名**，映射表只有本文件一份；
 * 任何页面都不得自己拼字符串跳转。
 *
 * 分期落地情况（设计 §3.1 表格）：
 * - 一期：fund / stock / manager；bond 一期只做集思录外链，**不在**白名单内；
 * - 二期：etf（#1974 加入）、index（卡在 #1407 估值长历史口径，未开）；
 * - 三期：portfolio（#1975 加入）。
 *
 * 未开放的品类传进来返回空串 / null，由调用方回退到「无详情页」的表现，
 * **不在前端推断、不加别名**。
 *
 * 路径上的 asset_type 只是**入口提示**，真实身份一律由后端
 * `GET /api/products/resolve/` 判定（§3.3）。本模块**不解析、不剥前缀**，
 * symbol 原样透传，各品类由后端与各自表去认。
 */

/**
 * 详情页路由参数形状（与 vue-router 的 params 对齐）。
 *
 * **只有这两个字段**：`market` / `venue` 曾作为「同码消歧」参数被拼进 URL query，
 * 但路由 `/:assetType/:symbol` 没有参数位、`parseProductRef` 也读不到它们，
 * 是一串「写了没人读」的死链（#2006）。
 *
 * 2026-10-10 取证（本机生产库）：**不存在**同码多实体——watchlist / positions
 * 按 `family+symbol` 分组的多 market/venue 命中数均为 0，`securities.symbol` 与
 * `funds.fund_code` 本身是唯一键。故不再用 URL 承载消歧参数。
 *
 * 将来真出现同码多实体时**按样本重新设计**——先把消费端接线，再加参数，
 * 不要再留一串没人读的字段（这正是本卡要修的东西）。
 */
export interface ProductRef {
  assetType: string;
  symbol: string;
}

/**
 * 支持独立详情页的品类白名单（设计 §3.1 / §6 分期）。
 *
 * `portfolio`（投顾组合）于 #1975 加入，同时拍板**路径段就用 `portfolio`**（**不**引入
 * `/advisory` 别名）—— 本表是「路径段 = asset_type、一对一、不推断、不别名」的唯一
 * 映射表，加别名会让它出现一对多特例（今天为 portfolio 破例，明天做 etf / index
 * 就没理由拒绝再破）。
 *
 * 与 `/asset/portfolios/:id`（**我方**组合）的区分放在**页面**层：详情页写
 * 「投顾组合」+ 平台，我方组合页写「我的组合」。路由层面不会互相命中（首段
 * `portfolio` vs `asset` 不同、末段平台码 vs 数字 id 不同）。推演见 #1975 评论。
 *
 * `etf` 于 #1974 加入，走 `etf` 路径段（同样不引别名），由后端 resolve 判身份——
 * 它与 `fund` **不在同一个数据口径**：ETF 是场内证券、落在 `securities` 表，
 * 前端不可拿 `fund` 的路径段去套ETF（后端会按 symbol 纠正，但 URL 与实际品类不符）。
 */
export const DETAIL_ASSET_TYPES = [
  "fund",
  "stock",
  "manager",
  "portfolio",
  "etf"
] as const;

export type DetailAssetType = (typeof DETAIL_ASSET_TYPES)[number];

/** 是否已支持详情页的品类 */
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

/**
 * 生成详情页 URL：`/fund/004369`（**不带 query**）。
 *
 * 刻意不带消歧参数（#2006）：带了也没有消费方——路由 `/:assetType/:symbol` 没有
 * 参数位、`parseProductRef` 也读不到，只会让 URL 变长、还给人「已经消歧」的错觉。
 * 详情页拿到 symbol 后由后端 `resolve` 判定身份（设计 §3.3），消歧同理。
 */
export function productRoute(ref: ProductRef): string {
  const segment = assetTypeToPath(ref.assetType);
  const symbol = (ref.symbol || "").trim();
  if (!segment || !symbol) return "";
  return `/${segment}/${encodeURIComponent(symbol)}`;
}

/**
 * 从路由信息解析产品引用。
 *
 * 接受 vue-router 的 route（含 params）或裸 path 字符串。symbol **原样返回**，
 * 拼接与解析各只做一次编码 / 解码，含特殊字符的代码不会被中途改写。
 * 品类段不在白名单内时返回 null（调用方交给 404 态，不硬渲染页面）。
 *
 * **不再解析 `market` / `venue`**（#2006）：这两个参数原来由 `productRoute` 拼进
 * URL query、又因为本函数「对象形式只读 params、不读 query」而一路丢失——是条
 * 「写了没人读」的死链。取证确认库内无同码多实体后，整条链路按「URL 不承载消歧
 * 参数」收敛，消歧交由后端按 symbol 判定。
 *
 * 若将来要恢复：**先把消费端接线，再加参数**，别又留一串没人读的字段。
 */
export function parseProductRef(
  input: { params?: Record<string, unknown> } | string | undefined
): ProductRef | null {
  if (!input) return null;

  let assetType: unknown;
  let symbol: unknown;

  if (typeof input === "string") {
    // 裸 path 形态：只取路径两段，query 一律忽略（与 productRoute 的产出保持一致）
    const [path] = input.split("?");
    const [segment, code] = path.replace(/^\/+/, "").split("/");
    assetType = segment;
    symbol = code;
  } else {
    assetType = input.params?.assetType;
    symbol = input.params?.symbol;
  }

  const normalizedType = pathToAssetType(String(assetType ?? ""));
  const normalizedSymbol = typeof symbol === "string" ? symbol.trim() : "";
  if (!normalizedType || !normalizedSymbol) return null;

  return {
    assetType: normalizedType,
    symbol: decodeURIComponent(normalizedSymbol)
  };
}
