import { expect, test, type Page } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 产品详情页去重回归网（用户反馈：同一个产品名在一页里出现 4 次）。
 *
 * 钉两条不变式：
 * 1. 识别信息（名称 + 品类）只由页头承担，识别卡（`.product-detail__hero`）不再复述；
 * 2. 持仓区块按账户分行，行标签是渠道名，不再逐行抄产品名，表头整块只出一次——
 *    因此整页产品名恰好只出现 1 次。
 *
 * 接口全部用 `page.route` 打桩，不依赖后端（docs/dev/frontend-e2e.md §7）。
 */

const NAME = "永赢北证50成份指数发起C";
const SYMBOL = "023887";

async function stubProductApis(page: Page) {
  // 兜底：未显式打桩的接口一律 404，让各区块走自己的降级分支——
  // 否则这些请求会经 vite 代理打到本机 8000 端口的真后端，用例就不再自洽。
  // ⚠️ 必须用**锚定到 host 的正则**而不是 `**/api/**`：后者连 vite 的源码模块请求
  // `/src/api/auth.ts` 也一起匹配掉（首版就是这么把应用壳打死在加载页上的）。
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
          asset_type: { fund: "基金", stock: "股票" },
          market: { CN_A: "A股" },
          venue: { OTC: "场外", EXCHANGE: "场内" }
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
          asset_type: "fund",
          market: "CN_A",
          venue: "OTC",
          display_name: NAME,
          in_watchlist: true,
          has_position: true,
          source: "position"
        },
        message: "ok"
      }
    })
  );
  await page.route("**/api/positions/**", route =>
    // 注意：**不能**套信封包装器——positions 的响应体本身就是
    // `{ data: [...], total, page, per_page }`，再包一层会让组件拿到对象而非数组
    // （症状：整块显示「当前产品暂无持仓记录。」，第一版就是这么错的）
    // 两条不同 ledger 的持仓，用于走通 #2012 的「多账户」分支（单账户会进指标网格）
    route.fulfill({
      status: 200,
      json: {
        data: [position(1, 2, "支付宝"), position(2, 3, "招商银行")],
        total: 2,
        page: 1,
        per_page: 100,
        message: "ok"
      }
    })
  );
}

/** 打桩持仓行：只有 id / ledger_id / account_name 会变，其余口径字段恒定 */
function position(id: number, ledgerId: number, accountName: string) {
  return {
    id,
    symbol: SYMBOL,
    name: NAME,
    market: "CN_A",
    type: "fund",
    account_name: accountName,
    quantity: 29551.43,
    avg_price: 10000,
    currency: "CNY",
    current_price: 7600,
    trade_date: "2026-10-08",
    notes: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ledger_id: ledgerId,
    market_value: 22532.97,
    pnl: -18.5
  };
}

test.describe("产品详情页去重（页头承担识别信息）", () => {
  // 冷启动时 vite 首次编译整套依赖可能超过默认 60s
  test.setTimeout(180_000);

  test.beforeEach(async ({ context, baseURL, page }) => {
    await injectSupabaseSession(context, baseURL!);
    await stubProductApis(page);
  });

  test("识别卡不再复述产品名与品类（识别信息只在页头出现）", async ({
    page
  }) => {
    await page.goto(`/#/fund/${SYMBOL}`);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(NAME, {
      timeout: 60_000
    });
    // 修复前：识别卡里还有一个 h2 名称 + 类型徽章，与页头一字不差地重复
    const hero = page.locator(".product-detail__hero");
    await expect(hero).toBeVisible();
    expect(await countVisibleIn(hero, NAME)).toBe(0);
    expect(await countVisibleIn(hero, "基金")).toBe(0);
  });

  test("识别卡仍展示代码等事实项（去重不等于删信息）", async ({ page }) => {
    await page.goto(`/#/fund/${SYMBOL}`);
    const hero = page.locator(".product-detail__hero");
    await expect(hero).toBeVisible({ timeout: 60_000 });
    await expect(hero.getByText(SYMBOL)).toBeVisible();
    await expect(hero.getByText("已关注")).toBeVisible();
    await expect(hero.getByText("已持有")).toBeVisible();
  });

  test("整页产品名只出现 1 次，持仓表头整块只出 1 次", async ({ page }) => {
    await page.goto(`/#/fund/${SYMBOL}`);
    // 等持仓区块渲染完（打桩里有两条不同账户的持仓 → 走多账户表格分支）
    const table = page.locator(".product-position__table");
    await expect(table).toBeVisible({ timeout: 60_000 });

    // 页头 h1 = 唯一一次；识别卡与持仓行里都不再重复
    const bodyText = await page.locator("body").innerText();
    expect(bodyText.split(NAME).length - 1).toBe(1);

    // #2012 之后整块只有**一个** thead（旧版每个渠道块各带一整套表头），
    // 且首列是「账户」而不是「产品」
    await expect(table.locator("thead")).toHaveCount(1);
    await expect(table.locator("thead th").first()).toHaveText("账户");
    await expect(page.getByText("产品", { exact: true })).toHaveCount(0);

    // 行标签是账户名——产品名不再以任何形式出现在持仓区块里
    await expect(table.locator("tbody .product-position__account")).toHaveText([
      "支付宝",
      "招商银行"
    ]);
  });
});

/** 计数限定在某个容器内（识别卡），避免被页头 / 持仓区块的同名文本干扰 */
function countVisibleIn(locator: ReturnType<Page["locator"]>, text: string) {
  return locator.evaluate((el, name) => {
    const body = (el as HTMLElement).innerText ?? "";
    return body.split(name).length - 1;
  }, text);
}
