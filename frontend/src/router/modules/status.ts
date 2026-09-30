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
      showLink: false // 父级作为目录，不直接显示链接（同 home.ts / agent.ts）
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
          rank: BASE_RANK + 1
        }
      }
    ]
  }
] satisfies Array<RouteConfigsTable>;
