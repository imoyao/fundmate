/**
 * 面包屑纯函数单测。
 *
 * 背景（2026-10-29 实机走查证据）：静态路由被 `formatTwoStageRoutes` 拍平挂到根 `/`
 * 下，`route.matched` 恒为 `[Home, 页面]`，面包屑因此永远渲染成「总览 / 某页」——
 * 哪怕该页在侧边栏里属于「资产管理 → 我的关注」。改读菜单树后，上面的层级才是真的。
 *
 * vitest 的 environment 是 `node`（无 DOM），组件挂载测不了，故把「树里找路径」
 * 抽成纯函数。这些用例同时是**结构契约**：改路由层级时这里必须跟着红。
 */
import { describe, it, expect } from "vitest";
import { buildBreadcrumb, type BreadcrumbNode } from "../breadcrumb";

/** 复刻重构后的真实菜单结构（4 顶级 / 4 分组） */
const menus: BreadcrumbNode[] = [
  {
    path: "/",
    name: "Home",
    meta: { title: "资产概览", showLink: false },
    children: [
      { path: "/welcome", name: "Welcome", meta: { title: "投资概览" } },
      { path: "/panorama", name: "AssetPanorama", meta: { title: "资产总览" } }
    ]
  },
  {
    path: "/asset",
    name: "Asset",
    meta: { title: "资产管理" },
    children: [
      {
        path: "portfolio-group",
        name: "AssetPortfolioGroup",
        meta: { title: "组合策略" },
        children: [
          {
            path: "/asset/portfolios",
            name: "PortfolioList",
            meta: { title: "投资组合" }
          },
          {
            path: "/asset/strategies",
            name: "Strategies",
            meta: { title: "策略分析" }
          },
          {
            path: "/asset/recurring",
            name: "AssetRecurring",
            meta: { title: "定投计划" }
          }
        ]
      },
      {
        path: "investment",
        name: "AssetCategoryGroup",
        meta: { title: "实物资产" },
        children: [
          {
            path: "/asset/precious",
            name: "AssetPrecious",
            meta: { title: "贵金属" }
          },
          {
            path: "/asset/realestate",
            name: "AssetRealEstate",
            meta: { title: "房产" }
          }
        ]
      },
      {
        // 2026-10-30：同类优选从「实物资产」（原「品类持仓」）移到「我的关注」——
        // 它是基金筛选页不是持仓，夹具跟真实树走，否则用例对着旧结构自证。
        path: "watch",
        name: "AssetWatchGroup",
        meta: { title: "我的关注" },
        children: [
          {
            path: "/watchlist",
            name: "Watchlist",
            meta: { title: "我的自选" }
          },
          {
            path: "/asset/fund-ranking",
            name: "AssetFundRanking",
            meta: { title: "同类优选" }
          }
        ]
      },
      {
        path: "household",
        name: "AssetHouseholdGroup",
        meta: { title: "账户成员" },
        children: [
          {
            path: "/asset/ledgers",
            name: "AssetLedgers",
            meta: { title: "账户管理" }
          },
          {
            path: "/asset/family",
            name: "AssetFamilyMembers",
            meta: { title: "家庭成员" }
          }
        ]
      },
      {
        path: "/asset/ledgers/:id",
        name: "LedgerDetail",
        meta: { title: "账户详情", hidden: true }
      }
    ]
  },
  {
    path: "/record",
    name: "Record",
    meta: { title: "记账中心" },
    children: [
      { path: "/inventory", name: "Inventory", meta: { title: "全面盘点" } },
      {
        path: "/transactions",
        name: "TransactionList",
        meta: { title: "交易流水" }
      },
      { path: "/dividends", name: "Dividends", meta: { title: "分红股息" } },
      {
        path: "/investment/reconcile-workbench",
        name: "ReconcileWorkbench",
        meta: { title: "对账中心" }
      }
    ]
  },
  {
    // 账本精灵：路由两级（Layout 容器 + 页面），但菜单层只有一级——
    // 唯一可见子项会被侧边栏拍平，面包屑必须跟着拍平（见下方用例）。
    path: "/agent",
    name: "Agent",
    meta: { title: "账本精灵", showLink: false },
    children: [
      {
        path: "/agent/chat",
        name: "AgentChat",
        meta: { title: "账本精灵" }
      }
    ]
  }
];

const titles = (crumbs: { title: string }[]) => crumbs.map(c => c.title);

describe("buildBreadcrumb", () => {
  it("精确命中：返回从顶级到当前页的完整链（不再是「总览 / 某页」）", () => {
    const crumbs = buildBreadcrumb(menus, "/asset/fund-ranking");
    // 真机旧行为是 ['总览','同类优选']——父级错成根目录
    expect(titles(crumbs)).toEqual(["资产管理", "我的关注", "同类优选"]);
  });

  it("末项不可点击，中间项可点击", () => {
    const crumbs = buildBreadcrumb(menus, "/asset/fund-ranking");
    expect(crumbs[crumbs.length - 1].to).toBeNull();
    expect(crumbs[0].to).toBeTruthy();
  });

  it("中间目录点击落在它的第一个可达子项，而不是空目录路径", () => {
    const crumbs = buildBreadcrumb(menus, "/asset/fund-ranking");
    // 「我的关注」自身没有组件（EmptyLayout），直接 push 会跳到空白页
    expect(crumbs[1].title).toBe("我的关注");
    expect(crumbs[1].to).toBe("/watchlist");
  });

  it("showLink:false 的顶级仍出现在链里（它是用户看到的目录标题）", () => {
    expect(titles(buildBreadcrumb(menus, "/welcome"))).toEqual([
      "资产概览",
      "投资概览"
    ]);
  });

  it("详情页（菜单里没有该 path）：取最长前缀并追加当前页标题", () => {
    const crumbs = buildBreadcrumb(menus, "/asset/ledgers/1", "账户详情");
    // `/asset/ledgers/:id` 是隐藏路由，不作为展示节点；靠前缀命中 `/asset/ledgers`
    expect(titles(crumbs)).toEqual([
      "资产管理",
      "账户成员",
      "账户管理",
      "账户详情"
    ]);
  });

  it("当前页标题与末级菜单项同名时不重复追加", () => {
    const crumbs = buildBreadcrumb(menus, "/asset/ledgers", "账户管理");
    expect(titles(crumbs)).toEqual(["资产管理", "账户成员", "账户管理"]);
  });

  it("隐藏节点（hidden:true）不作为菜单项出现，当前页标题只追加一次", () => {
    const crumbs = buildBreadcrumb(menus, "/asset/ledgers/9", "账户详情");
    // `/asset/ledgers/:id` 是 hidden 路由，不能既当菜单项又当"当前页"重复两次
    expect(titles(crumbs).filter(t => t === "账户详情").length).toBe(1);
    expect(crumbs.length).toBe(4);
  });

  it("路由不存在 → 返回空数组，由调用方兜底（不返回半截错误链）", () => {
    expect(buildBreadcrumb(menus, "/nope/whatever")).toEqual([]);
  });

  it("前缀匹配有边界：/asset/bcx 不得命中 /asset/bc", () => {
    const tree: BreadcrumbNode[] = [
      {
        path: "/asset",
        meta: { title: "资产管理" },
        children: [{ path: "/asset/bc", meta: { title: "边界测试" } }]
      }
    ];
    const crumbs = buildBreadcrumb(tree, "/asset/bcx");
    // 允许退到上级「资产管理」，但绝不能把 /asset/bc 当成它的父级
    expect(titles(crumbs)).not.toContain("边界测试");
  });

  it("菜单为空（首屏未组装）→ 空数组，不抛错", () => {
    expect(buildBreadcrumb([], "/welcome", "投资概览")).toEqual([]);
    expect(buildBreadcrumb(undefined, "/welcome", "投资概览")).toEqual([]);
  });

  it("记账中心：独立顶级，父级不再是「总览」", () => {
    expect(titles(buildBreadcrumb(menus, "/inventory"))).toEqual([
      "记账中心",
      "全面盘点"
    ]);
  });

  it("每个 crumb 的 key 唯一（同名节点不会撞 key 丢项）", () => {
    const crumbs = buildBreadcrumb(menus, "/asset/fund-ranking");
    const keys = crumbs.map(c => c.key);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("单子项目录（账本精灵）在面包屑里同样拍平：只剩 1 级，与侧边栏一致", () => {
    // 侧边栏 hasOneShowingChild 只显示「账本精灵」，若面包屑仍渲染「账本精灵 /
    // 账本精灵」两级，就等于逼着菜单加 `showParent` 来凑（2026-10-30 的错误方向）。
    expect(titles(buildBreadcrumb(menus, "/agent/chat"))).toEqual(["账本精灵"]);
  });

  it("判据非空转：子项显式 showParent 时目录层必须保留（旧写法仍能渲染两级）", () => {
    const withParent: BreadcrumbNode[] = [
      {
        path: "/x",
        meta: { title: "分组X" },
        children: [
          { path: "/x/1", meta: { title: "页面一", showParent: true } }
        ]
      }
    ];
    expect(titles(buildBreadcrumb(withParent, "/x/1"))).toEqual([
      "分组X",
      "页面一"
    ]);
  });

  it("多子项目录不折叠：记账中心仍是 2 级（拍平只针对单可见子项）", () => {
    expect(titles(buildBreadcrumb(menus, "/dividends"))).toEqual([
      "记账中心",
      "分红股息"
    ]);
  });
});
