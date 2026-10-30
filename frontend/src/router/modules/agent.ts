// 账本精灵（#1121 S1-B）：AI 助手模块，**侧边栏只有一级**。
//
// 路由层是两级（`/agent` = Layout 容器，`/agent/chat` = 页面）：two-stage 结构下顶级
// 必须是带 children 的 Layout 路由，否则页面拿不到布局与标签页。但**菜单层不多这一层**
// ——`SidebarItem.hasOneShowingChild` 对「只有 1 个可见子项」的父级会拍平，侧边栏直接
// 渲染子项「账本精灵」，点它即 `/agent/chat`。
//
// 2026-10-30 修正（上一版是错的）：曾给子项加 `showParent: true`，让「智能助手」成为
// 可折叠分组，理由是「面包屑读菜单树不拍平，侧边栏 1 级、面包屑 2 级对不上」。
// 这是**因果倒置**——为了让面包屑有两级，反过来给菜单强加一级；一个只有一页的模块
// 不该有目录层，多一次点击零信息增益，还凭空多出第二个名字（「智能助手」vs「账本精灵」）。
// 正确方向是**面包屑跟着拍平**：`utils/breadcrumb.ts` 对「单可见子项目录」折叠，
// 于是侧边栏 1 级、面包屑 1 级，天然一致，不需要任何 `showParent`。
const Layout = () => import("@/layout/index.vue");

const BASE_RANK = 200;

export default [
  {
    path: "/agent",
    name: "Agent",
    component: Layout,
    redirect: "/agent/chat",
    meta: {
      // 名字与子项**逐字一致**：拍平后用户只看到子项标题，父级若另起一个名字
      // （如旧的「智能助手」），它只会残留在代码与文档里，成为第三个叫法。
      title: "账本精灵",
      icon: "ep:chat-dot-square",
      rank: 3,
      showLink: false // 唯一可见子项会被拍平，父级本身不渲染成菜单项（同 home.ts）
    },
    children: [
      {
        // 子路由用绝对 path：路由会被 formatTwoStageRoutes 拍平，
        // 相对写法会导致 matched 链缺父级（见 home.ts 注释）
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
