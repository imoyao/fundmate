const Layout = () => import("@/layout/index.vue");
const EmptyLayout = () => import("@/layout/components/EmptyLayout.vue");

// 1. 「资产管理」占 rank 100 段，与 home.ts（0 段）、record.ts、agent.ts 彻底隔离
const BASE_RANK = 100;

// #2152：/asset 直接子级与孙级曾共用排序键段——两组 rank 完全相等
// （贵金属 ≡ 账户管理、房产 ≡ 策略分析、智能分析 ≡ 投资组合），菜单次序只能靠
// 数组先后兜底，改数组顺序就会跳位置。孙级改占 200+ 段：直接子级相对 rank 用
// 0~99（→100~199），孙级用 200~299，两段永不相交。
// 守卫见 __tests__/routeRankGuard.spec.ts。
//
// 2026-10-29 侧边栏重组：直接子级由「一堆平级页面」改为 **4 个语义分组目录**，
// 孙级数量从 3 增到 10。工厂函数因此**不再**给孙级自动加 200 偏移——各分组的
// 孙级 rank 手写为最终值（201/202/... 每 10 个一组），否则四个分组会全部从
// 201 起算、彼此撞键。守卫已同步扩展为「asset 全部孙级 ∈[200,299] 且全树唯一」。
const GRANDCHILD_MIN = 200;
const GRANDCHILD_MAX = 300;

// 2. 工厂函数：只处理直接子级（+100）；孙级 rank 已是最终值，原样保留
const createAssetRoutes = (routeConfig: any) => {
  const children = routeConfig.children.map((child: any) => {
    if (typeof child.meta?.rank === "number") {
      const isGrandchild =
        child.meta.rank >= GRANDCHILD_MIN && child.meta.rank < GRANDCHILD_MAX;
      // 孙级（含分组目录的 children）手写 2xx，不再叠加偏移
      if (isGrandchild) {
        throw new Error(
          `[router] ${child.name ?? child.path} 的 rank=${child.meta.rank} 落在孙级段，` +
            `但它声明在 /asset 直接子级上——请改为 0~99 的相对值`
        );
      }
    }
    return {
      ...child,
      meta: {
        ...child.meta,
        rank: (child.meta?.rank || 0) + BASE_RANK
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
// 分组口径（2026-10-30 二次修订，按「页面实际是什么」切，不再按名词凑 4 字）：
//   组合策略 = 一篮子的做法（投资组合、策略分析、定投计划）
//   实物资产 = 要手动登记、手动估值的线下资产（贵金属、房产）
//   我的关注 = 还没买、在挑、在盯的候选池（我的自选、特别关注、同类优选）
//   账户成员 = 这笔钱记在哪个账户、算谁的（账户管理、家庭成员）
//
// 2026-10-29 第一版用的是「组合策略 / 品类持仓 / 观察名单 / 账户家庭」，
// 三个名字是硬凑的：
//   - 「品类持仓」把**同类优选**也装了进来，而它是「按你的持仓与自选做基金同类
//     排序」的**筛选页**，不是持仓（页面 subtitle 自己写着）；名字与成员互相否定。
//   - 「观察名单」是 watchlist 的直译，读者要在脑子里翻一次英文。
//   - 「账户家庭」把「账户」+「家庭成员」两个名词硬拼，拼完什么也没说——
//     用户原话：「账户家庭是什么意思？说人话」。
// 结论：名字读不懂，通常是**成员装错**，改字面治不了。
//
// ⚠️ 只放**配置与档案**。凡是「把事实录进来」的页面（全面盘点 / 各类导入 /
// 对账单）一律归 record.ts；纯净的读页面（复盘 / 持仓分析）归 home.ts。
const AssetRouteConfig = {
  path: "/asset",
  name: "Asset",
  component: Layout,
  meta: {
    icon: "ep:coin",
    title: "资产管理",
    rank: 1, // 模块内相对位置
    showLink: true
  },
  children: [
    // ── 分组 1：组合策略 ──────────────────────────────────────
    {
      // 目录型父路由：redirect 必须落在**可见**子级上，否则复现 #1699「点父级跳空白页」
      path: "portfolio-group",
      name: "AssetPortfolioGroup",
      component: EmptyLayout,
      redirect: "/asset/portfolios",
      meta: { title: "组合策略", icon: "ep:collection", rank: 1 },
      children: [
        {
          path: "/asset/portfolios",
          name: "PortfolioList",
          component: () => import("@/views/asset/portfolio/index.vue"),
          meta: { title: "投资组合", icon: "ep:collection", rank: 201 }
        },
        {
          path: "/asset/strategies",
          name: "Strategies",
          component: () => import("@/views/asset/strategies/index.vue"),
          meta: {
            title: "策略分析",
            icon: "ep:data-analysis",
            rank: 202,
            showLink: true
          }
        },
        {
          // #2138：账本能力的「计划层」——先有计划，再有流水。
          // 归「组合策略」而不是「记账」：定投是**决策/执行**，不是记账事实。
          path: "/asset/recurring",
          name: "AssetRecurring",
          component: () => import("@/views/asset/recurring/index.vue"),
          meta: { title: "定投计划", icon: "ep:calendar", rank: 203 }
        }
      ]
    },
    // ── 分组 2：实物资产 ──────────────────────────────────────
    {
      // 前身「投资管理」→「品类持仓」→ 本名。两次都名实不符：
      // 「投资管理」让人以为这里是全部投资入口（股票/基金是隐藏路由，根本不在这）；
      // 「品类持仓」更离谱——除贵金属/房产外还装了**同类优选**，而那是筛选页不是持仓。
      // 现在只装「要手动登记、手动估值」的线下资产，名字与成员终于对得上。
      // 同类优选已移到分组 3「我的关注」：它的输入就是你的持仓与自选，属于候选池。
      path: "investment",
      name: "AssetCategoryGroup",
      component: EmptyLayout,
      redirect: "/asset/precious",
      meta: { title: "实物资产", icon: "ep:folder-opened", rank: 2 },
      children: [
        {
          // 路径带 /asset 前缀，与同层兄弟一致。
          // 原为 "/precious"：vue-router 4 里子路由 path 以 / 开头即**绝对路径**、
          // 不拼父级前缀（#1849 路径统一）。
          path: "/asset/precious",
          // #1798 入口：侧边栏 + 全景页「资产构成」贵金属行直跳（CategoryBalanceTable）
          name: "AssetPrecious",
          component: () => import("@/views/asset/precious/index.vue"),
          meta: { title: "贵金属", icon: "ep:medal", rank: 211, showLink: true }
        },
        {
          path: "/asset/realestate",
          // #1798 入口：侧边栏 + 全景页「资产构成」房产行直跳
          name: "AssetRealEstate",
          component: () => import("@/views/asset/realestate/index.vue"),
          meta: { title: "房产", icon: "ep:house", rank: 212, showLink: true }
        }
      ]
    },
    // ── 分组 3：我的关注 ──────────────────────────────────────
    {
      // 前身叫「观察名单」——watchlist 的直译，读者要在脑子里翻一次英文才懂。
      // 三个成员的共同点是「还没买、在挑、在盯」：
      //   我的自选 = 实时数据表格（我已加入、在盯的标的）
      //   特别关注 = 私有思考 + 资产变迁的卡片流（未竟之蹊）
      //   同类优选 = 按你的持仓与自选做基金同类排序（在挑的候选）
      // 「我的自选」原在 home.ts 的「总览」下、「特别关注」在「资产管理」下——
      // 同一件心事（还没买、在盯）隔着两个顶级，这是上一轮最典型的劈裂。
      path: "watch",
      name: "AssetWatchGroup",
      component: EmptyLayout,
      redirect: "/watchlist",
      meta: { title: "我的关注", icon: "ep:star", rank: 3 },
      children: [
        {
          path: "/watchlist",
          name: "Watchlist",
          component: () => import("@/views/asset/watchlist/index.vue"),
          meta: {
            title: "我的自选",
            icon: "ep:star",
            rank: 221,
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
          meta: { title: "特别关注", icon: "ep:opportunity", rank: 222 }
        },
        {
          // #167 收尾：按风险指标横向筛的列表页。端点（fund-risk-types /
          // fund-risk-ranking）早已上线，缺的是这个入口——能力在、用户看不到。
          // 2026-10-30 从「品类持仓」移来：它的输入就是你的持仓与自选（页面 subtitle
          // 原话），产出是候选清单，属「在挑的」而不是「已持有的」。
          path: "/asset/fund-ranking",
          name: "AssetFundRanking",
          component: () => import("@/views/asset/fund-ranking/index.vue"),
          meta: {
            title: "同类优选",
            icon: "ep:histogram",
            rank: 223,
            showLink: true,
            keepAlive: true
          }
        }
      ]
    },
    // ── 分组 4：账户成员 ──────────────────────────────────────
    {
      // 前身叫「账户家庭」——把「账户」和「家庭成员」两个名词硬拼成一个词，
      // 拼完什么也没说（用户原话：「账户家庭是什么意思？说人话」）。
      // 这一组的共同点是「这笔钱记在哪个账户、算谁的」：
      //   账户管理 = 钱放在哪（银行卡/支付宝/券商…，每个账户归属某个成员）
      //   家庭成员 = 算谁的（#1173 账户归属维度的档案与维护入口）
      // 两者合起来就是「账户 + 成员」两份档案，故叫「账户成员」。
      // 此前账户管理(3)、家庭成员(3.5)、定投计划(3.6) 靠小数 rank 挤在一起，
      // 小数补位本身就是「已无序可插」的病征。
      path: "household",
      name: "AssetHouseholdGroup",
      component: EmptyLayout,
      redirect: "/asset/ledgers",
      meta: { title: "账户成员", icon: "ep:wallet", rank: 4 },
      children: [
        {
          path: "/asset/ledgers",
          name: "AssetLedgers",
          component: () => import("@/views/asset/ledgers/index.vue"),
          meta: { title: "账户管理", icon: "ep:wallet", rank: 231 }
        },
        {
          // #1173：账户归属维度——「这笔钱是谁的」的档案与维护入口
          path: "/asset/family",
          name: "AssetFamilyMembers",
          component: () => import("@/views/asset/family/index.vue"),
          meta: { title: "家庭成员", icon: "ep:user", rank: 232 }
        }
      ]
    },
    // ── 隐藏下钻页（不进菜单，但保留在 /asset 直接子级以维持面包屑锚点）──
    {
      // #1133 路由归并：场外基金 / 场内证券的聚合下钻页收敛为 /funds 与 /stocks，
      // 与「资产总览 → 产品类型」的下钻目标合一。
      // 这两条**不是**可选装饰——`useLedgerList.ts`（点账户里的股票/基金持仓）与
      // `ResultSupplements.vue`（导入结果补录）都按 `{ name: "AssetStocks" }` /
      // `{ name: "AssetFunds" }` 跳转，删掉即静默死链（`check_router_links.mjs` 会报）。
      // 2026-10-30 从「品类持仓」移到直接子级：它们是「按产品类型看全部持仓」的
      // 下钻目标，与「实物资产」「我的关注」两组都不搭，挂哪组都是硬塞。
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
