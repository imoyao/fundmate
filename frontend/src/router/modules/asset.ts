const Layout = () => import("@/layout/index.vue");
const EmptyLayout = () => import("@/layout/components/EmptyLayout.vue");

// 1. 将资产管理模块的基础 Rank 设置为 100，彻底隔离 home.ts
const BASE_RANK = 100;

// 2. 工厂函数
const createAssetRoutes = (routeConfig: any) => {
  const children = routeConfig.children.map((child: any) => {
    // 如果子路由还有 children（如投资管理），需递归处理
    if (child.children) {
      child.children = child.children.map((grandChild: any) => ({
        ...grandChild,
        meta: {
          ...grandChild.meta,
          rank: (grandChild.meta?.rank || 0) + BASE_RANK
        }
      }));
    }
    return {
      ...child,
      meta: {
        ...child.meta,
        rank: (child.meta?.rank || 0) + BASE_RANK
      }
    };
  });
  return {
    ...routeConfig,
    children
  };
};

// 3. 定义原始配置
const AssetRouteConfig = {
  path: "/asset",
  name: "Asset",
  component: Layout,
  redirect: "/panorama",
  meta: {
    icon: "ep:coin",
    title: "资产管理",
    rank: 1, // 只要写模块内的相对位置即可（0, 1, 2...）
    showLink: true
  },
  children: [
    {
      path: "the-road-not-taken",
      name: "Favourites",
      component: () => import("@/views/asset/favorites/index.vue"),
      meta: { title: "特别关注", icon: "ep:opportunity", rank: 1 }
    },
    // ── 投资管理（可折叠）──
    {
      path: "investment",
      name: "InvestmentManage",
      component: EmptyLayout,
      redirect: "/asset/investment/favorites",
      meta: { title: "投资管理", icon: "ep:folder-opened", rank: 2 },
      children: [
        { path: "stocks", name: "AssetStocks", component: () => import("@/views/asset/stocks/index.vue"), meta: { title: "股票", icon: "ep:trend-charts", rank: 1, showLink: false } },
        { path: "funds", name: "AssetFunds", component: () => import("@/views/asset/funds/index.vue"), meta: { title: "基金", icon: "ep:box", rank: 2, showLink: false } },
        { path: "precious", name: "AssetPrecious", component: () => import("@/views/asset/precious/index.vue"), meta: { title: "贵金属", icon: "ep:medal", rank: 3, showLink: false } },
        { path: "realestate", name: "AssetRealEstate", component: () => import("@/views/asset/realestate/index.vue"), meta: { title: "房产", icon: "ep:house", rank: 4, showLink: false } },
        { path: "analysis", name: "AssetAnalysis", component: () => import("@/views/asset/IntelligentAnalysis.vue"), meta: { title: "智能分析", icon: "ep:data-analysis", rank: 5, showLink: false } },
        { path: "inventory/investment/import", name: "InvestmentImport", component: () => import("@/views/asset/investment/import/index.vue"), meta: { title: "对账单导入", icon: "ep:document", rank: 6, showLink: false } },
        { path: "inventory/investment/manual", name: "InvestmentManual", component: () => import("@/views/asset/investment/manual/index.vue"), meta: { title: "手动录入", icon: "ep:edit", rank: 7, showLink: false } },
        { path: "inventory/investment/batch", name: "InvestmentBatch", component: () => import("@/views/asset/investment/batch/index.vue"), meta: { title: "批量导入", icon: "ep:upload", rank: 8, showLink: false } },
      ]
    },
    {
      path: "/asset/ledgers", name: "AssetLedgers", component: () => import("@/views/asset/ledgers/index.vue"), meta: { title: "账户管理", icon: "ep:wallet", rank: 3 }
    },
    { path: "/asset/strategies", name: "Strategies", component: () => import("@/views/asset/strategies/index.vue"), meta: { title: "策略分析", icon: "ep:data-analysis", rank: 4, showLink: true }
    }
  ]
};

// 4. 导出
export default createAssetRoutes(AssetRouteConfig);
