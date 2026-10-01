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
    // router-orphan-allow: 与 /error/403 同指 views/error/403.vue，属重复实现且站内零入链
    // （router/index.ts:123 的 whiteList 是鉴权白名单，不是导航）。
    // 保留而非本次删除：#1787 的范围是「batch 死路由 + 孤儿守卫」，合并两套异常页
    // 属另一件事，已立 #1797 承接；那里会连 whiteList 一起处理。
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
    // router-orphan-allow: 与 /error/500 同指 views/error/500.vue，站内零入链（同上）。
    // 合并两套异常页见 #1797；标记随该卡一起摘。
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
    // router-orphan-allow: 这条路由**天生就是孤儿**，零站内入链是设计使然 ——
    // 它存在的唯一目的就是承接外部已分享链接与历史书签（见上方注释），
    // 站内早已不再指向它。删掉它等于让所有旧书签落到 404。
    name: "Temperature",
    // 字符串形式：本数组是字面量，函数式 redirect 会被 TS 统一推断成 string（TS2322）
    redirect: "/explore?view=detail",
    meta: {
      title: "市场温度计",
      showLink: false,
      requiresAuth: false // 探市免登录（D4），与后端 /api/temperature/* 白名单一致
    }
  },
  // 系统状态（#1720 建页；#1795 health→status 命名收敛；#1799 全屏公开页；#1802 归位一级路径）。
  // 路径就是 `/status`：status page 属站点根下的短路径（GitHub 即 /status），
  // 再套一层 /system 既无第二个兄弟页可挂，也让「系统」与「状态」语义重复。
  // 与探市同族：不经 Layout（无侧边栏），自带 MarketHeader + SiteLegalBar 外壳，免登录
  // （与后端 /api/health 白名单口径一致）。
  {
    path: "/status",
    name: "Status",
    component: () => import("@/views/status/index.vue"),
    meta: {
      title: "系统状态",
      showLink: false,
      requiresAuth: false
    }
  },
  // 旧路径归位（承接历史书签与外链，勿删）：/system/health 为原始路径，
  // /system/status 为 #1795 的中间态。
  {
    path: "/system/status",
    name: "SystemStatusLegacy",
    redirect: "/status",
    // router-orphan-allow: 纯 redirect 历史别名，站内零入链是设计使然 —— 只承接
    // 旧书签 / 外链（#1795 中间态），用户从站内任何地方都不该走到它，跳转后落在 /status。
    meta: {
      title: "系统状态",
      showLink: false,
      requiresAuth: false
    }
  },
  {
    path: "/system/health",
    name: "SystemHealthLegacy",
    redirect: "/status",
    // router-orphan-allow: 同上 —— /system/health 是 #1720 原始路径，纯 redirect
    // 别名承接历史书签与外链，站内零入链、跳转后落 /status，保留勿删。
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
