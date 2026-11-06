const Layout = () => import("@/layout/index.vue");

// 1. 「资产」占 rank 100 段，与 home.ts（0 段）、watch.ts（2 段）、record.ts（3 段）、
//    agent.ts（4 段）彻底隔离。
const BASE_RANK = 100;

// 2. 直接子级 rank 只接受 0~99 的相对值（工厂统一 +100 → 落 100~199）。
//    2026-11-01 起 /asset 是**平铺**结构，「我的关注」已独立成 watch.ts、其余三个分组
//    降级为平级页面，因此孙级段（2xx）不复存在。若有人手写 1xx/2xx 的最终值，这里直接
//    抛错——叠加 BASE_RANK 后会出现「13x ≡ 隐藏详情页」这类跨条目撞键（#2152 的老病）。
const RELATIVE_RANK_LIMIT = 100;

const createAssetRoutes = (routeConfig: any) => {
  const children = routeConfig.children.map((child: any) => {
    const rank = child.meta?.rank;
    if (typeof rank === "number" && rank >= RELATIVE_RANK_LIMIT) {
      throw new Error(
        `[router] ${child.name ?? child.path} 的 rank=${rank} 不是相对值——` +
          `/asset 直接子级请写 0~99，工厂会统一 +${BASE_RANK}`
      );
    }
    return {
      ...child,
      meta: {
        ...child.meta,
        rank: (rank || 0) + BASE_RANK
      }
    };
  });
  return {
    ...routeConfig,
    children
  };
};

// 3. 定义原始配置
//
// 结构（2026-11-01 三次修订）：**平铺，不再有分组目录**。
//
// 判据是顶级名与成员必须互相成立：「资产」= 已经在我名下的东西。由此得两个动作：
//   ① 「我的关注」整组搬出去做一级——它的成员是**还没买的候选池**（我的自选 /
//      特别关注 / 同类优选），放进「资产」属于名实不符，与当初把同类优选塞进
//      「品类持仓」是同一种错。搬走后 watchlist 的点击深度从 3 降到 2。
//   ② 剩下的三个分组（组合策略 / 实物资产 / 账户成员）撤销目录层，叶子直接挂在这里：
//      它们是同一类东西——"我的钱怎么摆、放在哪、算谁的"——分组只增加了点击深度，
//      没有增加区分度。原「组合策略」3 项、「账户成员」2 项本就是纯名词拼接
//      （「组合策略」「账户成员」都解释不了为什么这几项在一起）。
//
// 顺序即语义相近度，成对相邻（不靠目录层也读得出分组）：
//   投资组合 · 策略分析 · 定投计划  —— 一篮子的做法
//   账户管理 · 家庭成员            —— 钱放在哪、算谁的
//   贵金属 · 房产                  —— 要手动登记、手动估值的线下资产
//
// ⚠️ 只放**配置与档案**。凡是「把事实录进来」的页面（全面盘点 / 各类导入 /
// 对账单）一律归 record.ts；纯净的读页面（复盘 / 持仓分析）归 home.ts。
const AssetRouteConfig = {
  path: "/asset",
  name: "Asset",
  component: Layout,
  meta: {
    icon: "ep:coin",
    title: "资产",
    rank: 1, // 模块内相对位置
    showLink: true
  },
  children: [
    {
      path: "/asset/portfolios",
      name: "PortfolioList",
      component: () => import("@/views/asset/portfolio/index.vue"),
      meta: { title: "投资组合", icon: "ep:collection", rank: 1 }
    },
    {
      path: "/asset/strategies",
      name: "Strategies",
      component: () => import("@/views/asset/strategies/index.vue"),
      meta: {
        title: "策略分析",
        icon: "ep:data-analysis",
        rank: 2,
        showLink: true
      }
    },
    {
      // #2138：账本能力的「计划层」——先有计划，再有流水。
      // 归「资产」而不是「记账」：定投是**决策/执行**，不是记账事实。
      path: "/asset/recurring",
      name: "AssetRecurring",
      component: () => import("@/views/asset/recurring/index.vue"),
      meta: { title: "定投计划", icon: "ep:calendar", rank: 3 }
    },
    {
      path: "/asset/ledgers",
      name: "AssetLedgers",
      component: () => import("@/views/asset/ledgers/index.vue"),
      meta: { title: "账户管理", icon: "ep:wallet", rank: 4 }
    },
    {
      // #1173：账户归属维度——「这笔钱是谁的」的档案与维护入口。
      // 留在「资产」而不是搬进个人中心：建/编辑账户时 `OwnerMemberSelect` 要选它，
      // 页面自述也是「把账户归属到具体成员」，与用户资料无关。
      path: "/asset/family",
      name: "AssetFamilyMembers",
      component: () => import("@/views/asset/family/index.vue"),
      meta: { title: "家庭成员", icon: "ep:user", rank: 5 }
    },
    {
      // 路径带 /asset 前缀，与同层兄弟一致。
      // 原为 "/precious"：vue-router 4 里子路由 path 以 / 开头即**绝对路径**、
      // 不拼父级前缀（#1849 路径统一）。
      // #1798 入口：侧边栏 + 全景页「资产构成」贵金属行直跳（CategoryBalanceTable）
      path: "/asset/precious",
      name: "AssetPrecious",
      component: () => import("@/views/asset/precious/index.vue"),
      meta: { title: "贵金属", icon: "ep:medal", rank: 6, showLink: true }
    },
    {
      // #1798 入口：侧边栏 + 全景页「资产构成」房产行直跳
      path: "/asset/realestate",
      name: "AssetRealEstate",
      component: () => import("@/views/asset/realestate/index.vue"),
      meta: { title: "房产", icon: "ep:house", rank: 7, showLink: true }
    },
    // ── 隐藏下钻页（不进菜单，但保留在 /asset 直接子级以维持面包屑锚点）──
    {
      // #1133 路由归并：场外基金 / 场内证券的聚合下钻页收敛为 /funds 与 /stocks，
      // 与「资产总览 → 产品类型」的下钻目标合一。
      // 这两条**不是**可选装饰——`useLedgerList.ts`（点账户里的股票/基金持仓）与
      // `ResultSupplements.vue`（导入结果补录）都按 `{ name: "AssetStocks" }` /
      // `{ name: "AssetFunds" }` 跳转，删掉即静默死链（`check_router_links.mjs` 会报）。
      path: "/stocks",
      name: "AssetStocks",
      component: () => import("@/views/asset/stocks/index.vue"),
      meta: {
        title: "股票",
        icon: "ep:trend-charts",
        rank: 61,
        showLink: false
      }
    },
    {
      path: "/funds",
      name: "AssetFunds",
      component: () => import("@/views/asset/funds/index.vue"),
      meta: { title: "基金", icon: "ep:box", rank: 62, showLink: false }
    },
    // ── 隐藏详情页（不进菜单，但保留在 /asset 直接子级以维持面包屑锚点）──
    {
      path: "/asset/ledgers/:id",
      name: "LedgerDetail",
      component: () => import("@/views/asset/ledgers/detail.vue"),
      meta: {
        title: "账户详情",
        icon: "ep:wallet",
        rank: 31,
        showLink: false,
        hidden: true
      }
    },
    {
      path: "/asset/portfolios/:id",
      name: "PortfolioDetail",
      component: () => import("@/views/asset/portfolio/detail.vue"),
      meta: {
        title: "组合详情",
        icon: "ep:collection",
        rank: 51,
        showLink: false,
        hidden: true
      }
    }
  ]
};

// 4. 导出
export default createAssetRoutes(AssetRouteConfig);
