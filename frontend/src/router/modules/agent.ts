// 账本精灵（#1121 S1-B）：AI 助手模块，单页「对话」。
// rank 段位沿用 asset.ts 的隔离思路：home 占 0~5、asset 占 100+，
// 本模块 200+，父级 rank=2 排在「资产管理」之后、error 目录之前。
const Layout = () => import("@/layout/index.vue");

const BASE_RANK = 200;

export default [
  {
    path: "/agent",
    name: "Agent",
    component: Layout,
    redirect: "/agent/chat",
    meta: {
      title: "AI 助手",
      icon: "ep:chat-dot-square",
      rank: 2,
      showLink: false // 父级作为目录，不直接显示链接（同 home.ts）
    },
    children: [
      {
        // 子路由用绝对 path：路由会被 formatTwoStageRoutes 拍平，
        // 相对写法会导致面包屑 matched 链缺父级（见 home.ts 注释）
        path: "/agent/chat",
        name: "AgentChat",
        component: () => import("@/views/agent/index.vue"),
        meta: {
          title: "账本精灵",
          icon: "ep:chat-dot-square",
          rank: BASE_RANK + 1
          // requiresAuth 不写即默认需登录——与后端 /api/agent/chat/ 非白名单口径一致
        }
      }
    ]
  }
] satisfies Array<RouteConfigsTable>;
