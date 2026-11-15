import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 第三轮文案收敛回归网：把「同一件事说三遍」压成一遍之后，页面必须仍然看得懂、
 * 功能入口一个不少。
 *
 * 判据同样分两半：
 * 1. 旧文案 / 旧类名不许回来。类名取旧代码里真实存在的（`.auth-guide__desc`、
 *    `.gap-banner__desc`），否则 `toHaveCount(0)` 是恒真空断言；
 * 2. 关键控件与信息仍在（跳转 / 关闭 / 一键补齐 / 缺口明细 / 规则说明的 title）。
 *    只数「文案没了」挡不住「连功能一起删掉」这种回归。
 *
 * 定位一律走 `data-region` / `data-action` 语义锚，不靠随时会被清理的中文文案：
 * 这既让 e2e 不再随文案改动而漂移，也给 AI Agent 提供稳定的 DOM 抓手。
 */

const GAPS = [
  { symbol: "110011", name: "易方达中小盘", asset_type: "fund" },
  { symbol: "600519", name: "贵州茅台", asset_type: "stock" }
];

/** 自选页桩：沿用 watchlist-filter-actions-slim 的兜底顺序（后注册者先匹配） */
async function stubWatchlistWithGaps(page: Page) {
  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({
      status: 404,
      json: { data: null, message: "e2e 未打桩", error_code: 40400 }
    })
  );
  await page.route("**/api/watchlist/groups/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: [
          {
            id: 1,
            key: "all",
            name: "全部",
            label: "全部",
            is_system: true,
            count: 2
          }
        ]
      }
    })
  );
  await page.route("**/api/watchlist/items/**", route =>
    route.fulfill({ status: 200, json: { data: [], total: 0 } })
  );
  await page.route("**/api/watchlist/tags/**", route =>
    route.fulfill({ status: 200, json: { data: [] } })
  );
  await page.route("**/api/watchlist/holding-gaps/**", route =>
    route.fulfill({ status: 200, json: { data: GAPS } })
  );
}

test.describe("说明文案收敛（第三轮）", () => {
  test.setTimeout(180_000);

  test("探市：已登录引导条收敛成一行，跳转与关闭入口仍在", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await page.goto("/#/explore");

    const guide = page.locator('[data-region="explore-auth-guide"]');
    await expect(guide).toBeVisible({ timeout: 90_000 });

    // 旧实现：标题「可前往自选页管理资产」+ 说明「功能已迁移至自选页」
    // + 按钮「前往自选页」，同一件事说了三遍
    await expect(guide.locator(".auth-guide__desc")).toHaveCount(0);
    await expect(guide.getByText("已登录，可前往自选页管理资产")).toHaveCount(
      0
    );
    await expect(guide).toContainText("已迁至自选页");

    await expect(guide.locator('[data-action="go-watchlist"]')).toBeVisible();
    await expect(guide.locator('[data-action="dismiss"]')).toBeVisible();
  });

  test("自选：缺口横幅不再重复弹窗说明，明细与一键补齐仍在", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubWatchlistWithGaps(page);
    await page.goto("/#/watchlist");

    const banner = page.locator('[data-region="holding-gap-banner"]');
    await expect(banner).toBeVisible({ timeout: 90_000 });

    // 旧实现里这条说明与 HoldingGapDialog 的提示逐字重复
    await expect(banner.locator(".gap-banner__desc")).toHaveCount(0);
    await expect(banner).toContainText("2 个持仓产品尚未加入自选");

    // 规则文本没丢：挂 title，鼠标 / 读屏 / Agent 仍可取到
    await expect(banner.locator(".gap-banner__title")).toHaveAttribute(
      "title",
      /持仓即自选/
    );
    await expect(banner.locator(".gap-banner__row")).toHaveCount(2);
    await expect(banner.locator('[data-action="add-all"]')).toBeVisible();
  });
});
