import { expect, test } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * #1565 回归网：**首次**从探市首屏（/explore）跳转进应用页后，侧边栏必须真正渲染。
 *
 * 缺陷形态（#1566 修复前）：/explore 是独立全屏页，路由守卫在已登录分支对它提前 return，
 * 从不组装 `wholeMenus`；首屏落在探市后再**客户端跳转**进 /watchlist 时 `_from.name` 有值，
 * 又会绕过「首次访问」分支 → `wholeMenus` 恒为空 → 侧边栏 `v-loading` 常驻、菜单项 0
 * （表现为「侧边栏消失」，刷新后因为变成首屏直达才恢复）。
 *
 * 本用例为什么必须用 E2E：出问题的是「路由守卫 × permission store × 布局组件」的**联动**，
 * 任何组件级单测都得把守卫与 store mock 掉——正好把出问题的那层挖掉。
 */

/** 侧边栏菜单项（含子菜单）：`NavVertical` 的 el-menu 内 */
const MENU_ITEM =
  ".sidebar-container .el-menu-item, .sidebar-container .el-sub-menu";
/** 侧边栏自身的加载遮罩：`wholeMenus.length === 0` 时 v-loading 常驻 */
const SIDEBAR_LOADING_MASK = ".sidebar-container > .el-loading-mask";

test.describe("探市首屏 → 自选页：侧边栏渲染（#1565 回归）", () => {
  test("已登录首屏落在 /explore，点「前往自选页」后侧边栏有菜单且无加载遮罩", async ({
    context,
    page,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);

    await page.goto("/#/explore");

    // 探市页识别到登录态（这一步同时证明会话注入真的生效，而不是「碰巧没被拦截」）
    const authGuide = page.locator(".auth-guide");
    await expect(authGuide).toBeVisible();

    await authGuide.getByRole("button", { name: /前往自选页/ }).click();

    await expect(page).toHaveURL(/#\/watchlist/);

    // 核心断言 1：菜单真的组装出来了（修复前恒为 0）
    await expect(page.locator(MENU_ITEM).first()).toBeVisible();
    expect(await page.locator(MENU_ITEM).count()).toBeGreaterThan(0);

    // 核心断言 2：侧边栏的加载遮罩不再常驻（修复前 el-loading-mask 一直在转）
    await expect(page.locator(SIDEBAR_LOADING_MASK)).toHaveCount(0);
  });

  test("对照组：首屏直达 /watchlist 的侧边栏与「先探市后跳转」一致", async ({
    context,
    page,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);

    await page.goto("/#/watchlist");
    await expect(page.locator(MENU_ITEM).first()).toBeVisible();
    const directCount = await page.locator(MENU_ITEM).count();

    // 再走一遍「首屏探市 → 点按钮进自选」的路径，两者菜单项数量应一致
    const second = await context.newPage();
    await second.goto("/#/explore");
    await second
      .locator(".auth-guide")
      .getByRole("button", { name: /前往自选页/ })
      .click();
    await expect(second).toHaveURL(/#\/watchlist/);
    await expect(second.locator(MENU_ITEM).first()).toBeVisible();

    expect(await second.locator(MENU_ITEM).count()).toBe(directCount);
    await second.close();
  });

  test("未登录访问 /watchlist 仍被守卫拦到 /login（反向保护，避免上述兜底把权限放水）", async ({
    context,
    page
  }) => {
    // 不注入会话
    await context.clearCookies();
    await page.goto("/#/watchlist");
    await expect(page).toHaveURL(/#\/login/);
    await expect(page.locator(".sidebar-container")).toHaveCount(0);
  });
});
