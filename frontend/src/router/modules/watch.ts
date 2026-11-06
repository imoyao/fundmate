const Layout = () => import("@/layout/index.vue");

// 1. 「自选」占 rank 2 段（home 0 / asset 1 / watch 2 / record 3 / agent 4）
const BASE_RANK = 2;

// 2. 工厂函数：子级 rank 用 0~99 的相对值
const createWatchRoutes = (routeConfig: any) => {
  const children = routeConfig.children.map((child: any) => ({
    ...child,
    meta: {
      ...child.meta,
      rank: (child.meta?.rank || 0) + 100
    }
  }));
  return {
    ...routeConfig,
    children
  };
};

// 3. 定义原始配置
//
// 为什么自成一个顶级（2026-11-01）：
//
// 这一组此前叫「我的关注」，是 `/asset` 下的第三个分组目录。三个成员从未属于
// 「资产」——它们的共同点是**还没买、在挑、在盯**：
//   我的自选 = 实时数据表格（我已加入、在盯的标的）
//   特别关注 = 私有思考 + 资产变迁的卡片流（未竟之蹊）
//   同类优选 = 按你的持仓与自选做基金同类排序（在挑的候选）
// 顶级「资产」的字面是「已经在我名下」，把候选池放进去是名实不符；这与曾经把
// 同类优选塞进「品类持仓」是同一种错。搬出来之后两侧都名副其实：
//   资产 = 我的钱怎么摆 / 放在哪 / 算谁的
//   自选 = 我还没买、正在挑的
//
// 附带收益：/watchlist 的点击深度由 3 次降为 2 次（顶级 → 页面），与概览 / 记账
// 两个顶级对齐——此前「资产」是唯一需要展开两次的顶级。
//
// ⚠️ 名字只到「自选」两个汉字：这一级是用户最先扫的一列，短才扫得动；更长的
// 「自选观察」「自选跟踪」都是新造词，语义并不比「自选」更准。
const WatchRouteConfig = {
  path: "/watch",
  name: "Watch",
  component: Layout,
  redirect: "/watchlist",
  meta: {
    icon: "ep:star",
    title: "自选",
    rank: BASE_RANK,
    showLink: true
  },
  children: [
    {
      path: "/watchlist",
      name: "Watchlist",
      component: () => import("@/views/asset/watchlist/index.vue"),
      meta: {
        title: "我的自选",
        icon: "ep:star",
        rank: 1,
        keepAlive: true,
        // 高密度列表页：隐藏布局级页脚，把整块垂直空间交给表格（#1281）
        hideFooter: true,
        // 隐藏右下角「记一笔」FAB：它会压住表格右下角固定操作列（置顶/关注/移除），
        // 入口改由快捷键 N 承担（useQuickEntryHotkey，首次进页自动提示一次）
        hideQuickEntry: true
      }
    },
    {
      // 未竟之蹊：看「私有思考 + 资产变迁」的卡片流，与 /watchlist 的
      // 「实时数据表格」是两个产品（分工见 docs/features/watchlist.md §1.5.7）。
      path: "/the-road-not-taken",
      name: "Favourites",
      component: () => import("@/views/asset/favorites/index.vue"),
      meta: { title: "特别关注", icon: "ep:opportunity", rank: 2 }
    },
    {
      // #167 收尾：按风险指标横向筛的列表页。端点（fund-risk-types /
      // fund-risk-ranking）早已上线，缺的是这个入口——能力在、用户看不到。
      // 它的输入就是你的持仓与自选（页面 subtitle 原话），产出是候选清单，
      // 属「在挑的」而不是「已持有的」。
      path: "/asset/fund-ranking",
      name: "AssetFundRanking",
      component: () => import("@/views/asset/fund-ranking/index.vue"),
      meta: {
        title: "同类优选",
        icon: "ep:histogram",
        rank: 3,
        showLink: true,
        keepAlive: true
      }
    }
  ]
};

// 4. 导出
export default createWatchRoutes(WatchRouteConfig);
