import type { RouteConfigWithChildren } from "@/router/types";
// const { VITE_HIDE_HOME } = import.meta.env;
const Layout = () => import("@/layout/index.vue");

// 1. 定义一个基础 Rank (总览排在最前面，用 0)
const BASE_RANK = 0;

// 2. 定义一个工厂函数，用来包裹并处理路由配置
const createHomeRoutes = (routeConfig: RouteConfigWithChildren) => {
  const children = (routeConfig.children ?? []).map(child => ({
    ...child,
    meta: {
      ...child.meta,
      rank: (child.meta?.rank || 0) + BASE_RANK
    }
  }));
  return {
    ...routeConfig,
    children
  };
};

// 3. 定义原始路由配置
//
// 顶级命名与分组口径（2026-10-29 侧边栏重组，2026-11-01 三次修订）：
//
// 侧边栏按**财务动作**切顶级，全站四个业务顶级 + 一个助手：
//   「概览」= 看结果 / 「资产」= 管配置 / 「自选」= 还没买在挑的 / 「记账」= 记事实。
// 本文件只放「看结果」这一类。
//
// 一级菜单用 2 字、二级叶子用 4 字（见 routeRankGuard 的标题守卫）：用户扫一级
// 菜单是"扫列"，越短越快；叶子是"挑具体页面"，才需要说清是什么。
//
// 为什么不再按「我常用什么」摆：此前 home 与 asset 用的是两套分组逻辑
// （home 按使用频次、asset 按资产类型），同一个财务动作被劈到两个顶级下——
// 「看」散在 5 处、「记」散在 4 处、「我的自选 vs 特别关注」隔了两个顶级。
// 分层逻辑统一后，顶级自身就是财务动作，不需要用户记住「哪个功能在哪个顶级」。
//
// ⚠️ 这里只放**纯读**的页面。凡是「把事实录进来」的（全面盘点 / 流水 / 对账）
// 一律归 record.ts，不要因为「首页顺手放一下」再搬回来——那正是上一轮的病因。
const HomeRouteConfig: RouteConfigWithChildren = {
  path: "/",
  name: "Home",
  component: Layout,
  redirect: "/welcome",
  meta: {
    icon: "ep:home-filled",
    title: "概览",
    rank: BASE_RANK,
    showLink: false // 父级作为目录，不直接显示链接
  },
  // 子路由统一使用绝对 path（以 / 开头）。路由经 formatTwoStageRoutes 拍平后，
  // 所有非「/」路由会被挂到根 Home 下；若子路由用相对写法，vue-router 规范化
  // 可能使 matched 链缺失父级。改为绝对 path（与 asset.ts 保持一致）。
  //
  // ⚠️ 变通后果（2026-10-29 已修）：正因为被拍平到根下，`route.matched` 无法反映
  // 真实层级，面包屑曾恒显示「总览 / 某页」。面包屑现改读菜单树，见
  // `utils/breadcrumb.ts`。这里加页面时无需再为面包屑做特殊处理。
  children: [
    {
      path: "/welcome",
      name: "Welcome",
      component: () => import("@/views/welcome/index.vue"),
      meta: {
        title: "投资概览",
        icon: "ep:data-analysis",
        rank: 1,
        showLink: true
      }
    },
    {
      path: "/panorama",
      name: "AssetPanorama",
      component: () => import("@/views/asset/panorama/index.vue"),
      meta: {
        title: "资产总览",
        icon: "ep:pie-chart",
        rank: 2,
        keepAlive: true
      }
    },
    // 持仓分析（#2595）已于 2026-11-28 并入复盘页（P3-C）：区间表现 / 收益日历 /
    // 收益归因三块迁入 `/analysis`，结构区**只留复盘页那一份**（两页此前各有一份
    // 同源同组件，属页面对半时的过渡态）。旧 path 保留为重定向而不是删掉——
    // 它是外部书签可达的 URL，且常带 `?scope=ledger&scope_id=3` 这类口径参数，
    // 必须原样带到新地址，否则用户回来看到的是家庭级数据（静默错口径）。
    {
      path: "/asset/position-analysis",
      // router-orphan-allow: 纯重定向历史别名，站内零入链是设计使然 —— 它存在的
      // 唯一目的是承接外部书签与已分享链接（内容已于 2026-11-28 并入 /analysis）。
      name: "PositionAnalysis",
      // 函数式 redirect：口径参数（`?scope=ledger&scope_id=3`）必须原样带走。
      // 用函数式必须给 `HomeRouteConfig` 显式标注类型（见下方常量声明）——否则整棵
      // children 的推断会把父级判成 RouteRecordRedirect，报 component 不可赋给 never。
      redirect: to => ({ path: "/analysis", query: to.query }),
      meta: {
        title: "持仓分析",
        icon: "ep:pie-chart",
        rank: 3,
        // 侧栏不再给入口：内容已在「投资复盘」，两项并列只会让人以为有两个分析页
        showLink: false
      }
    },
    // 复盘（#2150 由「智能分析」改名）：时间维度的表现。
    // 2026-11-28 起它同时是原「持仓分析」的落点（P3-C）：净值怎么走、收益从哪来、
    // 区间超额与归因，都在这一页按口径切换看。
    // ⚠️ 路由 path 保持 `/analysis` 不动——它是外部可达 URL 与既有书签的锚点。
    {
      path: "/analysis",
      name: "AssetAnalysis",
      component: () => import("@/views/asset/IntelligentAnalysis.vue"),
      meta: {
        title: "投资复盘",
        icon: "ep:data-analysis",
        rank: 4,
        showLink: true
      }
    }
  ]
};

// 4. 导出处理后的路由
export default createHomeRoutes(HomeRouteConfig);
