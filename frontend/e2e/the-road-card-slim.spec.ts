import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * #980 批 B6 回归网：未竟之蹊单卡（`RoadCard`）拆分后的接线。
 *
 * 卡片被拆成「封面浮层 / 三行身份信息 / 指标条 / 底部行」四个子组件 + 一个纯函数模块。
 * 静态检查看不出、单测也测不到的三件事，必须在这里钉：
 *
 * 1. **`--card-color` 的继承链**：类型胶囊的底色读的是 `.road-card` 上设的
 *    `--card-color`，从父卡 → 封面组件 → `RoadSparkline` 根 → 插槽元素要跨三层。
 *    某一层断了不会报错，只会让胶囊变成透明背景——看得见但说不出哪里错。
 * 2. **编辑入口的跨组件 hover**：`.road-edit-entry` 的 `opacity: 0` 基态搬进了
 *    封面组件，而「何时显示」的祖先选择器只能留在父卡里用 `:deep()` 穿透。
 *    这条规则一旦写回非 `:deep()` 形式，按钮就永远不出现（#1834 的原症状）。
 * 3. **两态显隐**：身份信息在编辑态也显示，指标条与底部行只在浏览态显示。
 *
 * 数据全部打桩，不依赖本机后端。
 */

const FAV_URL = /\/api\/watchlist\/favorites\//;
const TAGS_URL = /\/api\/watchlist\/tags\//;
const CLEARED_URL = /\/api\/watchlist\/items\/\?.*status=cleared/;
const TRENDS_URL = /\/api\/watchlist\/trends\//;

/** 相对今天算日期，避免跨零点时「还有 3 天」漂成「还有 2 天」 */
function plusDays(n: number): string {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + n);
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}

const FUND = {
  id: 11,
  symbol: "110022",
  market: "OTC",
  display_name: "华泰柏瑞新经济",
  asset_type: "fund",
  venue: "OTC",
  holding_quantity: 0,
  favorite: true,
  favorite_at: plusDays(-10),
  next_review_date: plusDays(3),
  is_pinned: true,
  notes: "长期看好消费复苏节奏",
  notes_summary: "长期看好消费复苏节奏",
  add_reason: null,
  tag_ids: [7],
  current_price: 1.1,
  price_at_added: 1.0,
  holding_pnl: null,
  holding_pnl_percent: null,
  position_market_value: null,
  created_at: null,
  updated_at: "2099-01-02T00:00:00"
};

/** 没有复盘日期、没有 trend、没有价格的卡：三处降级文案同时命中 */
const STOCK = {
  id: 12,
  symbol: "600519",
  market: "SH",
  display_name: "紫金矿业",
  asset_type: "stock",
  venue: "EXCHANGE",
  holding_quantity: 0,
  favorite: true,
  favorite_at: plusDays(-3),
  next_review_date: null,
  is_pinned: false,
  notes: null,
  notes_summary: null,
  add_reason: null,
  tag_ids: [],
  current_price: null,
  price_at_added: null,
  holding_pnl: null,
  holding_pnl_percent: null,
  position_market_value: null,
  created_at: null,
  updated_at: "2099-01-01T00:00:00"
};

async function mockFavorites(page: Page) {
  // 兜底最宽、最先注册（Playwright 后注册先匹配）
  await page.route(/^https?:\/\/[^/]+\/api\//, route =>
    route.fulfill({ status: 404, json: { data: null, message: "e2e 未打桩" } })
  );
  await page.route(CLEARED_URL, route =>
    route.fulfill({ json: { data: [], message: "" } })
  );
  await page.route(TAGS_URL, route =>
    route.fulfill({
      json: {
        data: [{ id: 7, name: "长期持有", color: "#557596" }],
        message: ""
      }
    })
  );
  await page.route(TRENDS_URL, route =>
    route.fulfill({
      json: {
        data: { "110022": [1.0, 1.0, 1.2] },
        message: ""
      }
    })
  );
  await page.route(FAV_URL, route =>
    route.fulfill({ json: { data: [FUND, STOCK], message: "" } })
  );
}

test.describe("未竟之蹊单卡拆分后回归（#980 批 B6）", () => {
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL }) => {
    await injectSupabaseSession(context, baseURL!);
  });

  test("封面胶囊：类型色沿 --card-color 跨组件继承，状态与标签照旧", async ({
    page
  }) => {
    await mockFavorites(page);
    await page.goto("/#/the-road-not-taken");

    const fund = page.locator(".road-card", { hasText: "华泰柏瑞新经济" });
    const stock = page.locator(".road-card", { hasText: "紫金矿业" });
    await expect(fund).toBeVisible({ timeout: 90_000 });
    await expect(stock).toBeVisible();

    // 1) 类型胶囊文案
    await expect(fund.locator(".road-chip--type")).toHaveText("基金");
    await expect(stock.locator(".road-chip--type")).toHaveText("股票");

    // 2) 底色来自 fallthrough 的 --card-color（--asset-cat-fund / --asset-cat-stock）。
    //    断具体 rgb 而不是「两张卡不同」：色值相同的话后者会假红，
    //    而断 rgb 能同时证明「继承到了」和「没串台」。
    await expect(fund.locator(".road-chip--type")).toHaveCSS(
      "background-color",
      "rgb(85, 117, 150)"
    );
    await expect(stock.locator(".road-chip--type")).toHaveCSS(
      "background-color",
      "rgb(130, 101, 168)"
    );

    // 3) 状态胶囊：两张卡都还没持仓 ⇒ 观察中
    await expect(fund.locator(".road-chip--state")).toHaveText("观察中");

    // 4) 标签芯片仍在（tag_ids → tags 的映射由 pickTags 完成）
    await expect(fund).toContainText("长期持有");
    await expect(stock.locator(".road-tag")).toHaveCount(0);
  });

  test("指标条与底部行：有数据横排、无数据给说明句，复盘文案按时限分档", async ({
    page
  }) => {
    await mockFavorites(page);
    await page.goto("/#/the-road-not-taken");

    const fund = page.locator(".road-card", { hasText: "华泰柏瑞新经济" });
    const stock = page.locator(".road-card", { hasText: "紫金矿业" });
    await expect(fund).toBeVisible({ timeout: 90_000 });

    // 自选以来 10.00% + 近 3 日 20.00%（trends 桩只给了基金）
    await expect(fund.locator(".road-metric")).toHaveCount(2);
    await expect(fund.locator(".road-metrics")).toContainText("自选以来");
    await expect(fund.locator(".road-metrics")).toContainText("近 3 日");
    await expect(fund.locator(".road-metrics")).toContainText("+10.00%");

    // 股票卡：没有价格、没有 trend ⇒ 一格都不出现，只剩说明句
    await expect(stock.locator(".road-metric")).toHaveCount(0);
    await expect(stock.locator(".road-metrics--empty")).toHaveText(
      "行情数据积累中"
    );

    // 复盘文案：+3 天 ⇒ 「还有 3 天该复盘」；未设日期 ⇒ 降级句
    await expect(fund.locator(".road-review")).toContainText("还有 3 天该复盘");
    await expect(fund.locator(".road-review")).toHaveClass(/is-due/);
    await expect(stock.locator(".road-review")).toContainText("还没定复盘日期");
    await expect(stock.locator(".road-review")).not.toHaveClass(/is-due/);

    // 置顶态图标：fund 已置顶
    await expect(fund.locator(".road-op").nth(1)).toHaveClass(/is-on/);
  });

  test("编辑入口靠父卡 :deep() 唤起 —— 不悬停时不可见，悬停后出现", async ({
    page
  }) => {
    await mockFavorites(page);
    await page.goto("/#/the-road-not-taken");

    const fund = page.locator(".road-card", { hasText: "华泰柏瑞新经济" });
    await expect(fund).toBeVisible({ timeout: 90_000 });

    const entry = fund.locator(".road-edit-entry");
    // 静息态：按钮存在但透明（不是 display:none，键盘仍可聚焦）
    await expect(entry).toHaveCSS("opacity", "0");

    await fund.hover();
    // 这条断言是 `:deep()` 的回归网：若父卡的 `.road-card:hover .road-edit-entry`
    // 退回非穿透写法，跨 scoped 块就不匹配，此处会一直是 0。
    await expect(entry).toHaveCSS("opacity", "1");
  });
});
