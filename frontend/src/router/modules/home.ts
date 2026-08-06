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
const HomeRouteConfig = {
  path: "/",
  name: "Home",
  component: Layout,
  redirect: "/welcome",
  meta: {
    icon: "ep:home-filled",
    title: "总览",
    rank: BASE_RANK,
    showLink: false // 父级作为目录，不直接显示链接
  },
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
      component: () => import("@/views/asset/AssetPanorama.vue"),
      meta: {
        title: "资产总览",
        icon: "ep:pie-chart",
        rank: 2,
        keepAlive: true
      }
    },
    {
      path: "inventory",
      name: "Inventory",
      component: () => import("@/views/asset/inventory/index.vue"),
      meta: {
        title: "全面盘点",
        icon: "ep:document-checked",
        rank: 3,
        hideQuickEntry: true
      }
    },
    {
      path: "watchlist",
      name: "Watchlist",
      component: () => import("@/views/asset/watchlist/index.vue"),
      meta: {
        title: "我的自选",
        icon: "ep:star",
        rank: 4,
        keepAlive: true
      }
    },
    {
      path: "transactions",
      name: "TransactionList",
      component: () => import("@/views/asset/TransactionList.vue"),
      meta: {
        title: "交易流水",
        icon: "ep:list",
        rank: 5
      }
    }
  ]
};

// 4. 导出处理后的路由
export default createHomeRoutes(HomeRouteConfig);
