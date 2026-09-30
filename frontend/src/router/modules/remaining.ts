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
  // 全屏重置密码（忘记密码邮件回跳页）：不经过 Layout，未登录可直达
  {
    path: "/reset-password",
    name: "ResetPassword",
    component: () => import("@/views/login/reset-password.vue"),
    meta: {
      title: "重置密码",
      showLink: false,
      requiresAuth: false
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
      showLink: false, // 不在菜单中显示
      requiresAuth: false // 探市免登录（D4），与 /temperature 写法统一（#822）
    }
  },
  // 旧「温度计」独立入口（2026-09-12 方案 D 收敛）：重定向到探市「深度」档。
  // 保留该 path 以承接外部已分享链接与历史书签；页面组件已并入 /explore，
  // 因此不再有 component（原 @/views/temperature/index.vue 已迁移为
  // views/explore/components/ExploreDetailPanel.vue）。
  {
    path: "/temperature",
    name: "Temperature",
    // 字符串形式：本数组是字面量，函数式 redirect 会被 TS 统一推断成 string（TS2322）
    redirect: "/explore?view=detail",
    meta: {
      title: "市场温度计",
      showLink: false,
      requiresAuth: false // 探市免登录（D4），与后端 /api/temperature/* 白名单一致
    }
  },
  // 系统状态（#1720 建页；#1795 命名收敛 health→status；#1799 起为全屏公开页）。
  // 与探市同族：**不经 Layout**（无侧边栏）。页脚入口在探市等全屏公开页也存在，
  // 若落到带侧边栏的后台布局，对匿名访客是观感割裂的跳变；且本页免登录
  // （与后端 /api/health 白名单口径一致），自带 MarketHeader + SiteLegalBar 外壳。
  {
    path: "/system/status",
    name: "SystemStatus",
    component: () => import("@/views/system/status.vue"),
    meta: {
      title: "系统状态",
      showLink: false,
      requiresAuth: false
    }
  },
  // 旧路径归位（#1795）：/system/status 前身为 /system/health，保留重定向承接历史书签与旧页脚链接
  {
    path: "/system/health",
    name: "SystemHealthLegacy",
    redirect: "/system/status",
    meta: {
      title: "系统状态",
      showLink: false,
      requiresAuth: false
    }
  },
  // 个人中心 —— 应用内页面，挂在 Layout 下（不走全屏）
  {
    path: "/profile",
    name: "ProfileParent",
    component: Layout,
    redirect: "/profile",
    meta: {
      title: "个人中心",
      hidden: true // 不进侧边栏菜单，但从导航栏头像进入；hidden 不拦截标签页
    },
    children: [
      {
        path: "/profile",
        name: "Profile",
        component: () => import("@/views/profile/index.vue"),
        meta: {
          title: "个人中心",
          hidden: true
        }
      }
    ]
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
