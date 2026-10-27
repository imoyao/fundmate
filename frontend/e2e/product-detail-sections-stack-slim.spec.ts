import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * #980 批 B11 回归网：产品详情页正文区块栈拆分后的接线（427 → 249 行）。
 *
 * 正文那块 168 行「十几个 Section + 大段 v-if 门控」搬进了
 * `components/ProductDetailSections.vue`。这次拆分有一个**结构前提**，
 * 静态检查（等价性只比对字符串）完全看不见：
 *
 *   `.product-detail__main` 是 `display:flex; flex-direction:column; gap: var(--space-5)`，
 *   gap 只作用于**直接子节点**。所以子组件必须是多根（fragment），让这些 Section
 *   直接成为它的子节点；一旦有人给它包一层 div「看着整齐点」，父级 flex 就只剩一个
 *   子项 —— 一页 9~14 张卡会全部贴在一起，且没有任何报错。
 *
 * 另外钉住页内导航：`useProductPageNav` 是靠 MutationObserver 扫 `pageMain` 里的
 * `[id^="nav-"]` 生成锚点的。若区块被塞进一个不渲染实际 DOM 的壳里（或 id 被吞掉），
 * 顶部胶囊与右侧目录会**静默消失**。
 */

const SYMBOL = "000961";
const NAME = "沪深300ETF联接A";
const HOST_API = /^https?:\/\/[^/]+\/api\//;

const PERF_STUB = {
  fund_kind: "fund",
  applicable: true,
  basis: "acc_nav",
  intervals: [
    { key: "1m", label: "近 1 月", value: 2.31 },
    { key: "3m", label: "近 3 月", value: -1.42 }
  ],
  max_drawdown: -18.52,
  max_drawdown_basis: "fixed_3y",
  max_drawdown_window: "近3年",
  max_drawdown_as_of: "2026-10-23",
  volatility_1y: 22.14,
  as_of: "2026-10-24",
  source: "天天基金",
  current_drawdown: 0,
  risk_window: "近3年",
  risk_sample_points: 731,
  risk_caveats: [],
  shape_gain2: { shape_gain2: 9.42 }
};

async function stubApis(page: Page) {
  await page.route(HOST_API, route =>
    route.fulfill({
      status: 404,
      json: { data: null, message: "e2e 未打桩", error_code: 40400 }
    })
  );
  await page.route("**/api/utils/enums/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: { asset_type: { fund: "基金" }, market: { CN_A: "A股" } },
        message: "ok"
      }
    })
  );
  await page.route(new RegExp(HOST_API.source + "products/resolve/"), route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          symbol: SYMBOL,
          asset_type: "fund",
          market: "CN_A",
          venue: null,
          display_name: NAME,
          in_watchlist: false,
          has_position: false,
          source: "catalog"
        },
        message: "ok"
      }
    })
  );
  await page.route(
    new RegExp(HOST_API.source + "products/fund-performance/"),
    route =>
      route.fulfill({ status: 200, json: { data: PERF_STUB, message: "ok" } })
  );
}

test.describe("产品详情页区块栈拆分后回归（#980 批 B11）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("区块仍是 .product-detail__main 的直接子节点（多根没被包成单根）", async ({
    page
  }) => {
    await stubApis(page);
    await page.goto(`/#/fund/${SYMBOL}`);

    const main = page.locator(".product-detail__main");
    await expect(main).toBeVisible({ timeout: 90_000 });

    // 单根壳的标志：直接子节点只有 1 个。正常应有多张卡
    const children = main.locator("> *");
    const count = await children.count();
    expect(count).toBeGreaterThanOrEqual(2);

    // gap 生效：第二张卡的顶边要在第一张卡底边之下留出空隙
    const [first, second] = await Promise.all([
      children.nth(0).boundingBox(),
      children.nth(1).boundingBox()
    ]);
    expect(first).not.toBeNull();
    expect(second).not.toBeNull();
    const gap = second!.y - (first!.y + first!.height);
    expect(gap).toBeGreaterThan(1);
  });

  test("页内导航仍由真实锚点生成（pageMain 里的 nav-* 没被壳吞掉）", async ({
    page
  }) => {
    await stubApis(page);
    await page.goto(`/#/fund/${SYMBOL}`);

    await expect(page.locator(".product-detail__main")).toBeVisible({
      timeout: 90_000
    });

    // 锚点确实渲染在 DOM 里
    const anchors = await page.locator('[id^="nav-"]').count();
    expect(anchors).toBeGreaterThanOrEqual(2);

    // 顶部胶囊或右侧目录至少有一个接管（两者都靠 navItems.length > 1）
    const navChips = await page.locator(".page-nav, .page-toc").count();
    expect(navChips).toBeGreaterThanOrEqual(1);
  });
});
