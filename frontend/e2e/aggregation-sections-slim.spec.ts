import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * #980 批 A 拆分回归网：聚合视图（Hero / 环形图 / 工具条 / 产品卡）。
 *
 * 一次拆出四个文件的真实风险不是「DOM 还在不在」，而是**跨组件接线**：
 *
 * 1. `AggregationBreakdownDonut` 从 Hero 里整块搬出后，父级不再有 `hasBreakdown`
 *    这个 `v-if`——空数据时必须由子组件自己 `v-if` 掉，否则 Hero 的 flex 布局里
 *    会多出一个占位块（视觉上 Hero 整体左偏）；
 * 2. `AggregationToolbar` 只持有 props、不改状态，交互全部回抛页面。任一 emit 漏接，
 *    「点维度切换没反应」不会报错，只是静默失效——只能真点一次；
 * 3. 类型 Tab 的选项由 `aggregationToolbarModel.buildTypeOptions` 从 `result` 派生，
 *    搬进纯函数后若字段名写错，Tab 就只剩「全部」（也不报错）；
 * 4. 卡片指标（份额 / 净值 / 收益率胶囊）的派生全部下沉到 `productCardModel.ts`，
 *    换算错一位只有真渲染能看出来。
 *
 * 防假绿：每条断言前都先确认「容器真的渲染出来了」，避免「空态下没有某个元素」
 * 被误判成通过。
 */

/** 6 类构成：用于验证图例「前 5 + 其他 N 类」的折叠规则 */
const BREAKDOWN = [
  { name: "股票型", market_value_cents: 40000 },
  { name: "混合型", market_value_cents: 30000 },
  { name: "债券型", market_value_cents: 15000 },
  { name: "指数型", market_value_cents: 8000 },
  { name: "QDII", market_value_cents: 5000 },
  { name: "货币型", market_value_cents: 800 }
];

const GROUP_MULTI = {
  symbol: "110011",
  name: "易方达中小盘混合",
  market_value_cents: 10000,
  quantity: 25000000,
  nav_yuan: 1.23456,
  return_pct: 0.079,
  snapshot_date: "2026-10-20",
  fund_manager: "张坤",
  sources: [
    { ledger_id: 1, ledger_name: "支付宝-基金", market_value_cents: 6000 },
    { ledger_id: 2, ledger_name: "天天基金-基金", market_value_cents: 4000 }
  ]
};

const GROUP_SINGLE = {
  symbol: "000001",
  name: "华夏成长混合",
  market_value_cents: 88800,
  quantity: 20000000,
  nav_yuan: 4.44,
  return_pct: null,
  snapshot_date: "2026-10-18",
  fund_manager: null,
  sources: [{ ledger_id: 3, ledger_name: "招行-基金" }]
};

const INSTITUTION_GROUPS = [
  {
    key: 1,
    institution_name: "蚂蚁（杭州）基金销售有限公司",
    market_value_cents: 6000,
    items: [
      {
        ledger_id: 1,
        ledger_name: "支付宝-基金",
        institution_name: "蚂蚁（杭州）基金销售有限公司",
        institution_alias: "支付宝",
        symbol: "110011",
        name: "易方达中小盘混合",
        market_value_cents: 6000,
        quantity: 15000000,
        nav_yuan: 1.23456,
        return_pct: 0.05,
        snapshot_date: "2026-10-20"
      }
    ]
  }
];

/**
 * 打桩聚合接口；`dimension` 记录每次请求的维度，供「真的重发了请求」断言。
 *
 * ⚠️ 路由必须锚定 host（`/^https?:\/\/[^/]+\/api\//`）：宽 glob 会把 vite 的
 * 源码模块请求（`/src/api/ledger.ts`）一起拦掉，页面直接白屏。
 */
async function stubAggregation(page: Page): Promise<() => string[]> {
  const dimensions: string[] = [];

  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({
      status: 404,
      json: { data: null, message: "e2e 未打桩", error_code: 40400 }
    })
  );

  await page.route(
    /^https?:\/\/[^/]+\/api\/ledgers\/fund-aggregation\//,
    async route => {
      const url = new URL(route.request().url());
      const dimension = url.searchParams.get("dimension") ?? "product";
      dimensions.push(dimension);

      await route.fulfill({
        status: 200,
        json: {
          data: {
            total_market_value_cents: 98800,
            dimension,
            groups:
              dimension === "institution"
                ? INSTITUTION_GROUPS
                : [GROUP_MULTI, GROUP_SINGLE],
            total: dimension === "institution" ? 1 : 2,
            page: 1,
            page_size: 18,
            total_pages: 1,
            snapshot_date: "2026-10-18",
            snapshot_date_latest: "2026-10-20",
            nav_date: "2026-10-21",
            fund_type_counts: { 混合型: 2, 股票型: 0 },
            fund_type_unclassified_count: 1,
            fund_type_breakdown: BREAKDOWN,
            message: "ok"
          }
        }
      });
    }
  );

  return () => dimensions;
}

test.describe("聚合视图拆分回归（#980 批 A）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("Hero：金额 / 数据日期 / 环形图中心与图例折叠", async ({ page }) => {
    await stubAggregation(page);
    await page.goto("/#/funds");

    const hero = page.locator(".hero");
    await expect(hero).toBeVisible({ timeout: 90_000 });

    // 分 → 元（98800 分 = ¥988.00），走 MoneyDisplay 的 xl 档
    await expect(hero.locator(".hero-amount .money-display")).toContainText(
      "988"
    );
    // 数据日期折叠成「10月18日」；有 gap 时挂 info 提示图标
    await expect(hero.locator(".stat-block").first()).toContainText("10月18日");
    await expect(hero.locator(".stat-hint")).toBeVisible();
    // 持仓项数：total = 2
    await expect(hero.locator(".stat-block").nth(1)).toContainText("2 项");

    // 环形图：6 类 → 中心显示「6 类」，图例 5 条 + 「其他 1 类」
    const donut = hero.locator(".hero-donut-block");
    await expect(donut).toBeVisible();
    await expect(donut.locator(".donut-center-count")).toHaveText("6 类");
    await expect(donut.locator(".legend-item")).toHaveCount(6);
    await expect(donut.locator(".legend-item").last()).toContainText(
      "其他 1 类"
    );

    // Hero 与环形图在同一条水平线上（拆出子组件后仍是 flex 兄弟节点）
    const heroBox = (await hero.boundingBox())!;
    const donutBox = (await donut.boundingBox())!;
    expect(donutBox.y).toBeGreaterThanOrEqual(heroBox.y - 1);
    expect(donutBox.y + donutBox.height).toBeLessThanOrEqual(
      heroBox.y + heroBox.height + 1
    );
  });

  test("工具条：类型 Tab 只列有产品的分类，切换维度真的重发请求", async ({
    page
  }) => {
    const dimensions = await stubAggregation(page);
    await page.goto("/#/funds");

    const bar = page.locator(".control-bar");
    await expect(bar).toBeVisible({ timeout: 90_000 });
    await expect(bar.locator(".search-input")).toBeVisible();

    // 类型 Tab：股票型计数为 0 不出现；未分类计数 1 出现
    const typeTab = bar.locator('[aria-label="基金类型筛选"]');
    await expect(typeTab).toBeVisible();
    await expect(typeTab).toContainText("全部");
    await expect(typeTab).toContainText("混合型");
    await expect(typeTab).toContainText("未分类");
    await expect(typeTab).not.toContainText("股票型");

    // 排序档位与升降序按钮
    const sortControl = bar.locator(".sort-control");
    await expect(sortControl.locator('[aria-label="排序方式"]')).toBeVisible();
    await expect(sortControl.locator(".order-btn")).toBeVisible();

    // 维度切换：点击后必须重新请求（旧实现由页面直接改 ref，拆分后靠 emit 回抛）
    await expect.poll(() => dimensions()).toEqual(["product"]);
    await bar.getByText("按渠道展示", { exact: true }).click();
    await expect.poll(() => dimensions()).toEqual(["product", "institution"]);

    // 渠道模式：卡片副标题是账本名，且带钱包图标
    const cards = page.locator(".card-grid .product-card");
    await expect(cards).toHaveCount(1);
    await expect(cards.first().locator(".product-subtitle")).toHaveText(
      "支付宝-基金"
    );
    await expect(cards.first().locator(".sub-icon")).toBeVisible();
  });

  test("产品卡：份额 / 净值精度 / 收益率胶囊 / 多渠道提示", async ({
    page
  }) => {
    await stubAggregation(page);
    await page.goto("/#/funds");

    const cards = page.locator(".card-grid .product-card");
    await expect(cards).toHaveCount(2, { timeout: 90_000 });

    const multi = cards.first();
    await expect(multi.locator(".product-name")).toHaveText("易方达中小盘混合");
    await expect(multi.locator(".product-code")).toHaveText("110011");
    await expect(multi.locator(".product-subtitle")).toHaveText("张坤");

    // 市值 10000 分 = ¥100.00；收益率 0.079 → +7.90%
    await expect(multi.locator(".primary-amount .money-display")).toContainText(
      "100"
    );
    await expect(multi.locator(".return-badge")).toHaveText("+7.90%");
    await expect(multi.locator(".return-badge")).toHaveClass(
      /return-badge--positive/
    );

    // 份额 25000000/10000 = 2,500.00；净值保留 4 位
    const secondary = multi.locator(".secondary-value");
    await expect(secondary.nth(0)).toHaveText("2,500.00");
    await expect(secondary.nth(1)).toHaveText("1.2346");

    // 两个渠道 → 「2 账户」提示 + 底部日期折叠成 MM-DD
    await expect(multi.locator(".foot-channel")).toContainText("2 账户");
    await expect(multi.locator(".card-foot .foot-item").first()).toContainText(
      "10-20"
    );

    // 单渠道 + 无成本：不显示账户提示，收益率走中性胶囊
    const single = cards.nth(1);
    await expect(single.locator(".foot-channel")).toHaveCount(0);
    await expect(single.locator(".return-badge")).toHaveText("--");
    await expect(single.locator(".return-badge")).toHaveClass(
      /return-badge--flat/
    );
    await expect(single.locator(".secondary-value").nth(1)).toHaveText(
      "4.4400"
    );
  });
});
