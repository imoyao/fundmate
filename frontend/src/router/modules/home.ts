// const { VITE_HIDE_HOME } = import.meta.env;
const Layout = () => import("@/layout/index.vue");

export default {
  path: "/",
  name: "Home",
  component: Layout,
  redirect: "/welcome",
  meta: {
    icon: "ep/home-filled",
    title: "总览",
    rank: 0,
    showLink: false
  },
  children: [
    {
      path: "/welcome",
      name: "Welcome",
      component: () => import("@/views/welcome/index.vue"),
      meta: {
        title: "总览",
        showLink: false
      }
    },
    {
      path: "/panorama",
      name: "AssetPanorama",
      component: () => import("@/views/asset/AssetPanorama.vue"),
      meta: { title: "资产总览", icon: "ep:pie-chart", rank: 1, keepAlive: true }
    },
    {
      path: "inventory",
      name: "Inventory",
      component: () => import("@/views/asset/investment/import/index.vue"),
      meta: { title: "全面盘点", icon: "ep:document-copy", rank: 2 }
    },
    {
      path: "watchlist",
      name: "Watchlist",
      component: () => import("@/views/asset/watchlist/index.vue"),
      meta: { title: "我的自选", icon: "ep:star", rank: 3, keepAlive: true }
    },
    {
      path: "transactions",
      name: "TransactionList",
      component: () => import("@/views/asset/TransactionList.vue"),
      meta: { title: "交易流水", icon: "ep:list", rank: 4 }
    },
  ]
} satisfies RouteConfigsTable;
