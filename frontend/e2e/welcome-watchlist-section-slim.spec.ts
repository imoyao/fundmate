import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * #980 批 B10 回归网：首页「持仓市值最大资产」区块拆分后的接线（440 → 127 行）。
 *
 * 这一批只做两件事：整块自选区块（含「添加自选」弹窗）搬进
 * `WelcomeWatchlistSection.vue`，全页 208 行跨组件 `:deep()` 样式搬进
 * `styles/_welcome-deep.scss`。两件事都有「静态检查看不出来」的失效方式：
 *
 * ① **`:deep()` 与 `@keyframes` 的 scope 语义**：partial 是被 `@use` 内联进页面
 *    scoped 块的，理论上 keyframes 名会被加 scope 后缀、`animation` 引用同步改写。
 *    但一旦这条链路断掉（比如把 `.card-enter` 留在页面、把 keyframes 搬去 partial），
 *    表现是**入场动画静默不动**——不报错、不发请求，肉眼不盯着看根本发现不了。
 *    所以这里直接读 computed `animation-name` / `animation-duration`。
 * ② **弹窗与入口是否还连着**：`@add`（widget 内「添加」）与右上角按钮写的是同一个
 *    `showAddWatchlistModal`；搬组件时把弹窗落在页面、把按钮搬进子组件，就会
 *    「点了没反应」。这里点按钮、断言弹窗出现。
 */

test.use({ viewport: { width: 1440, height: 1000 } });

async function mockApis(page: Page) {
  // 首页会打一圈接口（summary / xirr / temperature / watchlist / 通知），
  // 本文件不关心它们的数据，统一 404 让页面进空态/错误态即可
  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({ status: 404, json: { data: null, message: "e2e 未打桩" } })
  );
}

test.describe("首页自选区块拆分后回归（#980 批 B10）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("区块仍在：标题、三个操作入口、自选 widget 都挂上了", async ({
    page
  }) => {
    await mockApis(page);
    await page.goto("/#/welcome");

    // 首页有多张 `.card-enter`（资产看板等），必须用本区块独有的入口锚定，
    // 否则会断言到别的卡片上（初版就踩了这个：`.card-enter` first() 命中的是资产看板）
    const card = page
      .locator(".card-enter")
      .filter({ has: page.getByRole("button", { name: "查看全部" }) });
    await expect(card).toBeVisible({ timeout: 90_000 });

    // 标题由 widget 的 hasPinned 派生：未就绪时是「自选资产」，就绪后是二者之一
    await expect(card.locator("h3, .section-header__title").first()).toHaveText(
      /自选资产|持仓市值最大资产|置顶资产/
    );
    await expect(card).toHaveCount(1);
    await expect(
      card.getByRole("button", { name: "添加", exact: true })
    ).toBeVisible();
    await expect(
      card.getByRole("button", { name: "特别关注", exact: true })
    ).toBeVisible();
    await expect(
      card.getByRole("button", { name: "查看全部", exact: true })
    ).toBeVisible();
  });

  test("点「添加」打开弹窗（入口与弹窗仍在同一个组件里）", async ({ page }) => {
    await mockApis(page);
    await page.goto("/#/welcome");

    // 首页有多张 `.card-enter`（资产看板等），必须用本区块独有的入口锚定，
    // 否则会断言到别的卡片上（初版就踩了这个：`.card-enter` first() 命中的是资产看板）
    const card = page
      .locator(".card-enter")
      .filter({ has: page.getByRole("button", { name: "查看全部" }) });
    await expect(card).toBeVisible({ timeout: 90_000 });

    await card.getByRole("button", { name: "添加", exact: true }).click();
    const dialog = page.locator(".el-dialog").filter({ hasText: "添加自选" });
    await expect(dialog.first()).toBeVisible({ timeout: 30_000 });
  });

  test("「查看全部」跳到我的自选", async ({ page }) => {
    await mockApis(page);
    await page.goto("/#/welcome");

    // 首页有多张 `.card-enter`（资产看板等），必须用本区块独有的入口锚定，
    // 否则会断言到别的卡片上（初版就踩了这个：`.card-enter` first() 命中的是资产看板）
    const card = page
      .locator(".card-enter")
      .filter({ has: page.getByRole("button", { name: "查看全部" }) });
    await expect(card).toBeVisible({ timeout: 90_000 });

    await card.getByRole("button", { name: "查看全部", exact: true }).click();
    await expect(page).toHaveURL(/\/watchlist/, { timeout: 30_000 });
  });

  test("样式搬进 partial 后入场动画仍生效（keyframes 没被 scope 断链）", async ({
    page
  }) => {
    await mockApis(page);
    await page.goto("/#/welcome");

    // 首页有多张 `.card-enter`（资产看板等），必须用本区块独有的入口锚定，
    // 否则会断言到别的卡片上（初版就踩了这个：`.card-enter` first() 命中的是资产看板）
    const card = page
      .locator(".card-enter")
      .filter({ has: page.getByRole("button", { name: "查看全部" }) });
    await expect(card).toBeVisible({ timeout: 90_000 });

    // `animation: fade-up 0.6s ...` 整条声明来自 `_welcome-deep.scss`；
    // 若 keyframes 与引用被拆散，animation-name 会变成 none
    await expect(card).toHaveCSS("animation-name", /fade-up/);
    await expect(card).toHaveCSS("animation-duration", "0.6s");
    // 动画结束后停在终态（forwards），不能留在 opacity: 0
    await expect(card).toHaveCSS("opacity", "1");
  });
});
