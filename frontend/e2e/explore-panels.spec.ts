import { expect, test } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * 探市页档位切换与三块提示卡的回归网（#980 拆分配套）。
 *
 * 拆分把「档位状态 → 显示哪一档」「提示卡渲染 → 往哪跳」拆到了
 * `exploreView/` 下的组件与组合式，跨了组件边界。单测只能钉纯映射
 * （档位归一化、键盘循环），**跨边界的接线只能在真实页面上验**：
 * 点 Tab 是否真的改了 URL 并切显示、点提示卡按钮是否真的跳到目标页、
 * 关掉引导条后 localStorage 是否真的持久。
 */

const ACTIVE_TAB = ".panel-tab--active";
const PANEL_OVERVIEW = "#panel-overview";
const PANEL_DETAIL = "#panel-detail";
const AUTH_GUIDE = ".auth-guide";
const AUTH_GUIDE_CLOSE = ".auth-guide__close";

test.describe("探市页档位切换与提示卡（#980 拆分回归）", () => {
  test("默认落在概览档，深度档此时尚未挂载", async ({
    context,
    page,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await page.goto("/#/explore");

    await expect(page.locator(ACTIVE_TAB)).toHaveText("概览");
    await expect(page.locator(PANEL_OVERVIEW)).toBeVisible();
    // 「首次进入才挂载」：没点过深度档，其 onMounted 的 4 个请求不该发出去
    await expect(page.locator(PANEL_DETAIL)).toHaveCount(0);
  });

  test("点「深度」切档：URL 带 ?view=detail，概览档隐藏而不是卸载", async ({
    context,
    page,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await page.goto("/#/explore");

    await page.locator('[id="panel-tab-detail"]').click();
    await expect(page).toHaveURL(/#\/explore\?view=detail/);
    await expect(page.locator(ACTIVE_TAB)).toHaveText("深度");

    await expect(page.locator(PANEL_DETAIL)).toBeVisible();
    // v-show 而非 v-if：概览档仍在 DOM 里，只是隐藏（避免每次切档重打接口）
    await expect(page.locator(PANEL_OVERVIEW)).toBeHidden();
  });

  test("概览档「大类资产观察」入口：切到深度档并定位", async ({
    context,
    page,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await page.goto("/#/explore");

    // 分类圆点按 ASSET_CATEGORIES 渲染，先确认入口本身有内容
    await expect(page.locator(".asset-entry__cat").first()).toBeVisible();

    await page.locator(".asset-entry__btn").click();
    await expect(page).toHaveURL(/#\/explore\?view=detail/);
    await expect(page.locator(PANEL_DETAIL)).toBeVisible();
  });

  test("已登录引导条可关闭，刷新后不再出现（localStorage 持久）", async ({
    context,
    page,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await page.goto("/#/explore");

    await expect(page.locator(AUTH_GUIDE)).toBeVisible();
    await page.locator(AUTH_GUIDE_CLOSE).click();
    await expect(page.locator(AUTH_GUIDE)).toHaveCount(0);

    await page.reload();
    await expect(page.locator(ACTIVE_TAB)).toHaveText("概览");
    await expect(page.locator(AUTH_GUIDE)).toHaveCount(0);
  });
});
