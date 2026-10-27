import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * #980 批 B6 回归网：资产全景顶部两张并排卡（`OverviewSummaryCard`）拆分后的接线。
 *
 * 拆成 `OverviewAssetsCard`（左）+ `OverviewInsightCard`（右）+ `_summary-card.scss`
 * （两卡共用的壳）之后，有三件事静态检查看不见：
 *
 * 1. **等高**：两卡并排靠的是「外层 el-col `h-full` + 卡片 `h-full` + 右卡卡片体锁
 *    280px」。壳被抽到 partial 后，若某个 scoped 块漏了 `@use`，卡片就没有
 *    `background-color` / `border` / `box-shadow`，视觉上「卡片消失」但 DOM 正常。
 * 2. **`host-header` 契约**（#2050）：右卡自己写 `<h3>`，PnlCalendar 必须一帧
 *    SectionHeader 都不画，否则出现两个同名标题。这条 e2e 不进 per-PR 门禁，
 *    所以拆分时特别容易把它弄丢——故在拆分回归网里再钉一次。
 * 3. **两态切换的标题翻转**：#1925 的原地开关，标题 / tooltip / aria-label 四处
 *    必须同步变，只换一处会让用户找不到回去的路。
 */

test.use({ viewport: { width: 1440, height: 1000 } });

const SUMMARY_URL = /\/api\/summary\/(\?|$)/;
const SANKEY_URL = /\/api\/summary\/sankey\//;
const DIST_URL = /\/api\/summary\/distributions\//;
const SNAP_URL = /\/api\/summary\/snapshots\//;

async function mockPanorama(page: Page) {
  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({ status: 404, json: { data: null, message: "e2e 未打桩" } })
  );
  await page.route(SANKEY_URL, route =>
    route.fulfill({ json: { data: { nodes: [], links: [] }, message: "" } })
  );
  await page.route(SNAP_URL, route =>
    route.fulfill({
      json: {
        data: [
          {
            snapshot_date: "2026-10-01",
            total_assets: 1250000,
            total_liabilities: 250000,
            net_assets: 1000000,
            monthly_change_pct: 1.24,
            yearly_change_pct: 6.8
          }
        ],
        message: ""
      }
    })
  );
  await page.route(DIST_URL, route =>
    route.fulfill({
      json: {
        data: {
          type_distribution: [
            { name: "基金", value: 800000 },
            { name: "股票", value: 450000 }
          ],
          allocation_distribution: [],
          market_distribution: [],
          account_distribution: [],
          category_distribution: [],
          liability_distribution: [],
          total_assets: 1250000,
          total_liabilities: 250000
        },
        message: ""
      }
    })
  );
  await page.route(SUMMARY_URL, route =>
    route.fulfill({
      json: {
        data: {
          total_assets_cny: 1250000,
          total_liabilities_cny: 250000,
          total_pnl_cny: 12345.67
        },
        message: ""
      }
    })
  );
}

test.describe("资产全景摘要卡拆分后回归（#980 批 B6）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("两卡等高且各自带壳：底色 / 描边 / 阴影都来自 _summary-card.scss", async ({
    page
  }) => {
    await mockPanorama(page);
    await page.goto("/#/panorama");

    const cards = page.locator(".summary-card");
    await expect(cards).toHaveCount(2, { timeout: 90_000 });

    // 壳的四个声明逐一断：漏 @use 时这里会掉到 transparent / 0px
    for (let i = 0; i < 2; i += 1) {
      await expect(cards.nth(i)).toHaveCSS("background-color", /.+/);
      await expect(cards.nth(i)).not.toHaveCSS(
        "background-color",
        "rgba(0, 0, 0, 0)"
      );
      await expect(cards.nth(i)).not.toHaveCSS("border-top-width", "0px");
      await expect(cards.nth(i)).not.toHaveCSS("box-shadow", "none");
    }

    // 等高：右卡卡片体锁 280px、左卡靠 h-full 跟随，两卡底边必须对齐
    const [left, right] = await Promise.all([
      cards.nth(0).boundingBox(),
      cards.nth(1).boundingBox()
    ]);
    expect(left).not.toBeNull();
    expect(right).not.toBeNull();
    expect(Math.abs(left!.height - right!.height)).toBeLessThanOrEqual(1);
  });

  test("左卡三指标：负债 / 净资产 / 盈亏三列齐全，结构性断点在位", async ({
    page
  }) => {
    await mockPanorama(page);
    await page.goto("/#/panorama");

    const left = page.locator(".summary-card").first();
    await expect(left).toBeVisible({ timeout: 90_000 });

    await expect(left).toContainText("总资产（本月）");
    await expect(left).toContainText("总负债");
    await expect(left).toContainText("净资产");
    await expect(left).toContainText("总盈亏");
    await expect(left).toContainText("较上月");
    await expect(left).toContainText("较去年同期");

    // 三列必须是三个并列块（拆成独立组件后 grid 若丢失会变成竖排）
    await expect(left.locator(".summary-card__metric")).toHaveCount(3);
    // 结构性断点仍在
    await expect(left.locator(".summary-card__rule")).toHaveCount(1);
  });

  test("右卡两态切换：标题翻转、PnlCalendar 不画 SectionHeader（host-header）", async ({
    page
  }) => {
    await mockPanorama(page);
    await page.goto("/#/panorama");

    const right = page.locator(".summary-card").nth(1);
    await expect(right).toBeVisible({ timeout: 90_000 });
    await expect(right.locator("h3")).toHaveText("资产大类");
    // 构成图态：卡片体里没有日历
    await expect(right.locator(".pnl-calendar")).toHaveCount(0);

    const toggle = page.getByRole("button", { name: "打开收益日历" });
    await toggle.click();

    await expect(right.locator("h3")).toHaveText("收益日历");
    // 控件排无条件渲染，用它证明日历真的挂上了（不依赖后端日历数据是否取到）
    await expect(right.locator(".pnl-calendar__controls")).toBeVisible({
      timeout: 30_000
    });
    // host-header 契约（#2050）：宿主自己写了 h3，日历不得再画一遍
    await expect(right.locator(".pnl-calendar .section-header")).toHaveCount(0);
    // 卡片体高度锁死 280px：两态共用同一高度，切换零跳变
    const body = right.locator(".overview-card__body");
    const box = await body.boundingBox();
    expect(box).not.toBeNull();
    expect(Math.abs(box!.height - 280)).toBeLessThanOrEqual(1);

    // 切回去：标题与 aria-label 同步翻转
    await page.getByRole("button", { name: "返回资产大类" }).click();
    await expect(right.locator("h3")).toHaveText("资产大类");
    await expect(right.locator(".pnl-calendar")).toHaveCount(0);
  });
});
