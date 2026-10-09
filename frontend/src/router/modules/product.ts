// frontend/src/router/modules/product.ts
/**
 * 产品详情页路由（#1964 · 设计 §3.1）。
 *
 * **一条带品类段的路由**而不是 fund/stock/manager 三条重复路由：
 * 目的是让 `productIdentity` 的映射表仍然只有一份（§3.2）。对外呈现的 URL
 * 依然是 `/fund/004369` 这种分品类形态——因为品类段就在路径里。
 *
 * 命名与形态约定：
 * - `name: "ProductDetail"` 必须与 `views/product/detail.vue` 的
 *   `defineOptions({ name })` **逐字一致**，否则 keep-alive 命中不到（本卡开
 *   `keepAlive`，从自选 / 持仓反复切详情要保住滚动与筛选状态）；
 * - `showLink: false`：详情页不进侧边栏，也不留标签页（同一意图只打一个标记，
 *   勿与 `hidden` 混用，见 `router/utils.ts` 的 meta 约定）；
 * - `requiresAuth`：默认即需登录，这里显式写出以免读者以为可省。
 *
 * router-orphan-allow: 四入口接线在 #1965，本卡路由还没有任何 `router-link`
 * 指向它，故会被 `scripts/check_router_links.mjs` 判为孤儿路由。但「用户手输 /
 * fund/004369 直达」正是本设计的核心诉求（§3.1），属**预期孤儿**，故显式豁免。
 */
const ProductDetailRoute = {
  path: "/:assetType/:symbol",
  name: "ProductDetail",
  component: () => import("@/views/product/detail.vue"),
  meta: {
    title: "产品详情",
    showLink: false,
    keepAlive: true,
    requiresAuth: true
  }
} satisfies RouteConfigsTable;

export default ProductDetailRoute;
