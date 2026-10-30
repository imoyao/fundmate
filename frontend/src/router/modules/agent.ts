// 账本精灵（#1121 S1-B）：AI 助手模块，单页「对话」。
// rank 段位沿用 asset.ts 的隔离思路：home 占 0、asset 占 100+、record 占 2、
// 本模块 rank=3 排在「记账中心」之后、error 目录之前。
const Layout = () => import("@/layout/index.vue");

const BASE_RANK = 200;

export default [
  {
    path: "/agent",
    name: "Agent",
    component: Layout,
    redirect: "/agent/chat",
    meta: {
      // 原「AI 助手」→「智能助手」：侧边栏统一 4 字（2026-10-29）。
      title: "智能助手",
      icon: "ep:chat-dot-square",
      rank: 3,
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
          rank: BASE_RANK + 1,
          // 唯一子项 + `showParent: true` = 强制「智能助手」渲染成可折叠分组。
          // 不加这一条，SidebarItem.hasOneShowingChild 会把只有一个子项的父级**拍平**，
          // 侧边栏直接出现一个顶级「账本精灵」，而面包屑仍是「智能助手 / 账本精灵」
          // （面包屑读的是菜单树，不会拍平）——侧边栏 1 级、面包屑 2 级，层级对不上。
          // 这是 SidebarItem.vue 里唯一的逃生口（`showingChildren[0]?.meta?.showParent`）。
          showParent: true
          // requiresAuth 不写即默认需登录——与后端 /api/agent/chat/ 非白名单口径一致
        }
      }
    ]
  }
] satisfies Array<RouteConfigsTable>;
