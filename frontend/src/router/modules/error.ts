export default {
  path: "/error",
  redirect: "/error/403",
  meta: {
    icon: "ri:information-line",
    // hidden：不进侧边栏（父级 + 全部子级均 hidden，整棵移除），
    // 但路由仍注册，直接访问 /error/403、/error/404、/error/500 可正常打开
    hidden: true,
    title: "异常页面",
    rank: 9
  },
  children: [
    {
      path: "/error/403",
      name: "403",
      component: () => import("@/views/error/403.vue"),
      meta: {
        title: "403",
        hidden: true
      }
    },
    {
      path: "/error/404",
      name: "404",
      component: () => import("@/views/error/404.vue"),
      meta: {
        title: "404",
        hidden: true
      }
    },
    {
      path: "/error/500",
      name: "500",
      component: () => import("@/views/error/500.vue"),
      meta: {
        title: "500",
        hidden: true
      }
    }
  ]
} satisfies RouteConfigsTable;
