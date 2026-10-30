/**
 * 面包屑纯函数单测。
 *
 * 背景（2026-10-29 实机走查证据）：静态路由被 `formatTwoStageRoutes` 拍平挂到根 `/`
 * 下，`route.matched` 恒为 `[Home, 页面]`，面包屑因此永远渲染成「总览 / 某页」——
 * 哪怕该页在侧边栏里属于「资产管理 → 品类持仓」。改读菜单树后，上面的层级才是真的。
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
          }
        ]
      },
      {
        path: "investment",
        name: "AssetCategoryGroup",
        meta: { title: "品类持仓" },
        children: [
          {
            path: "/asset/precious",
            name: "AssetPrecious",
            meta: { title: "贵金属" }
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
        meta: { title: "账户家庭" },
        children: [
          {
            path: "/asset/ledgers",
            name: "AssetLedgers",
            meta: { title: "账户管理" }
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
      { path: "/inventory", name: "Inventory", meta: { title: "全面盘点" } }
    ]
  }
];

const titles = (crumbs: { title: string }[]) => crumbs.map(c => c.title);

describe("buildBreadcrumb", () => {
  it("精确命中：返回从顶级到当前页的完整链（不再是「总览 / 某页」）", () => {
    const crumbs = buildBreadcrumb(menus, "/asset/fund-ranking");
    // 真机旧行为是 ['总览','同类优选']——父级错成根目录
    expect(titles(crumbs)).toEqual(["资产管理", "品类持仓", "同类优选"]);
  });

  it("末项不可点击，中间项可点击", () => {
    const crumbs = buildBreadcrumb(menus, "/asset/fund-ranking");
    expect(crumbs[crumbs.length - 1].to).toBeNull();
    expect(crumbs[0].to).toBeTruthy();
  });

  it("中间目录点击落在它的第一个可达子项，而不是空目录路径", () => {
    const crumbs = buildBreadcrumb(menus, "/asset/fund-ranking");
    // 「品类持仓」自身没有组件（EmptyLayout），直接 push 会跳到空白页
    expect(crumbs[1].title).toBe("品类持仓");
    expect(crumbs[1].to).toBe("/asset/precious");
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
      "账户家庭",
      "账户管理",
      "账户详情"
    ]);
  });

  it("当前页标题与末级菜单项同名时不重复追加", () => {
    const crumbs = buildBreadcrumb(menus, "/asset/ledgers", "账户管理");
    expect(titles(crumbs)).toEqual(["资产管理", "账户家庭", "账户管理"]);
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
});
