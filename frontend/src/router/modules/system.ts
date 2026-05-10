const Layout = () => import("@/layout/index.vue");

export default {
  path: "/system",
  name: "System",
  component: Layout,
  redirect: "/system/settings",
  meta: {
    icon: "ep:setting",
    title: "系统配置",
    rank: 3,
    showLink: true
  },
  children: [
    {
      path: "/system/settings",
      name: "SystemSettings",
      component: () => import("@/views/system/SystemSettings.vue"),
      meta: {
        title: "系统设置",
        showLink: true
      }
    }
  ]
} satisfies RouteConfigsTable;
