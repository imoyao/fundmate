import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * #980 批 B8 回归网：`SankeyChart` 拆分后的接线（447 → 168 行）。
 *
 * 几何算法搬去 `sankeyLayout.ts`（26 例纯函数单测），option 组装搬去
 * `sankeyOption.ts`。剩下真正会「静默坏掉」的东西只有一件：**布局算出来的
 * `maxY` 有没有被接回模板**——
 *
 *   maxY → `containerHeight = max(maxY + 40, 400)` → `v-bind(containerHeightPx)`
 *
 * 这条线上任何一处断掉（解构改名、忘了 `.value`、CSS 里 v-bind 变量名大小写不一致），
 * 表现都只是「图挤在 400px 里、下半截看不见」或「容器虚高留白」，而 canvas 照样
 * 渲染、控制台一行错都不报。canvas 内部像素没法断言，但**容器高度是 maxY 的
 * 唯一可见投影**，所以本文件用「高度随数据变」+「400 下限」两头夹住它。
 *
 * 另：空数据时 `paint` 会 `dispose()` 实例并留下空态遮罩，容器退回默认 400px
 * ——若拆分后误把 `isEmpty` 接到 `hasDrawableData` 之外，空态遮罩就不再出现。
 */

test.use({ viewport: { width: 1440, height: 1000 } });

const SANKEY_URL = /\/api\/summary\/sankey\//;
const SNAP_URL = /\/api\/summary\/snapshots\//;
const DIST_URL = /\/api\/summary\/distributions\//;
const SUMMARY_URL = /\/api\/summary\/(\?|$)/;

/** 10 个资产叶 + 1 个负债叶：第 2 层堆到 yCursor=400，用来压出 440px 的高度 */
const TALL_SANKEY = {
  nodes: [
    { name: "总资产" },
    { name: "投资理财" },
    { name: "总负债" },
    ...[
      "基金",
      "股票",
      "债券",
      "现金",
      "黄金",
      "保险",
      "房产",
      "外汇",
      "私募",
      "信托"
    ].map(name => ({ name })),
    { name: "房贷" }
  ],
  links: [
    { source: "总资产", target: "投资理财", value: 100 },
    { source: "总资产", target: "总负债", value: 40 },
    ...[
      "基金",
      "股票",
      "债券",
      "现金",
      "黄金",
      "保险",
      "房产",
      "外汇",
      "私募",
      "信托"
    ].map(target => ({ source: "投资理财", target, value: 10 })),
    { source: "总负债", target: "房贷", value: 40 }
  ]
};

/** 单链：maxY=50 ⇒ maxY+40=90 低于 400，验证下限生效 */
const SHORT_SANKEY = {
  nodes: [{ name: "总资产" }, { name: "基金" }],
  links: [{ source: "总资产", target: "基金", value: 100 }]
};

async function mockPanorama(page: Page, sankey: unknown) {
  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({ status: 404, json: { data: null, message: "e2e 未打桩" } })
  );
  await page.route(SANKEY_URL, route =>
    route.fulfill({ json: { data: sankey } })
  );
  await page.route(SNAP_URL, route =>
    route.fulfill({ json: { data: [], message: "" } })
  );
  await page.route(DIST_URL, route =>
    route.fulfill({
      json: {
        data: {
          type_distribution: [],
          allocation_distribution: [],
          market_distribution: [],
          account_distribution: [],
          category_distribution: [],
          liability_distribution: [],
          total_assets: 0,
          total_liabilities: 0
        },
        message: ""
      }
    })
  );
  await page.route(SUMMARY_URL, route =>
    route.fulfill({
      json: {
        data: {
          total_assets_cny: 0,
          total_liabilities_cny: 0,
          total_pnl_cny: 0
        },
        message: ""
      }
    })
  );
}

test.describe("桑基图拆分后回归（#980 批 B8）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("容器高度 = max(maxY + 40, 400)：深树压到 440px，图不会挤进 400px", async ({
    page
  }) => {
    await mockPanorama(page, TALL_SANKEY);
    await page.goto("/#/panorama");

    const container = page.locator(".sankey-chart-container");
    await expect(container).toHaveCount(1, { timeout: 90_000 });
    await expect(container).toHaveCSS("height", "440px");

    // 真的画了：ECharts 会往 .chart 里插 canvas
    await expect(page.locator(".chart canvas")).not.toHaveCount(0);
    // 有数据时不该出现空态遮罩
    await expect(page.locator(".empty-state")).toBeHidden();
    await expect(page.locator(".chart")).toHaveCSS("visibility", "visible");
  });

  test("浅树时高度回落到 400px 下限（不是写死的常量）", async ({ page }) => {
    await mockPanorama(page, SHORT_SANKEY);
    await page.goto("/#/panorama");

    const container = page.locator(".sankey-chart-container");
    await expect(container).toHaveCount(1, { timeout: 90_000 });
    await expect(container).toHaveCSS("height", "400px");
    await expect(page.locator(".chart canvas")).not.toHaveCount(0);
  });

  test("空数据：空态遮罩可见、绘图区隐藏、实例已交回", async ({ page }) => {
    await mockPanorama(page, { nodes: [], links: [] });
    await page.goto("/#/panorama");

    const empty = page.locator(".empty-state");
    await expect(empty).toBeVisible({ timeout: 90_000 });
    await expect(empty).toContainText("暂无资产构成数据");
    await expect(page.locator(".chart")).toHaveCSS("visibility", "hidden");
    // 空数据分支会把实例 dispose 掉，容器退回默认高度
    await expect(page.locator(".sankey-chart-container")).toHaveCSS(
      "height",
      "400px"
    );
  });
});
