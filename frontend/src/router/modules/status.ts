// 系统状态模块（#1720）：管理/状态页，向维护者展示后端 /api/health 组件健康。
// 侧边栏菜单由路由 meta 自动生成，无需手动注册。
// rank 段位：home 占 0~5、asset 占 100+、agent 占 200+；本模块排在 agent 之后用 300+。
const Layout = () => import("@/layout/index.vue");

const BASE_RANK = 300;

export default [
  {
    path: "/system",
    name: "System",
    component: Layout,
    redirect: "/system/health",
    meta: {
      title: "系统状态",
      icon: "ep:monitor",
      rank: 3,
      hidden: true, // 不进侧边栏菜单，仅作为 footer 引导链接的可访问路由（#1720）
      showLink: false
    },
    children: [
      {
        // 绝对 path：路由会被 formatTwoStageRoutes 拍平，相对写法会破坏面包屑 matched 链
        path: "/system/health",
        name: "SystemHealth",
        component: () => import("@/views/system/health.vue"),
        meta: {
          title: "健康检查",
          icon: "ep:connection",
          rank: BASE_RANK + 1,
          requiresAuth: false // 状态页匿名可见（#1720）：与后端 /api/health 免登录一致，便于访客查看服务状态
        }
      }
    ]
  }
] satisfies Array<RouteConfigsTable>;
