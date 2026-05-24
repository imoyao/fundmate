const Layout = () => import("@/layout/index.vue");
const EmptyLayout = () => import("@/layout/components/EmptyLayout.vue");

export default {
  path: "/asset",
  name: "Asset",
  component: Layout,
  redirect: "/asset/panorama",
  meta: {
    icon: "ep:coin",
    title: "资产管理",
    rank: 2,
    showLink: true
  },
  children: [
    // 投资理财 → 对账单导入
    {
      path: "inventory/investment/import",
      name: "InvestmentImport",
      component: () => import("@/views/asset/investment/import/index.vue"),
      meta: { title: "对账单导入", icon: "ep:document", rank: 10, showLink: false }
    },
    // 投资理财 → 手动录入（占位）
    {
      path: "inventory/investment/manual",
      name: "InvestmentManual",
      component: () => import("@/views/asset/investment/manual/index.vue"),
      meta: { title: "手动录入", icon: "ep:edit", rank: 11, showLink: false }
    },
    // 投资理财 → 批量导入（占位）
    {
      path: "inventory/investment/batch",
      name: "InvestmentBatch",
      component: () => import("@/views/asset/investment/batch/index.vue"),
      meta: { title: "批量导入", icon: "ep:upload", rank: 12, showLink: false }
    },
    // 通用资产录入
    {
      path: "/asset/asset-entry",
      name: "AssetEntry",
      component: () => import("@/views/asset/AssetEntry.vue"),
      meta: { title: "录入通用资产", icon: "ep:plus", rank: 8, showLink: false }
    },
    // 特别关注
    {
      path: "/the-road-not-taken",
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
      meta: { title: "投资管理", icon: "ep:folder-opened", rank: 10 },
      children: [
        {
          path: "stocks",
          name: "AssetStocks",
          component: () => import("@/views/asset/stocks/index.vue"),
          meta: { title: "股票", icon: "ep:trend-charts", rank: 2, showLink: false }
        },
        {
          path: "funds",
          name: "AssetFunds",
          component: () => import("@/views/asset/funds/index.vue"),
          meta: { title: "基金", icon: "ep:box", rank: 3, showLink: false }
        },
        {
          path: "precious",
          name: "AssetPrecious",
          component: () => import("@/views/asset/precious/index.vue"),
          meta: { title: "贵金属", icon: "ep:medal", rank: 4, showLink: false }
        },
        {
          path: "realestate",
          name: "AssetRealEstate",
          component: () => import("@/views/asset/realestate/index.vue"),
          meta: { title: "房产", icon: "ep:house", rank: 5, showLink: false }
        },
        {
          path: "analysis",
          name: "AssetAnalysis",
          component: () => import("@/views/asset/IntelligentAnalysis.vue"),
          meta: { title: "智能分析", icon: "ep:data-analysis", rank: 6, showLink: false }
        }
      ]
    },
    {
      path: "/asset/ledgers",
      name: "AssetLedgers",
      component: () => import("@/views/asset/AssetLedgers.vue"),
      meta: { title: "账户管理", icon: "ep:wallet", rank: 30}
    },
    // 账户详情（作为 Asset 的子路由，继承 Layout 布局）
    {
      path: "/asset/ledgers/:id",
      name: "LedgerDetail",
      component: () => import("@/views/asset/LedgerDetail.vue"),
      meta: { title: "账户详情", icon: "ep:wallet", rank: 31, showLink: false, hidden: true }
    }
  ]
} satisfies RouteConfigsTable;
