import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * #980 批 B8 回归网：`SankeyChart` 拆分后的接线（447 → 168 行）。
 *
 * 节点数据搬去 `sankeyLayout.ts`（纯函数单测），option 组装搬去
 * `sankeyOption.ts`。剩下真正会「静默坏掉」的东西只有一件：**按节点密度算出的
 * `minHeight` 有没有被接回模板**——
 *
 *   最密一列节点数 → `minHeight = max(400, n × (标签行高 16 + nodeGap 16) + 40)`
 *   → `containerHeight` → `v-bind(containerHeightPx)`
 *
 * 2026-11-09 修正：ECharts 6 已移除 `layout: 'none'`，旧的「手算 y 累加出 maxY」
 * 与实际几何脱钩。汇点一多，标签被压进几 px 厚的节点互相盖住。现在高度由
 * **最密一列**决定，同时必须显式 `chart.resize({ height: minHeight })`，否则复用
 * 实例下 canvas 仍按旧高度画。
 *
 * 2026-11-09 D94 修订：桑基图收敛为「资金来源 → 资产运用」单轴守恒图，标签改为
 * 单行 rich（行高 16）、nodeGap 从 36 收到 16，因此高度公式里的单节点占位由
 * 68px 变成 32px；桩数据也换成新拓扑。常量仍由 `sankeyLayout.spec.ts` 钉住，
 * 本文件只验证「高度随数据变」这条接线没断。
 *
 * 这条线上任何一处断掉（解构改名、忘了 `.value`、CSS 里 v-bind 变量名大小写不一致、
 * 漏了 resize），表现都只是「图挤在 400px 里」或「容器虚高留白」，而 canvas 照样
 * 渲染、控制台一行错都不报。canvas 内部像素没法断言，但**容器高度是 minHeight 的
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

/**
 * D94 单轴守恒图 + 20 个资产明细（都落在最密的最后一列）：
 * 20 × (16 + 16) + 40 = 680px。
 * 汇点带显式 depth，不会被 nodeAlign:'justify' 的 moveSinksRight 推走，
 * 所以最密列就是各拓扑层节点数的最大值。
 */
const LEAF_NAMES = Array.from({ length: 20 }, (_, i) => `资产明细${i + 1}`);
const TALL_SANKEY = {
  nodes: [
    { name: "房贷" },
    { name: "净资产" },
    { name: "总负债" },
    { name: "总资产" },
    { name: "固定资产" },
    { name: "流动资金" },
    { name: "投资理财" },
    ...LEAF_NAMES.map(name => ({ name }))
  ],
  links: [
    { source: "房贷", target: "总负债", value: 40 },
    { source: "总负债", target: "总资产", value: 40 },
    { source: "净资产", target: "总资产", value: 160 },
    { source: "总资产", target: "固定资产", value: 60 },
    { source: "总资产", target: "流动资金", value: 40 },
    { source: "总资产", target: "投资理财", value: 100 },
    ...LEAF_NAMES.map(name => ({ source: "投资理财", target: name, value: 5 }))
  ]
};

/** 单链只有 1 个汇点：32 + 40 低于 400，验证下限生效 */
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

  test("容器高度 = 最密列节点数 × (标签行高 + 间距) + 40：20 个明细撑到 680px", async ({
    page
  }) => {
    await mockPanorama(page, TALL_SANKEY);
    await page.goto("/#/panorama");

    const container = page.locator(".sankey-chart-container");
    await expect(container).toHaveCount(1, { timeout: 90_000 });
    await expect(container).toHaveCSS("height", "680px");

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
