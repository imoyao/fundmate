const Layout = () => import("@/layout/index.vue");

export default {
  path: "/asset",
  name: "Asset",
  component: Layout,
  redirect: "/asset/overview",
  meta: {
    icon: "ep:coin",
    title: "资产记账",
    rank: 2,
    showLink: true
  },
  children: [
    {
      path: "/asset/overview",
      name: "AssetOverview",
      component: () => import("@/views/asset/Overview.vue"),
      meta: {
        title: "资产总览",
        icon: "ep:monitor",
        showLink: true
      }
    },
    {
      path: "/asset/panorama",
      name: "AssetPanorama",
      component: () => import("@/views/asset/AssetPanorama.vue"),
      meta: {
        title: "资产全景",
        icon: "ep:pie-chart",
        rank: 1,
        keepAlive: true
      }
    },
    {
      path: "/watchlist",
      name: "Watchlist",
      component: () => import("@/views/asset/watchlist/index.vue"),
      meta: {
        title: "我的自选",
        icon: "ep:star",
        rank: 3,
        keepAlive: true
      }
    },
    {
      path: "/asset/stocks",
      name: "AssetStocks",
      component: () => import("@/views/asset/stocks/index.vue"),
      meta: {
        title: "股票",
        icon: "ep:trend-charts",
        showLink: true
      }
    },
    {
      path: "/asset/funds",
      name: "AssetFunds",
      component: () => import("@/views/asset/funds/index.vue"),
      meta: {
        title: "基金",
        icon: "ep:box",
        showLink: true
      }
    },
    {
      path: "/asset/bank",
      name: "AssetBank",
      component: () => import("@/views/asset/bank/index.vue"),
      meta: {
        title: "银行存款",
        icon: "ep:wallet",
        showLink: true
      }
    },
    {
      path: "/asset/realestate",
      name: "AssetRealEstate",
      component: () => import("@/views/asset/realestate/index.vue"),
      meta: {
        title: "房产",
        icon: "ep:house",
        showLink: true
      }
    },
    {
      path: "/asset/precious",
      name: "AssetPrecious",
      component: () => import("@/views/asset/precious/index.vue"),
      meta: {
        title: "贵金属",
        icon: "ep:medal",
        showLink: true
      }
    },
    {
      path: "/asset/analysis",
      name: "AssetAnalysis",
      component: () => import("@/views/asset/IntelligentAnalysis.vue"),
      meta: {
        title: "智能分析",
        icon: "ep:data-analysis",
        showLink: true
      }
    }
  ]
} satisfies RouteConfigsTable;
