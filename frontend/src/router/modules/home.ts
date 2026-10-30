// const { VITE_HIDE_HOME } = import.meta.env;
const Layout = () => import("@/layout/index.vue");

// 1. 定义一个基础 Rank (总览排在最前面，用 0)
const BASE_RANK = 0;

// 2. 定义一个工厂函数，用来包裹并处理路由配置
const createHomeRoutes = (routeConfig: any) => {
  const children = routeConfig.children.map((child: any) => ({
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
// 顶级命名与分组口径（2026-10-29 侧边栏重组）：
//
// 侧边栏按**财务动作**切顶级，全站只有三个业务顶级 + 一个助手：
//   「资产概览」= 看结果 / 「资产管理」= 管配置 / 「记账中心」= 记事实。
// 本文件只放「看结果」这一类。
//
// 为什么不再按「我常用什么」摆：此前 home 与 asset 用的是两套分组逻辑
// （home 按使用频次、asset 按资产类型），同一个财务动作被劈到两个顶级下——
// 「看」散在 5 处、「记」散在 4 处、「我的自选 vs 特别关注」隔了两个顶级。
// 分层逻辑统一后，顶级自身就是财务动作，不需要用户记住「哪个功能在哪个顶级」。
//
// ⚠️ 这里只放**纯读**的页面。凡是「把事实录进来」的（全面盘点 / 流水 / 对账）
// 一律归 record.ts，不要因为「首页顺手放一下」再搬回来——那正是上一轮的病因。
const HomeRouteConfig = {
  path: "/",
  name: "Home",
  component: Layout,
  redirect: "/welcome",
  meta: {
    icon: "ep:home-filled",
    title: "资产概览",
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
    // 持仓分析（#2595）：全家庭 / 单账户 / 组合三级口径。
    // 归「看结果」而不是「投资」——它不下任何配置，只回答「表现、超额、穿透」。
    {
      path: "/asset/position-analysis",
      name: "PositionAnalysis",
      component: () => import("@/views/asset/position-analysis/index.vue"),
      meta: {
        title: "持仓分析",
        icon: "ep:pie-chart",
        rank: 3,
        showLink: true
      }
    },
    // 复盘（#2150 由「智能分析」改名）：时间维度的表现。
    // 与持仓分析的分工：本页回答「净值怎么走、收益从哪来」，持仓分析回答
    // 「三级口径下的持仓表现与结构」。两者都是读，故同在这一顶级。
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
