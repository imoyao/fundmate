import { expect, test } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * 标签栏（lay-tag）的回归网（#980 拆分配套）。
 *
 * 为什么必须 E2E：标签栏的行为是「多标签 store × 路由 × 右键菜单」三者联动的结果——
 * `showMenuModel` 要读当前标签在 `multiTags` 里的下标、`deleteMenu` 要写 store 再跳路由、
 * 右键菜单的显隐又依赖 store 快照。任何组件级单测都得把这层联动整个 mock 掉，
 * 正好把要验的那层挖空。纯函数（`tagMenuModel` / `useTagScroll`）另有单测，这里只钉
 * 「拆分后界面上还认得出、点得动」。
 *
 * 三条用例分别对应对拆分最敏感的三处：
 * 1. 标签栏照常渲染（模板逐字未改的兜底证据）；
 * 2. 客户端跳转能加标签并切高亮（`dynamicRouteTag` / `tagOnClick` 搬走后的接线）；
 * 3. 右键菜单能弹出且含「关闭当前标签页」（`openMenu` + `showMenuModel` 搬走后的接线）。
 */

/** 标签栏容器：`v-if="!showTags"` 决定它是否在页面上 */
const TAGS_VIEW = ".tags-view";
/** 单个标签（含固定标签） */
const TAG_ITEM = ".tags-view .scroll-item";
/** 标签内的关闭按钮 */
const TAG_CLOSE = ".tags-view .scroll-item .el-icon-close";
/** 右键菜单（v-show 控制显隐，因此元素恒在 DOM 里） */
const CONTEXT_MENU = ".tags-view .contextmenu";

/** 打开侧边栏里的某个二级菜单项（先展开父级） */
async function gotoSidebarMenu(
  page: import("@playwright/test").Page,
  parent: string,
  child: string
) {
  const subTitle = page
    .locator(".sidebar-container .el-sub-menu__title")
    .filter({ hasText: parent });
  await expect(subTitle.first()).toBeVisible();
  await subTitle.first().click();

  const item = page
    .locator(".sidebar-container .el-menu-item")
    .filter({ hasText: child });
  await expect(item.first()).toBeVisible();
  await item.first().click();
}

test.describe("标签栏渲染与交互（#980 拆分回归）", () => {
  test("首屏标签栏可见，固定标签没有关闭按钮", async ({
    context,
    page,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await page.goto("/#/watchlist");

    await expect(page.locator(TAGS_VIEW)).toBeVisible();
    await expect(page.locator(TAG_ITEM).first()).toBeVisible();

    // 标签标题取路由 meta.title，至少得有一个非空
    const titles = await page.locator(`${TAG_ITEM} .tag-title`).allInnerTexts();
    expect(titles.filter(t => t.trim().length > 0).length).toBeGreaterThan(0);

    // 首个标签是固定标签（routerArrays）：不渲染关闭按钮
    await expect(page.locator(TAG_ITEM).first().locator(TAG_CLOSE)).toHaveCount(
      0
    );
  });

  test("侧边栏跳转会新增标签，并把新标签标为激活", async ({
    context,
    page,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await page.goto("/#/watchlist");

    // 等标签栏真正渲染出来再数（固定标签由路由初始化，数量本身不固定）
    await expect(page.locator(TAG_ITEM).first()).toBeVisible();
    const before = await page.locator(TAG_ITEM).count();

    await gotoSidebarMenu(page, "资产管理", "策略分析");
    await expect(page).toHaveURL(/#\/asset\/strategies/);

    // 标签数量真的多了一个（`dynamicRouteTag` + 路由 watch 的接线还在）
    await expect(page.locator(TAG_ITEM)).toHaveCount(before + 1);
    await expect(
      page.locator(`${TAG_ITEM}.is-active .tag-title`).first()
    ).toHaveText("策略分析");
  });

  test("右键标签弹出上下文菜单，含「关闭当前标签页」", async ({
    context,
    page,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await page.goto("/#/watchlist");

    await expect(page.locator(TAG_ITEM).first()).toBeVisible();
    const before = await page.locator(TAG_ITEM).count();

    // 先造出一个可关闭的新标签，否则右键固定标签只会给「重新加载」
    await gotoSidebarMenu(page, "资产管理", "策略分析");
    await expect(page.locator(TAG_ITEM)).toHaveCount(before + 1);

    // 右键刚加的那个（最后一个）标签
    await page.locator(TAG_ITEM).last().click({ button: "right" });

    const menu = page.locator(CONTEXT_MENU);
    await expect(menu).toBeVisible();
    await expect(menu).toContainText("关闭当前标签页");
    await expect(menu).toContainText("关闭全部标签页");
  });
});
