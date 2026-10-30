import { expect, test } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * 面包屑层级回归网（2026-10-30 实机盘查，Edge）。
 *
 * 为什么必须是 E2E：面包屑的正确性取决于**三层的合谋**——
 * `router/modules` 的层级、permission store 的剪枝口径、`buildBreadcrumb` 的取链规则。
 * 单测只能验第三层；前两层错（例如面包屑读了被 `filterTree` 剪过的侧边栏树）时，
 * 纯函数依然全绿，而用户在页面上看到的是错的父级。
 *
 * 本轮实机盘查抓出的错链（修复前 → 修复后）：
 *
 *   /stocks                   资产概览 / 股票        → 资产管理 / 股票
 *   /funds                    资产概览 / 基金        → 资产管理 / 基金
 *   /investment/holding-import 资产概览 / 导入持仓    → 记账中心 / 导入持仓
 *   /investment/manual        资产概览 / 手动记账    → 记账中心 / 手动记账
 *   /investment/reconcile     资产概览 / E账户对账   → 记账中心 / E账户对账
 *   /asset/asset-entry        资产管理 / 录入资产    → 记账中心 / 录入资产（path 前缀骗了它）
 *   /fund/004369              资产概览 / 产品详情    → 产品详情
 *
 * 判据口径：面包屑**末项**必须等于页面标题（`document.title` 的前半段，由路由守卫
 * 按 `to.matched` 写入），中间项逐个钉死。
 */

const CASES: Array<{ path: string; crumbs: string[] }> = [
  // 四顶级各自的正常页面
  { path: "/welcome", crumbs: ["资产概览", "投资概览"] },
  { path: "/watchlist", crumbs: ["资产管理", "我的关注", "我的自选"] },
  { path: "/asset/precious", crumbs: ["资产管理", "实物资产", "贵金属"] },
  { path: "/inventory", crumbs: ["记账中心", "全面盘点"] },
  // 单页模块：路由两级、菜单与面包屑都只有一级
  { path: "/agent/chat", crumbs: ["账本精灵"] },
  // showLink:false / hidden 的可达页面：父级必须来自路由结构，不能塌回「资产概览」
  { path: "/stocks", crumbs: ["资产管理", "股票"] },
  { path: "/funds", crumbs: ["资产管理", "基金"] },
  { path: "/investment/holding-import", crumbs: ["记账中心", "导入持仓"] },
  { path: "/investment/manual", crumbs: ["记账中心", "手动记账"] },
  { path: "/investment/reconcile", crumbs: ["记账中心", "E账户对账"] },
  {
    path: "/asset/asset-entry",
    crumbs: ["记账中心", "录入资产"]
  },
  // 带参路由：不虚构父级
  { path: "/fund/004369", crumbs: ["产品详情"] }
];

/** 面包屑文字（去掉每项末尾的分隔符 `/`） */
async function crumbsOf(
  page: import("@playwright/test").Page
): Promise<string[]> {
  return (await page.locator(".el-breadcrumb__item").allInnerTexts()).map(s =>
    s.replace(/\//g, "").trim()
  );
}

test.describe("面包屑层级与页面归属一致", () => {
  for (const c of CASES) {
    test(`${c.path} → ${c.crumbs.join(" / ")}`, async ({
      context,
      page,
      baseURL
    }) => {
      await injectSupabaseSession(context, baseURL!);
      await page.goto(`/#${c.path}`);

      // 面包屑随路由异步更新，等它追上页面标题再断言（避免读到上一页的残留）
      await expect
        .poll(async () => (await crumbsOf(page)).join(" / "), {
          timeout: 20_000
        })
        .toBe(c.crumbs.join(" / "));

      // 末项即当前页：与路由守卫写入的 document.title 对齐
      const pageTitle = (await page.title()).split("|")[0].trim();
      expect(c.crumbs[c.crumbs.length - 1]).toBe(pageTitle);
    });
  }
});
