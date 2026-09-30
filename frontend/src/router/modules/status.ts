// 系统状态模块（#1720；路径与命名收敛 #1795）：状态页，向维护者 / 访客展示后端 /api/health 组件健康。
// 命名口径：页面与前端路由统一叫 status（业界「status page」惯例），后端接口仍是 /api/health
// （运维探活端点，探活工具普遍按 /health 调用，属 conventions.md 尾斜杠规范例外 D28，不改）。
// 侧边栏菜单由路由 meta 自动生成，无需手动注册。
// rank 段位：home 占 0~5、asset 占 100+、agent 占 200+；本模块排在 agent 之后用 300+。
const Layout = () => import("@/layout/index.vue");

const BASE_RANK = 300;

export default [
  {
    path: "/system",
    name: "System",
    component: Layout,
    redirect: "/system/status",
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
        path: "/system/status",
        name: "SystemStatus",
        component: () => import("@/views/system/status.vue"),
        meta: {
          title: "系统状态",
          icon: "ep:monitor",
          rank: BASE_RANK + 1,
          requiresAuth: false // 状态页匿名可见（#1720）：与后端 /api/health 免登录一致，便于访客查看服务状态
        }
      },
      {
        // 旧路径归位（#1795）：/system/health 曾是对外分享 / 页脚入口，保留重定向承接旧书签与历史链接。
        // 只做重定向、不挂组件，故不参与菜单与 keep-alive。
        path: "/system/health",
        name: "SystemHealthLegacy",
        redirect: "/system/status",
        meta: {
          title: "系统状态",
          showLink: false,
          hidden: true,
          requiresAuth: false
        }
      }
    ]
  }
] satisfies Array<RouteConfigsTable>;
