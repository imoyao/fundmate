const Layout = () => import("@/layout/index.vue");

export default {
  path: "/account",
  name: "Account",
  component: Layout,
  redirect: "/account/overview",
  meta: {
    icon: "ep:wallet",
    title: "账户总览",
    rank: 1,
    showLink: true
  },
  children: [
    {
      path: "/account/overview",
      name: "AccountOverview",
      component: () => import("@/views/account/AccountOverview.vue"),
      meta: {
        title: "账户总览",
        icon: "ep:wallet",
        showLink: true
      }
    },
    {
      path: "/account/transactions",
      name: "TransactionList",
      component: () => import("@/views/account/TransactionList.vue"),
      meta: {
        title: "交易流水",
        icon: "ep:list"
      }
    },
    {
      path: "/account/management",
      name: "AccountManagement",
      component: () => import("@/views/account/AccountManagement.vue"),
      meta: {
        title: "账户管理",
        showLink: true
      }
    },
    {
      path: "/account/detail/:id?",
      name: "AccountDetail",
      component: () => import("@/views/account/AccountDetail.vue"),
      meta: {
        title: "账户详情",
        showLink: true
      }
    }
  ]
} satisfies RouteConfigsTable;
