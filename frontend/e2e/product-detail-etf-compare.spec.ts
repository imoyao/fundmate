import { expect, test } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 详情页关联 ETF 对比表回归网（#2275 · P0）。
 *
 * 钉四条不变式：
 * 1. **对比表全渲染**：两行 ETF 按成交额降序、净值 4 位小数、正负带符号
 *    （红涨绿跌 class 由组件内处理，这里钉文本）、null 窗口「—」不编数；
 * 2. **口径标注**：脚注带净值日期 + T-1 口径 + 新浪来源；跟踪差 title 带口径警示；
 * 3. **独立降级**：对比接口 500 → 对比块显示「—」，关联标的 chips 照常渲染
 *    （对比表是补充信息，不阻塞关联区块）；
 * 4. **挂载门控**：无 ETF 关联时不渲染对比块（由父组件 peer_role 门控，
 *    该分支由 ProductRelatedSection 现有降级路径覆盖，此处不重复）。
 *
 * 接口全部 page.route 打桩，不依赖后端（docs/dev/frontend-e2e.md §7）。
 *
 * 反向验证：删掉 ProductRelatedSection 里 <ProductEtfCompare> 挂载 → 两用例红；
 * 把 pctText 的 null 分支改回硬编码 0 → 「—」计数断言红。
 */

const NAME = "光伏产业指数";
const SYMBOL = "931151";

async function stubCompareApis(
  page: import("@playwright/test").Page,
  opts?: { compareStatus?: number }
) {
  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({
      status: 404,
      json: { data: null, message: "e2e 未打桩", error_code: 40400 }
    })
  );
  await page.route("**/api/utils/enums/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          asset_type: { index: "指数", etf: "ETF" },
          market: { CN_A: "A股" }
        },
        message: "ok"
      }
    })
  );
  await page.route("**/api/products/resolve/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          symbol: SYMBOL,
          asset_type: "index",
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
  await page.route("**/api/products/related-symbols/**", route =>
    route.fulfill({
      status: 200,
      json: {
        data: {
          links: [
            {
              code: "510300",
              name: "沪深300ETF华泰柏瑞",
              link_type: "index_etf",
              label: "同标的 ETF",
              peer_role: "etf"
            },
            {
              code: "159915",
              name: "创业板ETF易方达",
              link_type: "index_etf",
              label: "同标的 ETF",
              peer_role: "etf"
            }
          ],
          groups: ["同标的 ETF"]
        },
        message: "ok"
      }
    })
  );
  await page.route("**/api/products/index-etf-compare/**", route => {
    if (opts?.compareStatus) {
      return route.fulfill({
        status: opts.compareStatus,
        json: { data: null }
      });
    }
    return route.fulfill({
      status: 200,
      json: {
        data: {
          index_code: SYMBOL,
          as_of: "2026-10-16",
          rows: [
            {
              code: "510300",
              name: "沪深300ETF华泰柏瑞",
              nav: 4.0123,
              nav_date: "2026-10-16",
              nav_change_pct: -0.25,
              change_pct: 0.5,
              amount: 16092791436,
              returns: { m1: 1.2, m3: null, m6: -3.4, y1: 25.1 },
              tracking_diff_y1: 0.34
            },
            {
              code: "159915",
              name: "创业板ETF易方达",
              nav: 2.789,
              nav_date: "2026-10-16",
              nav_change_pct: 0.12,
              change_pct: null,
              amount: 814365660,
              returns: { m1: null, m3: -1.1, m6: 2.2, y1: 12.3 },
              tracking_diff_y1: null
            }
          ]
        },
        message: "ok"
      }
    });
  });
  await page.route("**/api/positions/**", route =>
    route.fulfill({
      status: 200,
      json: { data: [], total: 0, page: 1, per_page: 100, message: "ok" }
    })
  );
}

test.describe("详情页关联 ETF 对比表（#2275）", () => {
  test.setTimeout(120_000);

  test("对比表全渲染：降序 + 口径脚注 + null 窗口「—」", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubCompareApis(page);
    await page.goto(`/#/index/${SYMBOL}`);

    // 关联标的 chips 照常渲染（对比表是同卡内子区块，不取代 chips）。
    // 注意收窄到 __list：ETF 名称在下方对比表里也出现，strict mode 会撞多匹配
    const chips = page.locator(".rel-section__list");
    await expect(chips.getByText("沪深300ETF华泰柏瑞")).toBeVisible();
    await expect(
      page.locator(".rel-section__subtitle").filter({ hasText: "同标的 ETF" })
    ).toBeVisible();

    const cmp = page.locator(".etf-cmp");
    await expect(cmp.getByText("关联 ETF 对比")).toBeVisible();

    // 第一行（成交额 160亿 > 81亿，降序在前）：净值 4 位小数、正负带符号
    await expect(cmp.getByText("4.0123")).toBeVisible();
    await expect(cmp.getByText("+0.50%")).toBeVisible();
    await expect(cmp.getByText("160.93亿")).toBeVisible();
    await expect(cmp.getByText("+1.20%")).toBeVisible();
    await expect(cmp.getByText("-3.40%")).toBeVisible();
    await expect(cmp.getByText("+25.10%")).toBeVisible();
    await expect(cmp.getByText("+0.34%")).toBeVisible();

    // null 字段诚实降级：row1 的 m3 + row2 的涨幅/m1/跟踪差 = 恰好 4 个「—」
    // （计数断言：多了是漏降级，少了是编数）
    await expect(cmp.getByText("—")).toHaveCount(4);

    // 口径脚注：净值日期 + T-1 + 来源
    await expect(
      cmp.getByText("净值截至 2026-10-16（T-1 口径） · 当日行情来自新浪财经")
    ).toBeVisible();
  });

  test("对比接口失败独立降级：对比块空态，关联 chips 照常", async ({
    context,
    baseURL,
    page
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubCompareApis(page, { compareStatus: 500 });
    await page.goto(`/#/index/${SYMBOL}`);

    const cmp = page.locator(".etf-cmp");
    await expect(cmp.getByText("—")).toBeVisible(); // 空态（与全表「无数据一律 —」一致）

    // 独立降级：对比挂了不拖垮关联标的区块（断网/接口失败是验收项）
    const related = page.locator(".rel-section");
    await expect(related.getByText("同标的 ETF").first()).toBeVisible();
    await expect(
      related.locator(".rel-section__list").getByText("创业板ETF易方达")
    ).toBeVisible();
  });
});
