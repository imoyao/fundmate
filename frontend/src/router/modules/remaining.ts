const Layout = () => import("@/layout/index.vue");

export default [
  {
    path: "/login",
    name: "Login",
    component: () => import("@/views/login/index.vue"),
    meta: {
      title: "登录",
      showLink: false
    }
  },
  // 全屏403（无权访问）页面
  {
    path: "/access-denied",
    name: "AccessDenied",
    component: () => import("@/views/error/403.vue"),
    meta: {
      title: "403",
      showLink: false
    }
  },
  // 全屏500（服务器出错）页面
  {
    path: "/server-error",
    name: "ServerError",
    component: () => import("@/views/error/500.vue"),
    meta: {
      title: "500",
      showLink: false
    }
  },
  // 🔥 探市·研究 —— 独立全屏页面，不经过 Layout
  {
    path: "/explore",
    name: "Explore",
    component: () => import("@/views/explore/index.vue"),
    meta: {
      title: "探市",
      showLink: false // 不在菜单中显示
    }
  },
  // 在 remaining 路由数组中新增温度计页面
  {
    path: "/temperature",
    name: "Temperature",
    component: () => import("@/views/temperature/index.vue"),
    meta: {
      title: "市场温度计",
      showLink: false,
      requiresAuth: false // 探市免登录（D4），与后端 /api/temperature/* 白名单一致
    }
  },
  {
    path: "/redirect",
    component: Layout,
    meta: {
      title: "加载中...",
      showLink: false
    },
    children: [
      {
        path: "/redirect/:path(.*)",
        name: "Redirect",
        component: () => import("@/layout/redirect.vue"),
        meta: {
          title: "Redirect",
          showLink: false
        }
      }
    ]
  }
] satisfies Array<RouteConfigsTable>;
