const Layout = () => import("@/layout/index.vue");

// 1. 「记账中心」占 rank 2 段（home 0 / asset 1 / record 2 / agent 3）
const BASE_RANK = 2;

// 2. 工厂函数：子级 rank 用 0~99 的相对值
const createRecordRoutes = (routeConfig: any) => {
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
// 为什么要有这个顶级（2026-10-29 侧边栏重组）：
//
// 「记账」是一个独立的财务动作——它不产生任何判断，只把已经发生的事实落库。
// 此前这类页面被劈在两个顶级下：「全面盘点 / 交易流水 / 分红与股息」在 home，
// 「对账中心」在 asset。用户记完一笔账，想核对，得先想「核对在哪个顶级」。
//
// 本顶级只收三种东西，顺序即记账的实际动线：
//   录入（全面盘点 → 各导入入口）→ 流水（交易 / 分红）→ 核对（对账中心）
//
// ⚠️ 反向约束：凡是**读**（复盘 / 持仓分析）或**配置**（组合 / 账户 / 策略）的页面
// 都不许放进来，否则又回到「两个顶级各装一半」的老问题。
const RecordRouteConfig = {
  path: "/record",
  name: "Record",
  component: Layout,
  redirect: "/inventory",
  meta: {
    icon: "ep:edit-pen",
    title: "记账中心",
    rank: BASE_RANK,
    showLink: true
  },
  children: [
    {
      // 页面副标题自述「选择资产大类，快速录入或导入」——它的实质是**录入工作台**，
      // 不是只读的盘点报表。归本顶级而非「资产概览」，正名于此。
      path: "/inventory",
      name: "Inventory",
      component: () => import("@/views/asset/inventory/index.vue"),
      meta: {
        title: "全面盘点",
        icon: "ep:document-checked",
        rank: 1,
        hideQuickEntry: true
      }
    },
    {
      path: "/transactions",
      name: "TransactionList",
      component: () => import("@/views/asset/TransactionList.vue"),
      meta: { title: "交易流水", icon: "ep:list", rank: 2 }
    },
    {
      // 原名「分红与股息」（5 字）。菜单统一 4 字，语义不变：分红 + 股息本就是
      // 同一类「被动到账」，合称不损失信息。
      path: "/dividends",
      name: "Dividends",
      component: () => import("@/views/asset/dividends/index.vue"),
      meta: {
        title: "分红股息",
        icon: "ep:coin",
        rank: 3,
        keepAlive: true
      }
    },
    {
      // 原菜单名「对账工作台」（5 字）→「对账中心」；页内 h1 与各处提示文案已同步
      // 改名（2026-10-30），避免侧边栏与页头两个名字并存。
      // #1240 P0-C：三域 Tab 入口，P1/P2 逐域接入。
      path: "/investment/reconcile-workbench",
      name: "ReconcileWorkbench",
      component: () =>
        import("@/views/asset/investment/reconcile-workbench/index.vue"),
      meta: {
        title: "对账中心",
        icon: "ep:finished",
        rank: 4,
        hideQuickEntry: true
      }
    },

    // ── 以下为录入流程页：不进侧边栏，但归本顶级 ────────────────
    // 它们此前挂在「投资管理」目录下（一个叫"品类持仓"的目录里塞着六个录入页），
    // 面包屑会显示「资产管理 / 品类持仓 / 对账单导入」——语义错位。归到记账后
    // 面包屑变成「记账中心 / 对账单导入」，与实际动作一致。
    {
      path: "/inventory/investment/import",
      name: "InvestmentImport",
      component: () => import("@/views/asset/investment/import/index.vue"),
      meta: {
        title: "对账单导入",
        icon: "ep:document",
        rank: 11,
        showLink: false,
        hideQuickEntry: true
      }
    },
    {
      // 持仓快照导入（落 positions 不建流水；#1788 由「E账户导入」改名对齐三处
      // 入口文案。目录名仍为 eaccount-import/ —— 卡片只约定 path，且 api/eaccount.ts
      // 等同族标识沿用，避免无谓 churn）
      path: "/investment/holding-import",
      name: "InvestmentHoldingImport",
      component: () =>
        import("@/views/asset/investment/eaccount-import/index.vue"),
      meta: {
        title: "导入持仓",
        icon: "ep:upload",
        rank: 12,
        showLink: false,
        hideQuickEntry: true
      }
    },
    {
      path: "/investment/manual",
      name: "InvestmentManual",
      component: () => import("@/views/asset/investment/manual/index.vue"),
      meta: {
        title: "手动记账",
        icon: "ep:edit",
        rank: 13,
        showLink: false,
        hideQuickEntry: true
      }
    },
    {
      path: "/asset/asset-entry",
      name: "AssetEntry",
      component: () => import("@/views/asset/AssetEntry.vue"),
      meta: {
        title: "录入资产",
        icon: "ep:plus",
        rank: 14,
        showLink: false,
        hideQuickEntry: true
      }
    },
    {
      // E账户对账中心（从导入流程/菜单进入，不在侧边栏展示）
      path: "/investment/reconcile",
      name: "InvestmentReconcile",
      component: () => import("@/views/asset/investment/reconcile/index.vue"),
      meta: {
        title: "E账户对账",
        icon: "ep:document-checked",
        rank: 15,
        showLink: false,
        hideQuickEntry: true
      }
    }
  ]
};

// 4. 导出
export default createRecordRoutes(RecordRouteConfig);
